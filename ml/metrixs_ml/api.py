"""FastAPI service: recommended plans from artifacts + bonuses from config (config changes need no retraining).

    uvicorn metrixs_ml.api:app --port 8000

Completed quarters (`/plans`, `/bonuses`) and the future quarter (`/forecast`, `/bonus/scenarios`)
are served separately: a bonus is calculated only for a completed quarter with a known fact.
"""

from __future__ import annotations

import json
import re
import threading
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from . import settings
from .agents.llm import (
    AgentConfigError,
    AgentError,
    AgentRateLimitError,
    AgentRefusalError,
    AgentSettings,
    ClaudeRunner,
    LlmRunner,
    ModelUnavailableError,
)
from .agents.pipeline import BonusAgents
from .agents.toolbox import Toolbox, ToolboxError
from .bonus import BonusConfig, bonus_curve, calculate_bonus, demo_scenarios, load_bonus_config
from .kv.engine import KvDataError, KvInputs
from .kv.routes import TAG as KV_TAG, register_kv_routes
from .kv.rules import RulesCache, RulesError
from .kv.service import KvService

YEAR_PATTERN = re.compile(r"^\d{4}$")
# LLM calls are slow and paid: allow only a few at once and reject the rest instead of queueing.
MAX_CONCURRENT_AGENT_RUNS = 2

FORECAST_LIMITATION = (
    "Рекомендуемый план будущего квартала — это прогноз сборов. Если тот же прогноз подставить и как факт, "
    "план и результат совпадут и премия по построению будет 0. Поэтому для будущего квартала показываются "
    "только сценарии «что если», а не ожидаемая премия."
)

AGENT_HELP = "Имя работника. Пусто — все."
YEAR_HELP = "Год, например 2026. Пусто — все."

API_DESCRIPTION = """
Планы, премии и ИИ-агенты. Премия — только за завершённые кварталы. Данные синтетические.
"""

OPENAPI_TAGS = [
    {"name": "Прогноз и сценарии", "description": "Следующий квартал."},
    {"name": "Премии за завершённые кварталы", "description": "Прошедшие кварталы."},
    {"name": "ИИ-агенты", "description": "Агенты на Claude."},
    {"name": "Модель", "description": "Модель и правила."},
    {"name": "Служебные", "description": "Проверка."},
    {"name": "АВ: моя мотивация", "description": "Агентское вознаграждение по Решению ДРБ-УРСП-125/2019: ставки, доход, план. Отдельно от премии."},
]


class ReviewRequest(BaseModel):
    agent: str = Field(min_length=1, max_length=100, description="Имя работника, как в `/model`", examples=["Сато Кенъити"])
    quarter: str = Field(pattern=r"^\d{4}Q[1-4]$", description="Завершённый квартал, ГГГГQN", examples=["2026Q3"])


class AskRequest(BaseModel):
    question: str = Field(
        min_length=3,
        max_length=1000,
        description="Вопрос о планах, фактах или премиях",
        examples=["Почему у Сато Кенъити премия за 2026Q3 такая маленькая?"],
    )


def default_runner() -> LlmRunner:
    return ClaudeRunner(AgentSettings.from_env())


@dataclass(frozen=True)
class Artifacts:
    plans: list[dict]
    metrics: dict
    bonus_config: BonusConfig


def load_artifacts(artifacts_dir: Path, bonus_config_file: Path) -> Artifacts:
    plans_path = artifacts_dir / settings.PLANS_FILE
    metrics_path = artifacts_dir / settings.METRICS_FILE
    if not plans_path.exists() or not metrics_path.exists():
        raise FileNotFoundError(
            f"Нет артефактов модели в {artifacts_dir}. Сначала запустите: python -m metrixs_ml.train"
        )
    return Artifacts(
        plans=json.loads(plans_path.read_text(encoding="utf-8")),
        metrics=json.loads(metrics_path.read_text(encoding="utf-8")),
        bonus_config=load_bonus_config(bonus_config_file),
    )


def with_bonus(row: dict, config: BonusConfig) -> dict:
    """Bonus only for a completed quarter; a forecast row never gets one."""
    if row["kind"] != "completed":
        return {**row, "completion": None, "bonus": None}
    result = calculate_bonus(row["recommendedPlan"], row["fact"], row["refundShare"] or 0.0, config)
    return {
        **row,
        "completion": round(result.completion, 4),
        "bonus": {
            "amount": result.amount,
            "overperformance": round(result.overperformance, 2),
            "capped": result.capped,
            "refundPenalized": result.refund_penalized,
        },
    }


def scenario_payload(scenario) -> dict:
    r = scenario.result
    return {
        "key": scenario.key,
        "title": scenario.title,
        "fact": scenario.fact,
        "refundShare": scenario.refund_share,
        "completion": round(r.completion, 4),
        "overperformance": round(r.overperformance, 2),
        "amount": r.amount,
        "capped": r.capped,
        "refundPenalized": r.refund_penalized,
    }


def create_app(
    artifacts_dir: Path = settings.ARTIFACTS_DIR,
    bonus_config_file: Path = settings.BONUS_CONFIG_FILE,
    runner_factory: Callable[[], LlmRunner] = default_runner,
    kv_rules_file: Path = settings.KV_RULES_FILE,
) -> FastAPI:
    state: dict[str, object] = {}
    agent_slots = threading.BoundedSemaphore(MAX_CONCURRENT_AGENT_RUNS)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        state["artifacts"] = load_artifacts(artifacts_dir, bonus_config_file)
        yield

    app = FastAPI(
        title="Metrixs ML — планы и премии",
        version="0.2.0",
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )

    def artifacts() -> Artifacts:
        return state["artifacts"]  # type: ignore[return-value]

    def validate(agent: str | None, year: str | None) -> None:
        if agent and agent not in artifacts().metrics["agents"]:
            raise HTTPException(status_code=400, detail="Неизвестный агент")
        if year and not YEAR_PATTERN.match(year):
            raise HTTPException(status_code=400, detail="Год должен быть в формате ГГГГ")

    def select(agent: str | None, year: str | None, kind: str | None = None) -> list[dict]:
        a = artifacts()
        return [
            with_bonus(r, a.bonus_config)
            for r in a.plans
            if (not agent or r["agent"] == agent)
            and (not year or r["quarter"].startswith(year))
            and (not kind or r["kind"] == kind)
        ]

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        """API-only service: send a browser opening the root to the interactive docs."""
        return RedirectResponse(url="/docs")

    @app.get("/health", tags=['Служебные'], summary='Проверка, что сервис жив', description='Сервис запущен.')
    def health() -> dict:
        return {"success": True, "data": {"status": "ok"}}

    @app.get("/model", tags=['Модель'], summary='Метаданные модели и качество плана', description='Выбранная модель, её ошибка (синтетика), дата отчёта, список работников.')
    def model() -> dict:
        return {"success": True, "data": artifacts().metrics}

    @app.get("/config", tags=['Модель'], summary='Действующие правила премирования', description='Правила премий из `bonus.json`.')
    def config() -> dict:
        return {"success": True, "data": artifacts().bonus_config.model_dump()}

    @app.get("/plans", tags=['Премии за завершённые кварталы'], summary='Рекомендуемые планы по кварталам', description='План, факт и премия по кварталам. `kind`: completed — премия есть, forecast — только план.')
    def plans(agent: str | None = Query(None, max_length=100, description=AGENT_HELP), year: str | None = Query(None, max_length=4, description=YEAR_HELP)) -> dict:
        validate(agent, year)
        return {"success": True, "data": select(agent, year)}

    @app.get("/bonuses", tags=['Премии за завершённые кварталы'], summary='Сумма премий по работникам', description='Сумма премий по работникам за завершённые кварталы.')
    def bonuses(agent: str | None = Query(None, max_length=100, description=AGENT_HELP), year: str | None = Query(None, max_length=4, description=YEAR_HELP)) -> dict:
        """Bonus totals for completed quarters only."""
        validate(agent, year)
        totals: dict[str, dict] = defaultdict(lambda: {"bonus": 0.0, "recommendedPlan": 0.0, "fact": 0.0, "quarters": 0})
        for r in select(agent, year, kind="completed"):
            t = totals[r["agent"]]
            t["bonus"] += r["bonus"]["amount"]
            t["recommendedPlan"] += r["recommendedPlan"]
            t["fact"] += r["fact"]
            t["quarters"] += 1
        data = [
            {
                "agent": name,
                **{k: round(v, 2) for k, v in t.items()},
                "completion": round(t["fact"] / t["recommendedPlan"], 4),
            }
            for name, t in sorted(totals.items(), key=lambda item: -item[1]["bonus"])
        ]
        return {"success": True, "data": data}

    @app.get("/forecast", tags=['Прогноз и сценарии'], summary='Рекомендуемый план на будущий квартал', description='Прогноз сборов на следующий квартал. Премии нет.')
    def forecast(agent: str | None = Query(None, max_length=100, description=AGENT_HELP)) -> dict:
        """Recommended plan for the next, not yet completed quarter — no fact, no bonus."""
        validate(agent, None)
        rows = [
            {"agent": r["agent"], "recommendedPlan": r["recommendedPlan"], "contributions": r["contributions"]}
            for r in select(agent, None, kind="forecast")
        ]
        return {
            "success": True,
            "data": {
                "quarter": artifacts().metrics.get("forecastQuarter"),
                "rows": rows,
                "totalRecommendedPlan": round(sum(r["recommendedPlan"] for r in rows), 2),
                "limitation": FORECAST_LIMITATION,
            },
        }

    @app.get("/bonus/scenarios", tags=['Прогноз и сценарии'], summary='Демонстрационные сценарии правил премирования', description='Примеры расчёта премии по правилам. Не выплаты.')
    def bonus_scenarios(agent: str | None = Query(None, max_length=100, description=AGENT_HELP)) -> dict:
        """Demonstration of the bonus rules on the agent's forecast-quarter recommended plan."""
        validate(agent, None)
        a = artifacts()
        name = agent or a.metrics["agents"][0]
        row = next((r for r in a.plans if r["agent"] == name and r["kind"] == "forecast"), None)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Нет прогнозного квартала для агента {name}")
        return {
            "success": True,
            "data": {
                "demo": True,
                "agent": name,
                "quarter": row["quarter"],
                "plan": row["recommendedPlan"],
                "planSource": "рекомендуемый план на основе прогноза",
                "config": a.bonus_config.model_dump(),
                "scenarios": [scenario_payload(s) for s in demo_scenarios(row["recommendedPlan"], a.bonus_config)],
            },
        }

    @app.get("/bonus/forecast", tags=['Прогноз и сценарии'], summary='Прогноз премии работника (главный график)', description='Кривая «сборы → премия» для работника. Главный график.')
    def bonus_forecast(agent: str | None = Query(None, max_length=100, description=AGENT_HELP)) -> dict:
        """Employee bonus outlook for the next quarter: bonus vs. collections, with the model forecast marked."""
        validate(agent, None)
        a = artifacts()
        name = agent or a.metrics["agents"][0]
        row = next((r for r in a.plans if r["agent"] == name and r["kind"] == "forecast"), None)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Нет прогнозного квартала для агента {name}")
        c = a.bonus_config
        plan = row["recommendedPlan"]
        threshold = plan * (1 + c.threshold)
        history = [r for r in a.plans if r["agent"] == name and r["kind"] == "completed"]
        return {
            "success": True,
            "data": {
                "agent": name,
                "quarter": row["quarter"],
                "forecastCollections": plan,
                "forecastBonus": calculate_bonus(plan, plan, 0.0, c).amount,
                "threshold": round(threshold, 2),
                "capReachedAt": round(threshold + c.cap_per_quarter / c.rate, 2) if c.rate > 0 else None,
                "lastFact": history[-1]["fact"] if history else None,
                "lastQuarter": history[-1]["quarter"] if history else None,
                "config": c.model_dump(),
                "curve": [p.model_dump() for p in bonus_curve(plan, c)],
                "note": FORECAST_LIMITATION,
            },
        }

    def kv_service() -> KvService:
        if "kv" not in state:
            path = artifacts_dir / settings.KV_INPUTS_FILE
            if not path.exists():
                raise HTTPException(status_code=503, detail="Нет данных АВ (kv_inputs.json). Запустите: python -m metrixs_ml.train")
            state["kv"] = KvService(KvInputs(json.loads(path.read_text(encoding="utf-8"))), RulesCache(kv_rules_file))
        return state["kv"]  # type: ignore[return-value]

    register_kv_routes(app, kv_service)

    def agents() -> BonusAgents:
        if "agents" not in state:
            a = artifacts()
            box = Toolbox(plans=tuple(a.plans), metrics=a.metrics, config=a.bonus_config)
            kv = kv_service() if (artifacts_dir / settings.KV_INPUTS_FILE).exists() else None
            state["agents"] = BonusAgents(box, runner_factory(), kv=kv)
        return state["agents"]  # type: ignore[return-value]

    def run_agents(action: Callable[[BonusAgents], BaseModel]) -> dict:
        if not agent_slots.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="Агенты заняты другими запросами, повторите через минуту")
        try:
            return {"success": True, "data": action(agents()).model_dump()}
        except (ToolboxError, KvDataError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RulesError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except AgentRefusalError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except AgentRateLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except (AgentConfigError, ModelUnavailableError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except AgentError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        finally:
            agent_slots.release()

    # Sync handlers: FastAPI runs them in a worker thread, so the blocking SDK calls don't stall the loop.
    @app.post("/agents/review", tags=['ИИ-агенты'], summary='Разбор завершённого квартала ИИ-агентами', description='ИИ-агенты разбирают квартал и пишут письмо работнику. Нужен `ANTHROPIC_API_KEY`.')
    def agents_review(request: ReviewRequest) -> dict:
        return run_agents(lambda a: a.review(request.agent, request.quarter))

    @app.post("/agents/ask", tags=['ИИ-агенты'], summary='Вопрос ИИ-ассистенту о планах и премиях', description='Вопрос ИИ-ассистенту о планах и премиях.')
    def agents_ask(request: AskRequest) -> dict:
        return run_agents(lambda a: a.ask(request.question))

    @app.post(
        "/agents/kv-review",
        tags=["ИИ-агенты"],
        summary="Разбор АВ ИИ-агентами",
        description="Агенты объясняют ставки АВ (база и Доп.АВ1–3) и план их повышения. Нужен `ANTHROPIC_API_KEY`.",
    )
    def agents_kv_review(request: ReviewRequest) -> dict:
        return run_agents(lambda a: a.kv_review(request.agent, request.quarter))

    return app


app = create_app()
