"""АВ service: rates, income, cabinet and «what if» — the single entry point for the API and the agents."""

from __future__ import annotations

import math
import threading

import pandas as pd

from . import planner
from .engine import (
    KIND_TITLES,
    NO_ADDITIONS,
    SCENARIO_TITLES,
    SCENARIOS,
    Additions,
    KvDataError,
    KvInputs,
    amounts,
    evaluate,
    income,
    is_newcomer,
    label,
    parse_quarter,
    scenario_delta,
)
from .rules import RuleVersion, RulesCache

CACHE_LIMIT = 512


class KvService:
    def __init__(self, inputs: KvInputs, rules: RulesCache) -> None:
        self.inputs = inputs
        self.rules = rules
        self._cache: dict[tuple, dict] = {}
        self._lock = threading.Lock()

    # --- rules ---------------------------------------------------------------------------------
    def rule_for(self, quarter: pd.Period) -> RuleVersion:
        book, _ = self.rules.get()
        return book.for_quarter(quarter)

    def rules_summary(self) -> dict:
        book, _ = self.rules.get()
        return {"versions": [v.model_dump(mode="json") for v in book.versions]}

    @staticmethod
    def rule_info(rule: RuleVersion) -> dict:
        return {
            "id": rule.id,
            "status": rule.status,
            "title": rule.title,
            "source": rule.source,
            "validFrom": rule.valid_from.isoformat(),
            "validTo": None if rule.valid_to is None else rule.valid_to.isoformat(),
        }

    # --- options -------------------------------------------------------------------------------
    def rate_quarters(self) -> list[str]:
        """Cabinet quarters T: T−2 is in the data and T is not later than the open quarter."""
        data = self.inputs.data["quarters"]
        first = min(parse_quarter(q) for quarters in data.values() for q in quarters)
        out, q = [], first + 2
        while q <= self.inputs.current:
            out.append(label(q))
            q += 1
        return out

    def options(self) -> dict:
        d = self.inputs.data
        return {
            "agents": self.inputs.agents,
            "quarters": self.rate_quarters(),
            "currentQuarter": label(self.inputs.current),
            "asOf": self.inputs.as_of,
            "source": d["source"],
            "currentQuarterHasData": d["currentQuarterHasData"],
        }

    def check_quarter(self, quarter_label: str) -> pd.Period:
        q = parse_quarter(quarter_label)
        available = self.rate_quarters()
        if quarter_label not in available:
            raise KvDataError(f"Квартал {quarter_label} недоступен. Доступны: {', '.join(available)}")
        return q

    def check_agent(self, agent: str, quarter: pd.Period) -> dict:
        info = self.inputs.info(agent)
        if info["branch"].upper() in {b.upper() for b in self.rule_for(quarter).excluded_branches}:
            raise KvDataError(f"Положение об АВ не применяется к филиалу «{info['branch']}»")
        return info

    # --- core calculations ---------------------------------------------------------------------
    def rate(self, agent: str, quarter: pd.Period, scenario: str = "base", additions: Additions = NO_ADDITIONS) -> dict:
        """АВ rates of quarter T from the reporting quarter R = T−1 and P = T−2."""
        rule = self.rule_for(quarter)
        info = self.check_agent(agent, quarter)
        r_q, p_q = quarter - 1, quarter - 2
        if additions.has_inputs() and r_q != self.inputs.current:
            raise KvDataError(
                f"Ставку {label(quarter)} определяет завершённый квартал {label(r_q)} — новые продажи на неё не влияют"
            )
        reporting, previous = self.inputs.quarter(agent, r_q), self.inputs.quarter(agent, p_q)
        result = evaluate(rule, info, quarter, reporting, previous, scenario_delta(rule, scenario),
                          additions if additions.has_inputs() else None)
        all_fact = reporting["kind"] == previous["kind"] == "fact"
        return {
            **result,
            "rule": self.rule_info(rule),
            "basis": [{"quarter": label(q), "kind": e["kind"], "kindTitle": KIND_TITLES[e["kind"]]}
                      for q, e in ((r_q, reporting), (p_q, previous))],
            "status": "fact" if all_fact else "forecast",
            "statusTitle": "по фактам" if all_fact else f"прогноз: {label(r_q)} ещё не завершён",
        }

    def income(self, agent: str, quarter: pd.Period, scenario: str = "base", rate: dict | None = None,
               additions: Additions = NO_ADDITIONS) -> dict:
        """АВ for the sales of quarter T at T's rates."""
        rule = self.rule_for(quarter)
        rate = rate or self.rate(agent, quarter, scenario)
        entry = self.inputs.quarter(agent, quarter)
        extra = additions if additions.has_inputs() and quarter == self.inputs.current else None
        result = income(rule, rate["rates"], amounts(rule, entry, scenario_delta(rule, scenario), extra))
        return {
            "quarter": label(quarter),
            "scenario": scenario,
            "scenarioTitle": SCENARIO_TITLES[scenario],
            "kind": entry["kind"],
            "kindTitle": KIND_TITLES[entry["kind"]],
            **result,
        }

    def effects(self, agent: str, nxt: pd.Period, additions: Additions, before: dict, after: dict) -> dict:
        """Sales effect: extra sales of the open quarter × its rates. Rate effect: forecast base of `nxt` × rate change."""
        open_q = nxt - 1
        now_rate = self.rate(agent, open_q)
        sales = self.income(agent, open_q, rate=now_rate, additions=additions)["kv"] - self.income(agent, open_q, rate=now_rate)["kv"]
        rate_eff = self.income(agent, nxt, rate=after)["kv"] - self.income(agent, nxt, rate=before)["kv"]
        return {
            "salesEffect": sales,
            "salesEffectNote": f"АВ с доп. продаж {label(open_q)} по ставкам {label(open_q)}",
            "rateEffect": rate_eff,
            "rateEffectNote": f"рост АВ {label(nxt)} от новых ставок при той же прогнозной базе",
            "total": sales + rate_eff,
        }

    def contracts_estimate(self, agent: str, additions: Additions) -> dict:
        """Contract counts from the average collections per contract over fact quarters — an estimate only."""
        rule = self.rule_for(self.inputs.current)
        sums, counts = {"kasko": 0.0, "priority": 0.0}, {"kasko": 0, "priority": 0}
        for entry in self.inputs.data["quarters"][agent].values():
            if entry["kind"] != "fact":
                continue
            for line, v in entry["lines"].items():
                key = "kasko" if line == rule.kasko.line else "priority"
                if v["toDate"] > 0:
                    sums[key] += v["toDate"]
                    counts[key] += v["contracts"]
        out = {}
        for key, amount in (("kasko", additions.kasko), ("priority", additions.priority)):
            check = sums[key] / counts[key] if counts[key] else None
            out[key] = {"avgCheck": check, "contracts": None if not check or amount <= 0 else math.ceil(amount / check)}
        out["note"] = "оценка: сборы ÷ число договоров по завершённым кварталам"
        return out

    # --- cabinet -------------------------------------------------------------------------------
    def cabinet(self, agent: str, quarter_label: str) -> dict:
        quarter = self.check_quarter(quarter_label)
        info = self.check_agent(agent, quarter)
        _, mtime = self.rules.get()
        key = ("cabinet", agent, quarter_label, mtime)
        with self._lock:
            if key in self._cache:
                return self._cache[key]

        nxt = quarter + 1
        current_rate = self.rate(agent, quarter)
        next_rates = {s: self.rate(agent, nxt, s) for s in SCENARIOS}
        rule = self.rule_for(nxt)
        result = {
            "agent": agent,
            "agentInfo": {**info, "newcomer": is_newcomer(info.get("firstAd"), quarter)},
            "quarter": quarter_label,
            "nextQuarter": label(nxt),
            "asOf": self.inputs.as_of,
            "source": self.inputs.data["source"],
            "currentRate": current_rate,
            "nextRate": next_rates["base"],
            "nextRateByScenario": {s: [{"line": x["line"], "total": x["total"]} for x in r["rates"]] for s, r in next_rates.items()},
            "income": {
                "current": {s: self.income(agent, quarter, s, rate=current_rate) for s in SCENARIOS},
                "next": {s: self.income(agent, nxt, s, rate=next_rates[s]) for s in SCENARIOS},
            },
            "scenarioNote": rule.scenarios.note,
            "plan": planner.plan(self, agent, nxt),
            "assumptions": self.assumptions(rule, current_rate, next_rates["base"]),
        }
        with self._lock:
            if len(self._cache) > CACHE_LIMIT:
                self._cache.clear()
            self._cache[key] = result
        return result

    def assumptions(self, rule: RuleVersion, current: dict, nxt: dict) -> list[str]:
        d = self.inputs.data
        fq = d["forecastQuality"]
        chosen = fq["chosen"]
        unrated = ", ".join(lr.title for lr in rule.lines.values() if lr.base_rate is None and lr.title != "КАСКО")
        items = [
            f"Правила: {rule.title}.",
            f"Ставка квартала считается по отчётному (предыдущему) кварталу и кварталу перед ним: "
            f"{current['quarter']} — по {current['reporting']} и {current['previous']}, "
            f"{nxt['quarter']} — по {nxt['reporting']} и {nxt['previous']}.",
            f"Данные: {d['source']} (синтетический обезличенный набор), дата расчёта {d['asOf']}; "
            f"записи после неё не используются (исключено {d['rowsAfterAsOfExcluded']}).",
            f"Открытый квартал {label(self.inputs.current)}: договоры, заключённые по дату расчёта, + прогноз остатка "
            f"(прогноз квартала × доля оставшихся дней, {_pct(1 - d['elapsedShare'])}).",
            f"Прогноз сборов — «{chosen['title']}»; ошибка на бэктесте {_pct(chosen['wape'])}. {fq['note']}",
            "Пролонгация: число договоров к пролонгации — из листа «пролонг»; "
            + ("результаты пролонгации есть в данных." if d["prolongationOutcomesAvailable"]
               else "результатов пролонгации в данных нет — Доп.АВ3 не начисляется, пока его не задать в калькуляторе."),
            f"Без ставки АВ: {unrated} — их сборы входят в ДВС, но АВ по ним не считается.",
            "Границы шкал — «меньше»; Доп.АВ2 — доля > 9,9%, Доп.АВ3 — ≥ 69,99%, как в калькуляторе АВ.",
            rule.scenarios.note,
        ]
        if rule.kasko.group_aliases_note:
            items.append(rule.kasko.group_aliases_note)
        kis = rule.lines.get("КИС")
        if kis and kis.note:
            items.append(f"КИС: {kis.note}.")
        return items

    # --- what if -------------------------------------------------------------------------------
    def simulate(self, agent: str, quarter_label: str, additions: Additions) -> dict:
        """Base forecast vs a plan of extra sales / prolongations in the open quarter."""
        quarter = self.check_quarter(quarter_label)
        if quarter != self.inputs.current:
            raise KvDataError(f"Сценарии считаются для открытого квартала {label(self.inputs.current)}")
        nxt = quarter + 1
        before = self.rate(agent, nxt)
        after = self.rate(agent, nxt, additions=additions)
        now_rate = self.rate(agent, quarter)
        return {
            "agent": agent,
            "quarter": quarter_label,
            "nextQuarter": label(nxt),
            "additions": {"kasko": additions.kasko, "priority": additions.priority,
                          "prolonged": additions.prolonged, "due": additions.due},
            "baseline": {"nextRate": _brief(before),
                         "incomeCurrent": self.income(agent, quarter, rate=now_rate),
                         "incomeNext": self.income(agent, nxt, rate=before)},
            "scenario": {"nextRate": _brief(after),
                         "incomeCurrent": self.income(agent, quarter, rate=now_rate, additions=additions),
                         "incomeNext": self.income(agent, nxt, rate=after)},
            "contracts": self.contracts_estimate(agent, additions),
            "effects": self.effects(agent, nxt, additions, before, after),
        }


def _brief(rate: dict) -> dict:
    return {
        "quarter": rate["quarter"],
        "rates": rate["rates"],
        "components": planner.component_values(rate),
        "metrics": rate["metrics"],
        "status": rate["status"],
    }


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"
