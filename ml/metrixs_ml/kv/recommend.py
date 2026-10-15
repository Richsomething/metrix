"""Main-page advice for the open quarter, built around the agent's portfolio.

Portfolio first: the agent's contracts that end this quarter (the products he sells) are what to prolong (Доп.АВ3),
and every renewal is a contact where a priority product can be offered (Доп.АВ2 and ДВС volume). The sales advice splits the planner's
priority amount over the lines the agent already sells. Every amount comes from the rules engine.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import TYPE_CHECKING

from . import planner
from .engine import Additions, amounts, label

if TYPE_CHECKING:
    from .service import KvService

SALES_UNIT = 100_000.0
TOP_PRODUCTS = 3
HIDDEN_LINES = frozenset({"АВТО НС"})  # not recommended on the main page; still part of the rate calculation


def recommendations(service: "KvService", agent: str) -> dict:
    open_q = service.inputs.current
    nxt = open_q + 1
    service.check_agent(agent, open_q)
    rule = service.rule_for(nxt)
    rate_now = service.rate(agent, open_q)  # rates paid on this quarter's sales
    before = service.rate(agent, nxt)
    plan = planner.plan(service, agent, nxt)
    portfolio = _portfolio(service, agent, nxt, before)
    sell = _sell(service, agent, rate_now, plan, portfolio["needed"], before)
    both = Additions(kasko=sell["kasko"], priority=sell["priority"], prolonged=portfolio["needed"] or None,
                     exclude=HIDDEN_LINES)
    after = service.rate(agent, nxt, additions=both) if both.has_inputs() else None
    combined = service.effects(agent, nxt, both, before, after) if after else None
    income_now = service.income(agent, open_q, rate=rate_now)
    income_next = service.income(agent, nxt, rate=before)
    return {
        "agent": agent,
        "quarter": label(open_q),
        "nextQuarter": label(nxt),
        "asOf": service.inputs.as_of,
        "income": {
            "current": income_now["kv"],
            "next": income_next["kv"],
            "currentBase": income_now["base"],
            "nextBase": income_next["base"],
        },
        "rates": _line_rates(rate_now, before, after, income_now),
        "planComponents": {  # доплаты ставки следующего квартала без плана и с планом
            "before": planner.component_values(before),
            "after": planner.component_values(after) if after else None,
        },
        "portfolio": portfolio,
        "sell": sell,
        "planEffect": combined,  # selling and prolonging together, computed once (no double counting)
        "steps": plan.get("steps", []),
        "notes": [
            f"Ставки {label(open_q)} уже известны — по ним оплачиваются продажи этого квартала; "
            f"продажи и продления {label(open_q)} поднимают ставки {label(nxt)}.",
            rule.prolongation.note,
            "Число договоров — оценка по среднему чеку агента; суммы плана — наименьшие при продаже только приоритетных видов.",
        ],
    }


def _line_rates(rate_now: dict, before: dict, after: dict | None, income_now: dict) -> list[dict]:
    """Per line: this quarter's rate, next quarter's without and with the plan; biggest collections first."""
    nxt = {r["line"]: r for r in before["rates"]}
    planned = {r["line"]: r for r in after["rates"]} if after else {}
    share = {row["line"]: row["base"] for row in income_now["lines"]}
    rows = [
        {
            "line": r["line"],
            "title": r["title"],
            "base": r["base"],
            "current": r["total"],
            "next": nxt[r["line"]]["total"],
            "nextWithPlan": planned.get(r["line"], nxt[r["line"]])["total"],
            "cappedWithPlan": planned.get(r["line"], nxt[r["line"]])["capped"],
            # points added on top of the base by Доп.АВ1–3 with the plan, after the caps
            "addedWithPlan": (None if r["base"] is None or planned.get(r["line"], nxt[r["line"]])["total"] is None
                              else planned.get(r["line"], nxt[r["line"]])["total"] - planned.get(r["line"], nxt[r["line"]])["base"]),
            "collections": share.get(r["line"], 0.0),
        }
        for r in rate_now["rates"]
        if r["total"] is not None and r["line"] not in HIDDEN_LINES and share.get(r["line"], 0.0) > 0
    ]
    return sorted(rows, key=lambda r: -r["collections"])


def _portfolio(service: "KvService", agent: str, nxt, before: dict) -> dict:
    """Contracts of the prolongation lines that end in the open quarter, grouped by product."""
    rule = service.rule_for(nxt)
    lines = rule.prolongation.lines
    contracts = [c for c in service.inputs.data.get("prolongContracts", {}).get(agent, [])
                 if rule.prolongation.counts(c["line"], c["product"])]
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for c in contracts:
        groups[(c["line"], c["product"])].append(
            {"contract": c["contract"], "endAt": c["endAt"], "expired": c["endAt"] < service.inputs.as_of})
    prol = before["metrics"]["prolongation"]
    due = prol["due"]
    needed = math.ceil(rule.prolongation.at_least * due - 1e-9) if due else 0
    effects, gain = None, {}
    if needed:
        adds = Additions(prolonged=needed)
        after = service.rate(agent, nxt, additions=adds)
        effects, gain = service.effects(agent, nxt, adds, before, after), planner.rate_gain(before, after)
    return {
        "lines": lines,
        "due": due,
        "needed": needed,
        "atLeast": rule.prolongation.at_least,
        "bonus": rule.prolongation.bonus,
        "expired": sum(1 for c in contracts if c["endAt"] < service.inputs.as_of),
        "gain": gain,
        "effects": effects,
        "groups": sorted(
            ({"line": line, "title": rule.line(line).title, "product": product, "count": len(items), "contracts": items}
             for (line, product), items in groups.items()),
            key=lambda g: -g["count"],
        ),
    }


def _avg_checks(service: "KvService", agent: str) -> dict[str, float]:
    sums: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for entry in service.inputs.data["quarters"][agent].values():
        if entry["kind"] != "fact":
            continue
        for line, v in entry["lines"].items():
            if v["toDate"] > 0 and v["contracts"]:
                sums[line] += v["toDate"]
                counts[line] += v["contracts"]
    return {line: sums[line] / counts[line] for line in sums}


def _sell(service: "KvService", agent: str, rate_now: dict, plan: dict, renewals: int, before: dict) -> dict:
    """Rated lines with this quarter's rate, the planned priority amount split by the agent's mix, and products."""
    open_q = service.inputs.current
    rule = service.rule_for(open_q + 1)
    # priority lines only: they raise ДВС volume and the share of priority lines at once
    option = next((o for o in plan.get("options", []) if o["key"] == "priority"), None)
    kasko = option["kasko"] if option else 0.0
    priority = option["priority"] if option else 0.0
    total = kasko + priority
    entry = service.inputs.quarter(agent, open_q)
    base = amounts(rule, entry, 0.0, None)
    planned_sales = Additions(kasko=kasko, priority=priority, exclude=HIDDEN_LINES)
    split = {line: a - base.get(line, 0.0) for line, a in amounts(rule, entry, 0.0, planned_sales).items()}
    checks = _avg_checks(service, agent)
    mix = service.inputs.data.get("productMix", {}).get(agent, {})

    rows = []
    for r in rate_now["rates"]:
        if r["total"] is None or r["line"] in HIDDEN_LINES:
            continue
        line = r["line"]
        planned = max(0.0, split.get(line, 0.0))
        check = checks.get(line)
        rows.append({
            "line": line,
            "title": r["title"],
            "priority": rule.line(line).priority,
            "rate": r["total"],
            "kvPerUnit": SALES_UNIT * r["total"],
            "planAmount": round(planned, 2),
            "avgCheck": check,
            "planContracts": math.ceil(planned / check) if check and planned > 0 else None,
            "products": mix.get(line, [])[:TOP_PRODUCTS],
        })
    rows = [r for r in rows if r["products"]]  # lines the agent does not sell are not advised
    rows.sort(key=lambda r: (not r["priority"], -r["planAmount"], -r["rate"]))
    effects, components = None, None
    if total > 0:  # the planner's option also prolongs; sales alone are re-evaluated here
        after = service.rate(agent, open_q + 1, additions=planned_sales)
        effects = service.effects(agent, open_q + 1, planned_sales, before, after)
        components = planner.component_values(after)
    return {
        "unit": SALES_UNIT,
        "total": total,
        "kasko": kasko,
        "priority": priority,
        "mix": option["key"] if option else None,
        "perRenewal": total / renewals if total and renewals else None,
        "effects": effects,
        "componentsAfter": components,
        "rows": rows,
    }
