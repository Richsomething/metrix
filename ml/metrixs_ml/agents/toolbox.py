"""Deterministic data access for the agents.

Every number an agent may quote — plan, fact, bonus, what-if, required fact — is computed here
from the model artifacts and the bonus config. The LLM never does arithmetic on money.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..bonus import BonusConfig, calculate_bonus

QUARTER_PATTERN = re.compile(r"^\d{4}Q[1-4]$")
# Illustrative bonus levels for next-quarter goals; filtered by the configured cap.
BONUS_TARGETS = (10_000.0, 30_000.0, 50_000.0)
BASIS_NOTE = (
    "В выгрузке нет утверждённых планов, поэтому премия считается против рекомендуемого плана на основе "
    "прогноза — это допущение демонстрации, а не утверждённое правило."
)


class ToolboxError(ValueError):
    """Bad agent/quarter or data not available; message is safe to show to the user and to the LLM."""


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 2)


@dataclass(frozen=True)
class Toolbox:
    plans: tuple[dict, ...]
    metrics: dict
    config: BonusConfig

    def agents(self) -> list[str]:
        return list(self.metrics["agents"])

    def _check_agent(self, agent: str) -> None:
        if agent not in self.metrics["agents"]:
            raise ToolboxError(f"Неизвестный агент «{agent}». Доступные: {', '.join(self.agents())}")

    def _row(self, agent: str, quarter: str) -> dict:
        self._check_agent(agent)
        if not QUARTER_PATTERN.match(quarter):
            raise ToolboxError("Квартал должен быть в формате ГГГГQN, например 2026Q3")
        row = next((r for r in self.plans if r["agent"] == agent and r["quarter"] == quarter), None)
        if row is None:
            available = ", ".join(r["quarter"] for r in self.plans if r["agent"] == agent)
            raise ToolboxError(f"Нет плана для {agent} за {quarter}. Есть кварталы: {available}")
        return row

    def history(self, agent: str) -> list[dict]:
        self._check_agent(agent)
        rows = []
        for r in (r for r in self.plans if r["agent"] == agent):
            bonus = None if r["isForecast"] else self.bonus(agent, r["quarter"])
            rows.append(
                {
                    "quarter": r["quarter"],
                    "isForecast": r["isForecast"],
                    "recommendedPlan": r["recommendedPlan"],
                    "fact": r["fact"],
                    "completionPct": None if bonus is None else bonus["completionPct"],
                    "bonus": None if bonus is None else bonus["amount"],
                    "refundSharePct": None if r["refundShare"] is None else round(r["refundShare"] * 100, 2),
                }
            )
        return rows

    def plan_explanation(self, agent: str, quarter: str) -> dict:
        row = self._row(agent, quarter)
        return {"agent": agent, "quarter": quarter, "recommendedPlan": row["recommendedPlan"], "contributions": row["contributions"]}

    def model_quality(self) -> dict:
        scores = [
            {"model": s["title"], "wapePct": round(s["wape"] * 100, 4), "biasPct": round(s["bias"] * 100, 4)}
            for s in self.metrics["scores"]
        ]
        chosen = next((s["title"] for s in self.metrics["scores"] if s["name"] == self.metrics["chosen"]), None)
        return {
            "chosenModel": chosen,
            "backtest": scores,
            "plannedQuarters": self.metrics.get("plannedQuarters", []),
            "forecastQuarter": self.metrics.get("forecastQuarter"),
            "note": (
                "WAPE — средняя ошибка рекомендуемого плана к факту на кварталах, которые модель не видела при "
                "обучении. Результат получен на синтетическом наборе; на реальных данных точность не установлена."
            ),
            "asOf": self.metrics.get("asOf"),
            "futureRowsExcluded": self.metrics.get("futureRowsExcluded"),
        }

    def _bonus_for(self, plan: float, fact: float, refund_share: float) -> dict:
        result = calculate_bonus(plan, fact, refund_share, self.config)
        return {
            "recommendedPlan": _round(plan),
            "fact": _round(fact),
            "completionPct": round(result.completion * 100, 2),
            "bonusThreshold": _round(plan * (1 + self.config.threshold)),
            "overperformance": _round(result.overperformance),
            "amount": result.amount,
            "capped": result.capped,
            "refundPenalized": result.refund_penalized,
        }

    def bonus(self, agent: str, quarter: str) -> dict:
        row = self._row(agent, quarter)
        if row["isForecast"]:
            raise ToolboxError(f"{quarter} — прогнозный квартал, факта ещё нет. Используйте расчёт «что если».")
        return {
            "agent": agent,
            "quarter": quarter,
            "kind": "completed",
            "basis": BASIS_NOTE,
            **self._bonus_for(row["recommendedPlan"], row["fact"], row["refundShare"] or 0.0),
        }

    def what_if(self, agent: str, quarter: str, fact: float) -> dict:
        if fact < 0:
            raise ToolboxError("Сборы не могут быть отрицательными")
        row = self._row(agent, quarter)
        return {
            "agent": agent,
            "quarter": quarter,
            "kind": "scenario",
            "hypothetical": True,
            **self._bonus_for(row["recommendedPlan"], fact, 0.0),
        }

    def required_fact(self, agent: str, quarter: str, target_bonus: float) -> dict:
        """Fact needed for `target_bonus`, assuming refunds stay within the allowed share."""
        row = self._row(agent, quarter)
        if target_bonus <= 0:
            raise ToolboxError("Целевая премия должна быть положительной")
        if target_bonus > self.config.cap_per_quarter:
            raise ToolboxError(f"Премия за квартал ограничена {self.config.cap_per_quarter:,.0f}")
        if self.config.rate == 0:
            raise ToolboxError("Ставка премии равна 0 — премия недостижима")

        threshold = row["recommendedPlan"] * (1 + self.config.threshold)
        fact = threshold + target_bonus / self.config.rate
        return {
            "agent": agent,
            "quarter": quarter,
            "targetBonus": _round(target_bonus),
            "recommendedPlan": row["recommendedPlan"],
            "requiredFact": _round(fact),
            "requiredCompletionPct": round(fact / row["recommendedPlan"] * 100, 2),
            "condition": f"доля возвратов не выше {self.config.max_refund_share:.0%}",
        }

    def bonus_rules(self) -> dict:
        c = self.config
        return {
            "formula": "премия = min(потолок, ставка × max(0, факт − план × (1 + порог)))",
            "ratePct": c.rate * 100,
            "thresholdPct": c.threshold * 100,
            "capPerQuarter": c.cap_per_quarter,
            "maxRefundSharePct": c.max_refund_share * 100,
            "refundPenaltyMultiplier": c.refund_penalty,
        }

    def review_facts(self, agent: str, quarter: str) -> dict:
        """Everything the review agents need about one agent-quarter, computed up front."""
        bonus = self.bonus(agent, quarter)
        forecast = next((r for r in self.plans if r["agent"] == agent and r["isForecast"]), None)
        targets = []
        if forecast is not None:
            targets = [
                self.required_fact(agent, forecast["quarter"], t)
                for t in BONUS_TARGETS
                if t <= self.config.cap_per_quarter
            ]
        return {
            "bonus": bonus,
            "rules": self.bonus_rules(),
            "history": self.history(agent),
            "planExplanation": self.plan_explanation(agent, quarter)["contributions"],
            "nextQuarter": None
            if forecast is None
            else {
                "quarter": forecast["quarter"],
                "recommendedPlan": forecast["recommendedPlan"],
                "note": "Квартал не завершён: факта и премии нет, цели ниже — сценарии «что если».",
            },
            "nextQuarterTargets": targets,
            "dataNote": self.metrics.get("datasetNote"),
            "asOf": self.metrics.get("asOf"),
        }
