"""Agents are tested with a scripted fake runner — no network, no API key."""

import json

import pytest
from fastapi.testclient import TestClient

import anthropic
import httpx2 as httpx

from metrixs_ml.agents.llm import (
    AgentConfigError,
    AgentError,
    AgentRefusalError,
    AgentSettings,
    ClaudeRunner,
    ModelUnavailableError,
    RunResult,
)
from metrixs_ml.agents.pipeline import BonusAgents
from metrixs_ml.agents.schemas import Analysis, AuditVerdict, MotivationLetter
from metrixs_ml.agents.toolbox import Toolbox, ToolboxError
from metrixs_ml.agents.tools import build_tools
from metrixs_ml.api import create_app
from metrixs_ml.bonus import BonusConfig

CONFIG = BonusConfig(rate=0.05, threshold=0.0, cap_per_quarter=150_000, max_refund_share=0.1, refund_penalty=0.5)
PLANS = (
    {"agent": "Агент А", "quarter": "2025Q1", "kind": "completed", "recommendedPlan": 100_000, "fact": 110_000,
     "refundShare": 0.01, "isForecast": False, "approvedPlan": None, "bonusBasis": "recommended_plan",
     "contributions": [{"key": "base", "label": "База", "value": 100_000}]},
    {"agent": "Агент А", "quarter": "2025Q2", "kind": "forecast", "recommendedPlan": 120_000, "fact": None,
     "refundShare": None, "isForecast": True, "approvedPlan": None, "bonusBasis": None,
     "contributions": [{"key": "base", "label": "База", "value": 120_000}]},
)
METRICS = {"chosen": "trend", "agents": ["Агент А"], "scores": [{"name": "trend", "title": "Тренд", "wape": 0.01, "bias": 0.0}]}


@pytest.fixture
def box() -> Toolbox:
    return Toolbox(plans=PLANS, metrics=METRICS, config=CONFIG)


class ScriptedRunner:
    """Returns queued outputs per role and records every call."""

    def __init__(self, outputs: dict[str, list]):
        self.outputs = {role: list(items) for role, items in outputs.items()}
        self.calls: list[dict] = []

    def run(self, *, role, system, prompt, tools, output_format=None):
        self.calls.append({"role": role, "prompt": prompt, "tools": [t.name for t in tools]})
        output = self.outputs[role].pop(0)
        text = output if isinstance(output, str) else output.model_dump_json()
        return RunResult(output=None if isinstance(output, str) else output, text=text, tool_calls=(), model="fake")


ANALYSIS = Analysis(summary="План перевыполнен на 10%", strengths=["рост"], risks=[], plan_drivers=["база"])
LETTER = MotivationLetter(title="Итоги", body="Премия 500", next_steps=["Собрать 1 120 000"])


def test_bonus_matches_formula(box):
    bonus = box.bonus("Агент А", "2025Q1")

    assert bonus["amount"] == pytest.approx(500)
    assert bonus["completionPct"] == pytest.approx(110)


def test_required_fact_is_inverse_of_what_if(box):
    needed = box.required_fact("Агент А", "2025Q2", 30_000)

    check = box.what_if("Агент А", "2025Q2", needed["requiredFact"])

    assert check["amount"] == pytest.approx(30_000)


def test_toolbox_rejects_bad_input(box):
    with pytest.raises(ToolboxError):
        box.bonus("Чужой", "2025Q1")
    with pytest.raises(ToolboxError):
        box.bonus("Агент А", "2025-1")
    with pytest.raises(ToolboxError):
        box.bonus("Агент А", "2025Q2")  # forecast quarter has no fact
    with pytest.raises(ToolboxError):
        box.required_fact("Агент А", "2025Q2", 1_000_000)  # above cap


def test_tools_return_json_from_toolbox(box):
    tools = {t.name: t for t in build_tools(box)}

    result = json.loads(tools["get_bonus"].call({"agent": "Агент А", "quarter": "2025Q1"}))

    assert result["amount"] == pytest.approx(500)


def test_review_uses_toolbox_bonus_and_revises_rejected_letter(box):
    runner = ScriptedRunner(
        {
            "analyst": [ANALYSIS],
            "motivator": [LETTER, LETTER],
            "auditor": [AuditVerdict(approved=False, issues=["Неверная сумма"]), AuditVerdict(approved=True, issues=[])],
        }
    )

    report = BonusAgents(box, runner).review("Агент А", "2025Q1")

    assert report.bonus["amount"] == pytest.approx(500)
    assert report.audit.approved and report.revisions == 1
    assert "Неверная сумма" in runner.calls[3]["prompt"]
    assert "<facts>" in runner.calls[0]["prompt"]


def test_review_stops_after_max_revisions(box):
    reject = AuditVerdict(approved=False, issues=["x"])
    runner = ScriptedRunner({"analyst": [ANALYSIS], "motivator": [LETTER, LETTER], "auditor": [reject, reject]})

    report = BonusAgents(box, runner).review("Агент А", "2025Q1")

    assert not report.audit.approved
    assert report.revisions == 1


def test_claude_runner_reports_missing_credentials(monkeypatch):
    class NoAuthClient:
        class beta:
            class messages:
                @staticmethod
                def tool_runner(**_):
                    raise TypeError("Could not resolve authentication method. Expected one of api_key")

    runner = ClaudeRunner(AgentSettings(), client=NoAuthClient())

    with pytest.raises(AgentConfigError):
        runner.run(role="x", system="s", prompt="p", tools=[])


def test_claude_runner_sends_effort_cache_and_no_refusal_fallback():
    runner = ClaudeRunner(AgentSettings(effort="high"), client=object())

    params = runner._params("claude-opus-5-5", "s", "p", [], Analysis)

    assert params["output_config"] == {"effort": "high"}
    assert params["cache_control"] == {"type": "ephemeral"}
    assert "fallbacks" not in params and "betas" not in params  # no server-side routing around refusals
    assert params["model"] == "claude-opus-5-5"


def _http_error(cls, status):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("err", response=httpx.Response(status, request=request), body=None)


class _Final:
    def __init__(self, stop_reason):
        self.stop_reason = stop_reason
        self.content = [type("B", (), {"type": "text", "text": '{"approved": true, "issues": []}'})()]


class SequenceClient:
    """tool_runner raises or yields per model, recording which models were called."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.models = []
        outer = self

        class _Messages:
            @staticmethod
            def tool_runner(**params):
                outer.models.append(params["model"])
                action = outer.behaviour[params["model"]]
                if isinstance(action, Exception):
                    raise action
                return iter([_Final(action)])

        self.beta = type("Beta", (), {"messages": _Messages})()


def _run(client, fallback="claude-opus-5"):
    runner = ClaudeRunner(AgentSettings(fallback_model=fallback), client=client)
    return runner.run(role="auditor", system="s", prompt="p", tools=[], output_format=AuditVerdict)


@pytest.mark.parametrize("error", [(anthropic.OverloadedError, 529), (anthropic.ServiceUnavailableError, 503), (anthropic.NotFoundError, 404)])
def test_unavailable_model_switches_to_fallback(error):
    client = SequenceClient({"claude-opus-5-5": _http_error(*error), "claude-opus-5": "end_turn"})

    result = _run(client)

    assert client.models == ["claude-opus-5-5", "claude-opus-5"]
    assert result.model == "claude-opus-5" and "недоступна" in result.fallback_reason


def test_refusal_is_not_routed_to_fallback():
    client = SequenceClient({"claude-opus-5-5": "refusal", "claude-opus-5": "end_turn"})

    with pytest.raises(AgentRefusalError):
        _run(client)
    assert client.models == ["claude-opus-5-5"]


def test_technical_error_does_not_switch_model():
    client = SequenceClient({"claude-opus-5-5": _http_error(anthropic.InternalServerError, 500), "claude-opus-5": "end_turn"})

    with pytest.raises(AgentError) as exc:
        _run(client)
    assert not isinstance(exc.value, (AgentRefusalError, ModelUnavailableError))
    assert client.models == ["claude-opus-5-5"]


def test_unavailable_without_fallback_reports_unavailability():
    client = SequenceClient({"claude-opus-5-5": _http_error(anthropic.OverloadedError, 529)})

    with pytest.raises(ModelUnavailableError):
        _run(client, fallback="")


@pytest.fixture
def api(tmp_path):
    (tmp_path / "plans.json").write_text(json.dumps(list(PLANS), ensure_ascii=False), encoding="utf-8")
    (tmp_path / "metrics.json").write_text(json.dumps(METRICS, ensure_ascii=False), encoding="utf-8")
    config = tmp_path / "bonus.json"
    config.write_text(CONFIG.model_dump_json(), encoding="utf-8")
    runner = ScriptedRunner(
        {"analyst": [ANALYSIS], "motivator": [LETTER], "auditor": [AuditVerdict(approved=True, issues=[])], "assistant": ["Ответ"]}
    )
    app = create_app(artifacts_dir=tmp_path, bonus_config_file=config, runner_factory=lambda: runner)
    with TestClient(app) as client:
        yield client


def test_api_review_returns_report(api):
    response = api.post("/agents/review", json={"agent": "Агент А", "quarter": "2025Q1"})

    assert response.status_code == 200
    assert response.json()["data"]["bonus"]["amount"] == pytest.approx(500)


def test_api_review_validates_input(api):
    assert api.post("/agents/review", json={"agent": "Агент А", "quarter": "2025-1"}).status_code == 422
    assert api.post("/agents/review", json={"agent": "Чужой", "quarter": "2025Q1"}).status_code == 400


def test_api_ask(api):
    response = api.post("/agents/ask", json={"question": "Почему такая премия?"})

    assert response.json()["data"]["answer"] == "Ответ"


def test_kv_review_uses_kv_calculation_and_kv_tools(box, tmp_path):
    from tests.test_kv import _agent, _service

    kv = _service(tmp_path, {"Агент А": _agent()})
    runner = ScriptedRunner(
        {"analyst": [ANALYSIS], "motivator": [LETTER], "auditor": [AuditVerdict(approved=True, issues=[])]}
    )

    report = BonusAgents(box, runner, kv=kv).kv_review("Агент А", "2026Q3")

    assert report.calculation["nextRate"]["quarter"] == "2026Q4"
    assert all({"get_kv_cabinet", "simulate_kv"} <= set(c["tools"]) for c in runner.calls)
    assert "агентское вознаграждение" in runner.calls[0]["prompt"]


def test_kv_review_without_kv_data_is_a_clear_error(box):
    from metrixs_ml.kv.engine import KvDataError

    with pytest.raises(KvDataError):
        BonusAgents(box, ScriptedRunner({})).kv_review("Агент А", "2026Q4")
