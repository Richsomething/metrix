"""Agent chains: analyst → motivator → auditor (one revision round), plus a free-form assistant.

Two subjects share the chain: the overperformance bonus and the АВ (agency reward) cabinet.
Every number in a report comes from deterministic tools, never from the LLM.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..kv.engine import KvDataError
from . import prompts
from .llm import LlmRunner, RunResult
from .schemas import Analysis, AskReport, AuditVerdict, KvReviewReport, ModelUse, MotivationLetter, ReviewReport
from .toolbox import Toolbox
from .tools import build_kv_tools, build_tools, kv_brief

MAX_REVISIONS = 1

ANALYST_TOOLS = ["get_agent_history", "get_plan_explanation", "get_model_quality", "get_bonus_rules"]
MOTIVATOR_TOOLS = ["get_required_fact", "simulate_bonus", "get_plan_explanation"]
AUDITOR_TOOLS = ["get_bonus", "get_required_fact", "get_agent_history", "get_bonus_rules"]


def _facts_block(facts: dict) -> str:
    return f"<facts>\n{json.dumps(facts, ensure_ascii=False, indent=1, default=str)}\n</facts>"


def _model_use(role: str, result: RunResult) -> ModelUse:
    return ModelUse(role=role, model=result.model, fallback_reason=result.fallback_reason)


@dataclass(frozen=True)
class _ChainSpec:
    subject: str
    systems: dict[str, str]
    tools: dict[str, list]


@dataclass(frozen=True)
class _ChainResult:
    analysis: Analysis
    letter: MotivationLetter
    audit: AuditVerdict
    revisions: int
    runs: list[tuple[str, RunResult]]


class BonusAgents:
    def __init__(self, box: Toolbox, runner: LlmRunner, kv=None) -> None:
        self.box = box
        self.runner = runner
        self.kv = kv

    def _chain(self, spec: _ChainSpec, facts: str) -> _ChainResult:
        def run(role: str, prompt: str, output_format):
            return self.runner.run(role=role, system=spec.systems[role], prompt=prompt, tools=spec.tools[role], output_format=output_format)

        analysis = run("analyst", f"Разбери {spec.subject}.\n\n{facts}", Analysis)

        def write(issues: list[str]) -> RunResult[MotivationLetter]:
            revision = "\n\nКонтролёр нашёл ошибки в прошлой версии — исправь их:\n- " + "\n- ".join(issues) if issues else ""
            return run(
                "motivator",
                f"Напиши письмо агенту: {spec.subject}.\n\n{facts}\n\n<analysis>\n{analysis.output.model_dump_json(indent=1)}\n</analysis>{revision}",
                MotivationLetter,
            )

        def audit(letter: RunResult[MotivationLetter]) -> RunResult[AuditVerdict]:
            return run("auditor", f"Проверь письмо: {spec.subject}.\n\n{facts}\n\n<letter>\n{letter.output.model_dump_json(indent=1)}\n</letter>", AuditVerdict)

        letter = write([])
        verdict = audit(letter)
        runs = [("analyst", analysis), ("motivator", letter), ("auditor", verdict)]
        revisions = 0
        while not verdict.output.approved and revisions < MAX_REVISIONS:
            letter = write(verdict.output.issues)
            verdict = audit(letter)
            runs += [("motivator", letter), ("auditor", verdict)]
            revisions += 1
        return _ChainResult(analysis.output, letter.output, verdict.output, revisions, runs)

    def review(self, agent: str, quarter: str) -> ReviewReport:
        raw_facts = self.box.review_facts(agent, quarter)  # raises for an unknown agent or a non-completed quarter
        spec = _ChainSpec(
            subject=f"премия за перевыполнение плана, агент {agent}, завершённый квартал {quarter}",
            systems={"analyst": prompts.ANALYST, "motivator": prompts.MOTIVATOR, "auditor": prompts.AUDITOR},
            tools={
                "analyst": build_tools(self.box, ANALYST_TOOLS),
                "motivator": build_tools(self.box, MOTIVATOR_TOOLS),
                "auditor": build_tools(self.box, AUDITOR_TOOLS),
            },
        )
        r = self._chain(spec, _facts_block(raw_facts))
        return ReviewReport(
            agent=agent, quarter=quarter, bonus=raw_facts["bonus"], analysis=r.analysis, letter=r.letter, audit=r.audit,
            revisions=r.revisions, tool_calls=[c for _, run in r.runs for c in run.tool_calls],
            models=[_model_use(role, run) for role, run in r.runs],
        )

    def kv_review(self, agent: str, quarter: str) -> KvReviewReport:
        if self.kv is None:
            raise KvDataError("Нет данных АВ — запустите обучение (python -m metrixs_ml.train)")
        brief = kv_brief(self.kv.cabinet(agent, quarter))  # raises KvDataError for bad agent/quarter
        tools = build_kv_tools(self.kv)
        spec = _ChainSpec(
            subject=f"агентское вознаграждение (АВ), агент {agent}, квартал расчёта {quarter}",
            systems={"analyst": prompts.KV_ANALYST, "motivator": prompts.KV_MOTIVATOR, "auditor": prompts.KV_AUDITOR},
            tools={"analyst": tools, "motivator": tools, "auditor": tools},
        )
        r = self._chain(spec, _facts_block(brief))
        return KvReviewReport(
            agent=agent, quarter=quarter, calculation=brief, analysis=r.analysis, letter=r.letter, audit=r.audit,
            revisions=r.revisions, tool_calls=[c for _, run in r.runs for c in run.tool_calls],
            models=[_model_use(role, run) for role, run in r.runs],
        )

    def ask(self, question: str) -> AskReport:
        tools = build_tools(self.box) + (build_kv_tools(self.kv) if self.kv is not None else [])
        hint = f"\nОткрытый квартал АВ: {self.kv.options()['currentQuarter']}." if self.kv is not None else ""
        result = self.runner.run(
            role="assistant",
            system=prompts.ASSISTANT,
            prompt=f"<question>\n{question}\n</question>{hint}",
            tools=tools,
        )
        return AskReport(answer=result.text, tool_calls=list(result.tool_calls), models=[_model_use("assistant", result)])
