"""Claude tool definitions over the deterministic Toolbox.

Tool errors raise; the SDK tool runner returns them to the model as `is_error` results,
so the agent can correct an agent name or quarter and retry.
"""

from __future__ import annotations

import json
from typing import Iterable

from anthropic import beta_tool
from anthropic.lib.tools import BetaFunctionTool

from .toolbox import Toolbox


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def build_tools(box: Toolbox, names: Iterable[str] | None = None) -> list[BetaFunctionTool]:
    @beta_tool
    def list_agents() -> str:
        """Список агентов, по которым есть планы и премии."""
        return _json(box.agents())

    @beta_tool
    def get_bonus_rules() -> str:
        """Действующие правила расчёта премии: формула, ставка, порог, потолок, штраф за возвраты."""
        return _json(box.bonus_rules())

    @beta_tool
    def get_agent_history(agent: str) -> str:
        """Поквартальная история агента: план, факт, выполнение плана, премия, доля возвратов.

        Args:
            agent: Имя агента ровно как в списке агентов.
        """
        return _json(box.history(agent))

    @beta_tool
    def get_plan_explanation(agent: str, quarter: str) -> str:
        """Из чего сложился план агента на квартал: база и вклад каждого фактора в деньгах.

        Args:
            agent: Имя агента.
            quarter: Квартал в формате ГГГГQN, например 2026Q3.
        """
        return _json(box.plan_explanation(agent, quarter))

    @beta_tool
    def get_bonus(agent: str, quarter: str) -> str:
        """Точный расчёт премии агента за прошедший квартал по действующим правилам.

        Args:
            agent: Имя агента.
            quarter: Прошедший квартал в формате ГГГГQN.
        """
        return _json(box.bonus(agent, quarter))

    @beta_tool
    def simulate_bonus(agent: str, quarter: str, fact: float) -> str:
        """Какой была бы премия при заданной сумме сборов (расчёт «что если»).

        Args:
            agent: Имя агента.
            quarter: Квартал в формате ГГГГQN (можно прогнозный).
            fact: Гипотетическая сумма сборов за квартал.
        """
        return _json(box.what_if(agent, quarter, fact))

    @beta_tool
    def get_required_fact(agent: str, quarter: str, target_bonus: float) -> str:
        """Сколько нужно собрать в квартале, чтобы получить целевую премию.

        Args:
            agent: Имя агента.
            quarter: Квартал в формате ГГГГQN (обычно прогнозный).
            target_bonus: Желаемая премия за квартал.
        """
        return _json(box.required_fact(agent, quarter, target_bonus))

    @beta_tool
    def get_model_quality() -> str:
        """Качество модели плана на бэктесте: какая модель выбрана и её ошибка на невиденных кварталах."""
        return _json(box.model_quality())

    tools = {
        t.name: t
        for t in [
            list_agents,
            get_bonus_rules,
            get_agent_history,
            get_plan_explanation,
            get_bonus,
            simulate_bonus,
            get_required_fact,
            get_model_quality,
        ]
    }
    if names is None:
        return list(tools.values())
    return [tools[name] for name in names]


def kv_brief(cabinet: dict) -> dict:
    """Compact cabinet for the LLM: every number comes from the АВ service."""
    def rate(r: dict) -> dict:
        m = r["metrics"]
        return {
            "quarter": r["quarter"],
            "reporting": r["reporting"],
            "previous": r["previous"],
            "status": r["statusTitle"],
            "rates": [{k: x[k] for k in ("title", "base", "d1", "d2", "d3", "total", "capped", "note")} for x in r["rates"]],
            "metrics": {
                "dvs": m["dvs"], "dvsPrevious": m["dvsPrevious"], "dynamics": m["dynamics"],
                "dynamicsFloorApplied": m["dynamicsFloorApplied"], "penetration": m["penetration"],
                "prolongation": m["prolongation"],
            },
            "components": {
                "kaskoBase": {k: r["components"]["kaskoBase"][k] for k in ("rate", "newcomer", "group", "scale")},
                "d1": r["components"]["d1"], "d2": r["components"]["d2"], "d3": r["components"]["d3"],
            },
        }

    plan = cabinet["plan"]
    return {
        "agent": cabinet["agent"],
        "agentInfo": cabinet["agentInfo"],
        "asOf": cabinet["asOf"],
        "rule": cabinet["currentRate"]["rule"],
        "currentRate": rate(cabinet["currentRate"]),
        "nextRate": rate(cabinet["nextRate"]),
        "income": {
            period: {s: {"quarter": v["quarter"], "kv": v["kv"], "base": v["base"], "kind": v["kindTitle"],
                         "unrated": v["unrated"]}
                     for s, v in cabinet["income"][period].items()}
            for period in ("current", "next")
        },
        "scenarioNote": cabinet["scenarioNote"],
        "plan": {
            **{k: v for k, v in plan.items() if k not in ("steps", "options")},
            "steps": [{k: st.get(k) for k in ("title", "target", "from", "to", "needs", "gain", "blocked")}
                      for st in plan.get("steps", [])],
            "options": [{k: o[k] for k in ("title", "kasko", "priority", "prolonged", "contracts", "components", "effects")}
                        for o in plan.get("options", [])],
        },
        "assumptions": cabinet["assumptions"],
    }


def build_kv_tools(service) -> list[BetaFunctionTool]:
    from ..kv.engine import Additions

    @beta_tool
    def get_kv_rules() -> str:
        """Правила АВ (Решение ДРБ-УРСП-125/2019 и калькулятор АВ): базовые ставки по видам, шкала КАСКО по группам филиалов, Доп.АВ1–3."""
        return _json(service.rules_summary())

    @beta_tool
    def get_kv_cabinet(agent: str, quarter: str) -> str:
        """Расчёт АВ агента: ставки по видам (база + Доп.АВ1/2/3) квартала и следующего, показатели, доход по сценариям, план.

        Args:
            agent: Имя агента.
            quarter: Квартал расчёта в формате ГГГГQN, например 2026Q3.
        """
        return _json(kv_brief(service.cabinet(agent, quarter)))

    @beta_tool
    def simulate_kv(agent: str, quarter: str, extra_kasko: float = 0, extra_priority: float = 0, prolonged: int | None = None) -> str:
        """Что изменится, если в открытом квартале допродать или пролонгировать: ставки следующего квартала и доход
        (эффект продаж и эффект ставки отдельно).

        Args:
            agent: Имя агента.
            quarter: Открытый квартал, ГГГГQN.
            extra_kasko: Доп. сборы КАСКО, ₽.
            extra_priority: Доп. сборы приоритетных видов (ИФЛ, КИС, ВЗР, АвтоНС, НСиБ и др.), ₽.
            prolonged: Сколько договоров всего будет пролонгировано в квартале, шт.
        """
        additions = Additions(kasko=max(0.0, extra_kasko), priority=max(0.0, extra_priority),
                              prolonged=None if prolonged is None else max(0, prolonged))
        result = service.simulate(agent, quarter, additions)
        return _json({k: result[k] for k in ("additions", "effects", "contracts")} | {
            "baselineRates": result["baseline"]["nextRate"]["components"],
            "scenarioRates": result["scenario"]["nextRate"]["components"],
            "baselineIncomeNext": result["baseline"]["incomeNext"]["kv"],
            "scenarioIncomeNext": result["scenario"]["incomeNext"]["kv"],
        })

    return [get_kv_rules, get_kv_cabinet, simulate_kv]
