"""Agency reward (АВ) for a quarter T, by the rules of Решение ДРБ-УРСП-125/2019 and the АВ calculator.

R = T−1 is the reporting quarter, P = T−2 the one before it.
  base:   КАСКО — scale by branch group on R's voluntary (ДВС) collections, 25% for newcomers; other lines fixed
  Доп.АВ1 dynamics     = ДВС_R / max(ДВС_P, floor) − 1, scale by R's quarter number
  Доп.АВ2 penetration  = (ДВС_R − КАСКО_R) / ДВС_R  > threshold
  Доп.АВ3 prolongation = prolonged / due in R      ≥ threshold
  total per line = base + Доп.АВ1 + Доп.АВ2 + Доп.АВ3; КАСКО capped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import pandas as pd

from .rules import RuleVersion, band_value

QUARTER_PATTERN = re.compile(r"^(\d{4})Q([1-4])$")
SCENARIOS = ("base", "cautious", "optimistic")
SCENARIO_TITLES = {"base": "Базовый", "cautious": "Осторожный", "optimistic": "Оптимистичный"}
KIND_TITLES = {"fact": "факт", "nowcast": "факт на дату + прогноз", "forecast": "прогноз"}


class KvDataError(ValueError):
    """Requested agent/quarter is not in the data; message is safe to show."""


def parse_quarter(text: str) -> pd.Period:
    m = QUARTER_PATTERN.match(text or "")
    if not m:
        raise KvDataError("Квартал должен быть в формате ГГГГQN, например 2026Q4")
    return pd.Period(year=int(m[1]), quarter=int(m[2]), freq="Q")


def label(q: pd.Period) -> str:
    return f"{q.year}Q{q.quarter}"


@dataclass(frozen=True)
class Additions:
    """What the agent plans in the open quarter. A priority sale raises ДВС volume AND penetration."""

    kasko: float = 0.0
    priority: float = 0.0
    prolonged: int | None = None  # planned prolonged contracts in the open quarter (total)
    due: int | None = None  # override of the estimated contracts due for prolongation
    exclude: frozenset[str] = frozenset()  # lines that get no share of the priority sales

    def has_inputs(self) -> bool:
        return self.kasko > 0 or self.priority > 0 or self.prolonged is not None or self.due is not None


NO_ADDITIONS = Additions()


class KvInputs:
    def __init__(self, data: dict) -> None:
        self.data = data
        self.as_of: str = data["asOf"]
        self.current = parse_quarter(data["currentQuarter"])
        self.agents: list[str] = data["agents"]

    def check_agent(self, agent: str) -> None:
        if agent not in self.data["quarters"]:
            raise KvDataError(f"Неизвестный агент «{agent}»")

    def info(self, agent: str) -> dict:
        self.check_agent(agent)
        return self.data["agentInfo"][agent]

    def quarter(self, agent: str, q: pd.Period) -> dict:
        self.check_agent(agent)
        entry = self.data["quarters"][agent].get(label(q))
        if entry is None:
            raise KvDataError(f"Нет данных по агенту за {label(q)}")
        return entry

    def has_quarter(self, agent: str, q: pd.Period) -> bool:
        return label(q) in self.data["quarters"].get(agent, {})


def scenario_delta(rule: RuleVersion, scenario: str) -> float:
    if scenario not in SCENARIOS:
        raise KvDataError(f"Неизвестный сценарий «{scenario}»")
    return {"base": 0.0, "cautious": rule.scenarios.cautious, "optimistic": rule.scenarios.optimistic}[scenario]


def is_newcomer(first_ad: str | None, quarter: pd.Period) -> bool:
    """25% КАСКО: to the end of the signing quarter if ≥2 full months remain in it, else to the end of the next one."""
    if not first_ad:
        return False
    signed = date.fromisoformat(first_ad)
    sq = pd.Period(signed, freq="Q")
    end_month = sq.end_time.month
    full_months = (end_month - signed.month) + (1 if signed.day == 1 else 0)
    last = sq if full_months >= 2 else sq + 1
    return sq <= quarter <= last


def amounts(rule: RuleVersion, entry: dict, delta: float, additions: Additions | None) -> dict[str, float]:
    """Collections by line; the forecast part is scaled by the scenario, planned sales are added."""
    out = {line: v["toDate"] + v["remainder"] * (1 + delta) for line, v in entry["lines"].items()}
    if additions is None:
        return out
    kasko = rule.kasko.line
    out[kasko] = out.get(kasko, 0.0) + additions.kasko
    if additions.priority > 0:
        mix = {line: max(0.0, a) for line, a in out.items()
               if rule.line(line).priority and rule.line(line).base_rate and line not in additions.exclude}
        total = sum(mix.values())
        if total <= 0:  # no priority history: book it to the first rated priority line
            first = next(name for name, r in rule.lines.items()
                         if r.priority and r.base_rate and name not in additions.exclude)
            mix, total = {first: 1.0}, 1.0
        for line, weight in mix.items():
            out[line] = out.get(line, 0.0) + additions.priority * weight / total
    return out


def _due_and_done(entry: dict, rule) -> tuple[int, int | None]:
    """Contracts due / prolonged that count for Доп.АВ3 (by line and product when the data has the split)."""
    by_due = entry.get("prolongDueByProduct")
    if rule is None or by_due is None:
        return entry["prolongDue"], entry["prolonged"]

    def total(by: dict) -> int:
        return sum(n for line, products in by.items() for product, n in products.items() if rule.counts(line, product))

    by_done = entry.get("prolongedByProduct")
    return total(by_due), None if by_done is None else total(by_done)


def prolongation(entry: dict, additions: Additions | None, rule=None) -> dict:
    due, prolonged = _due_and_done(entry, rule)
    estimated = entry.get("prolongDueEstimated", False)
    if additions is not None and additions.due is not None:
        due, estimated = additions.due, False
    if additions is not None and additions.prolonged is not None:
        prolonged = min(additions.prolonged, due) if due else additions.prolonged
    rate = None if prolonged is None or not due else prolonged / due
    missing = (
        None if rate is not None
        else "нет договоров к пролонгации" if prolonged is not None and not due
        else "в данных нет результата пролонгации" if entry["kind"] == "fact"
        else "результат пролонгации ещё неизвестен"
    )
    return {"due": due, "prolonged": prolonged, "rate": rate, "dueEstimated": estimated, "missing": missing,
            "lines": None if rule is None else rule.lines}


def evaluate(
    rule: RuleVersion,
    info: dict,
    quarter: pd.Period,
    reporting: dict,
    previous: dict,
    delta: float = 0.0,
    additions: Additions | None = None,
) -> dict:
    """АВ rates for quarter T from its reporting quarter R (with planned additions) and P."""
    r_q, p_q = quarter - 1, quarter - 2
    r_amounts = amounts(rule, reporting, delta, additions)
    p_amounts = amounts(rule, previous, delta, None)
    dvs_r, dvs_p = sum(r_amounts.values()), sum(p_amounts.values())
    prio_r = sum(a for line, a in r_amounts.items() if rule.line(line).priority)

    floor = rule.dynamics.floor_base
    dyn_base = max(dvs_p, floor)
    dynamics = 0.0 if dvs_r == 0 and dvs_p == 0 else dvs_r / dyn_base - 1
    dyn_bands = rule.dynamics.bands_by_reporting_quarter[str(r_q.quarter)]
    d1, d1_index = band_value(dyn_bands, dynamics)

    penetration = None if dvs_r <= 0 else prio_r / dvs_r
    d2 = rule.penetration.bonus if penetration is not None and penetration > rule.penetration.above else 0.0

    prol = prolongation(reporting, additions, rule.prolongation)
    d3 = rule.prolongation.bonus if prol["rate"] is not None and prol["rate"] >= rule.prolongation.at_least else 0.0

    group = info.get("group")
    scale_group = rule.kasko.scale_group(group)
    newcomer = is_newcomer(info.get("firstAd"), quarter)
    scale = rule.kasko.scale_by_group.get(scale_group or "")
    if newcomer:
        kasko_base, scale_index = rule.kasko.newcomer_rate, None
    elif scale is None:
        kasko_base, scale_index = None, None
    else:
        kasko_base, scale_index = band_value(scale, dvs_r)

    lines = sorted(set(rule.lines) | set(r_amounts))
    rates = []
    for line in lines:
        lr = rule.line(line)
        base = kasko_base if line == rule.kasko.line else lr.base_rate
        bonus = d1 + d2 + d3
        if lr.max_bonus is not None:  # some lines cap the sum of Доп.АВ1–3
            bonus = min(bonus, lr.max_bonus)
        total = None if base is None else base + bonus
        if total is not None and line == rule.kasko.line:
            total = min(total, rule.kasko.cap)
        rates.append(
            {
                "line": line,
                "title": lr.title,
                "base": base,
                "d1": d1, "d2": d2, "d3": d3,
                "total": total,
                "capped": total is not None and total < base + d1 + d2 + d3 - 1e-12,
                "note": lr.note if base is not None or line != rule.kasko.line else "нет группы филиала в правилах",
            }
        )

    return {
        "quarter": label(quarter),
        "reporting": label(r_q),
        "previous": label(p_q),
        "metrics": {
            "dvs": dvs_r,
            "dvsPrevious": dvs_p,
            "priority": prio_r,
            "dynamics": dynamics,
            "dynamicsBase": dyn_base,
            "dynamicsFloorApplied": dvs_p < floor,
            "penetration": penetration,
            "prolongation": prol,
        },
        "components": {
            "kaskoBase": {"rate": kasko_base, "newcomer": newcomer, "group": group, "scaleGroup": scale_group,
                          "scaleIndex": scale_index,
                          "scale": scale},
            "d1": {"value": d1, "bandIndex": d1_index, "bands": dyn_bands},
            "d2": {"value": d2, "above": rule.penetration.above, "bonus": rule.penetration.bonus},
            "d3": {"value": d3, "atLeast": rule.prolongation.at_least, "bonus": rule.prolongation.bonus},
        },
        "rates": rates,
        "amountsReporting": r_amounts,
    }


def income(rule: RuleVersion, rates: list[dict], line_amounts: dict[str, float]) -> dict:
    """АВ = Σ max(0, collections of the line) × the line's total rate; lines without a rate are listed apart."""
    by_rate = {r["line"]: r for r in rates}
    rows, unrated = [], []
    for line, amount in sorted(line_amounts.items()):
        rate = by_rate.get(line, {}).get("total")
        base = max(0.0, amount)
        if rate is None:
            if base > 0:
                unrated.append({"line": line, "title": rule.line(line).title, "amount": base})
            continue
        rows.append({"line": line, "title": rule.line(line).title, "base": base, "rate": rate, "kv": base * rate,
                     "zeroBase": amount <= 0})
    total_base = sum(r["base"] for r in rows)
    total_kv = sum(r["kv"] for r in rows)
    return {
        "lines": rows,
        "unrated": unrated,
        "base": total_base,
        "kv": total_kv,
        "effectiveRate": None if total_base <= 0 else total_kv / total_base,
        "effectiveRateNote": "эффективная ставка = сумма АВ по видам ÷ сборы видов, для которых ставка задана",
    }
