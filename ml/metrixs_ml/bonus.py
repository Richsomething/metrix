"""Bonus formula on top of the model plan. Parameters live in config/bonus.json, not in the model."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class BonusConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rate: float = Field(ge=0, le=1, description="Доля от перевыполнения, идущая в премию")
    threshold: float = Field(ge=0, le=1, description="Перевыполнение считается от плана × (1 + threshold)")
    cap_per_quarter: float = Field(ge=0, description="Максимальная премия агента за квартал")
    max_refund_share: float = Field(ge=0, le=1, description="Допустимая доля возвратов в квартале")
    refund_penalty: float = Field(ge=0, le=1, description="Множитель премии при превышении доли возвратов")


class BonusResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    completion: float
    overperformance: float
    amount: float
    capped: bool
    refund_penalized: bool


def load_bonus_config(path: Path) -> BonusConfig:
    try:
        return BonusConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Не найден конфиг премий: {path}") from exc


def calculate_bonus(plan: float, fact: float, refund_share: float, config: BonusConfig) -> BonusResult:
    """bonus = min(cap, rate × max(0, fact − plan × (1 + threshold))), reduced if refunds are too high."""
    if plan <= 0:
        raise ValueError("План должен быть положительным")

    target = plan * (1 + config.threshold)
    overperformance = max(0.0, fact - target)
    raw_amount = config.rate * overperformance
    capped = raw_amount > config.cap_per_quarter
    amount = min(raw_amount, config.cap_per_quarter)

    refund_penalized = refund_share > config.max_refund_share
    if refund_penalized:
        amount *= config.refund_penalty

    return BonusResult(
        completion=fact / plan,
        overperformance=overperformance,
        amount=round(amount, 2),
        capped=capped,
        refund_penalized=refund_penalized,
    )


CURVE_POINTS = 60
CURVE_START = 0.9  # curve starts at 90 % of the bonus threshold
CURVE_PAST_CAP = 1.25  # and ends 25 % past the point where the cap is reached


class CurvePoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    fact: float
    bonus: float
    bonus_high_refunds: float


def bonus_curve(plan: float, config: BonusConfig) -> list[CurvePoint]:
    """Bonus as a function of quarter collections, with the formula's kinks (threshold, cap) included exactly."""
    target = plan * (1 + config.threshold)
    to_cap = config.cap_per_quarter / config.rate if config.rate > 0 else plan * 0.5
    start, end = target * CURVE_START, target + to_cap * CURVE_PAST_CAP
    step = (end - start) / (CURVE_POINTS - 1)
    facts = sorted({round(start + i * step, 2) for i in range(CURVE_POINTS)} | {round(target, 2), round(target + to_cap, 2)})
    high_refunds = min(1.0, config.max_refund_share + DEMO_REFUND_STEP)
    return [
        CurvePoint(
            fact=fact,
            bonus=calculate_bonus(plan, fact, 0.0, config).amount,
            bonus_high_refunds=calculate_bonus(plan, fact, high_refunds, config).amount,
        )
        for fact in facts
    ]


# Demo offsets only — they pick illustrative facts around the configured thresholds, they are not rules.
DEMO_SHORTFALL = 0.05  # fact 5 % below the bonus threshold
DEMO_REFUND_STEP = 0.01  # refund share 1 p.p. above the allowed share


class Scenario(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    title: str
    fact: float
    refund_share: float
    result: BonusResult


def demo_scenarios(plan: float, config: BonusConfig) -> list[Scenario]:
    """Illustrative facts at and around every boundary of the configured rules."""
    target = plan * (1 + config.threshold)
    cases: list[tuple[str, str, float, float]] = [
        ("shortfall", "Недовыполнение", target * (1 - DEMO_SHORTFALL), 0.0),
        ("at_threshold", "Ровно порог плана — граница, премии ещё нет", target, 0.0),
    ]
    if config.rate > 0 and config.cap_per_quarter > 0:
        to_cap = config.cap_per_quarter / config.rate  # overperformance that reaches the cap exactly
        refunds_over = min(1.0, config.max_refund_share + DEMO_REFUND_STEP)
        cases += [
            ("over", "Перевыполнение — половина потолка", target + to_cap / 2, 0.0),
            ("at_cap", "Ровно потолок — граница", target + to_cap, 0.0),
            ("above_cap", "Выше потолка — премия ограничена", target + to_cap * 2, 0.0),
            ("refunds_at_limit", "Возвраты ровно на допустимом уровне — без снижения", target + to_cap / 2, config.max_refund_share),
            ("refunds_over_limit", "Возвраты выше допустимого — премия снижается", target + to_cap / 2, refunds_over),
        ]
    return [
        Scenario(key=key, title=title, fact=round(fact, 2), refund_share=share, result=calculate_bonus(plan, fact, share, config))
        for key, title, fact, share in cases
    ]
