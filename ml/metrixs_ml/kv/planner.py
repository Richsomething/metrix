"""What to do in the open quarter R to raise the АВ rate of the next quarter N = R+1.

Planned sales: c — КАСКО, v — priority lines (all voluntary lines except КАСКО), k — prolonged contracts.
A priority sale raises ДВС volume (КАСКО scale, Доп.АВ1) AND penetration (Доп.АВ2); a КАСКО sale raises
volume but lowers penetration. So conditions are solved jointly, and every plan is re-checked by evaluate().
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .engine import Additions, label

if TYPE_CHECKING:
    from .service import KvService

ROUBLE = 1.0  # strict inequalities and float rounding: amounts are rounded up and get one extra rouble


def _ceil(x: float) -> float:
    return float(math.ceil(x)) + ROUBLE if x > 0 else 0.0


def _rate_map(rate: dict) -> dict[str, float | None]:
    return {r["line"]: r["total"] for r in rate["rates"]}


def rate_gain(before: dict, after: dict) -> dict[str, float]:
    a, b = _rate_map(after), _rate_map(before)
    return {
        line: a[line] - (b.get(line) or 0.0)
        for line in a
        if a[line] is not None and a[line] - (b.get(line) or 0.0) > 1e-9
    }


def _volume_steps(rate: dict) -> list[dict]:
    """Top band of the КАСКО scale and of Доп.АВ1: extra ДВС (any voluntary line) needed to reach the maximum.

    Line caps (КАСКО and КИС: Доп.АВ ≤ +5 п.п., КАСКО ≤ 30%) are applied by evaluate() when the plan is re-checked.
    """
    m, comp = rate["metrics"], rate["components"]
    out = []
    kb = comp["kaskoBase"]
    if kb["scale"] and not kb["newcomer"] and kb["scaleIndex"] is not None and kb["scaleIndex"] < len(kb["scale"]) - 1:
        bound, value = kb["scale"][-2][0], kb["scale"][-1][1]
        out.append({"component": "kaskoBase", "title": "Базовая ставка КАСКО", "target": f"ДВС ≥ {_rub(bound)}",
                    "from": kb["rate"], "to": value, "needs": {"dvs": _ceil(bound - m["dvs"])}})
    d1 = comp["d1"]
    if d1["bandIndex"] < len(d1["bands"]) - 1:
        bound, value = d1["bands"][-2][0], d1["bands"][-1][1]
        out.append({"component": "d1", "title": "Доп.АВ1 — динамика ДВС", "target": f"динамика ≥ {bound * 100:+.0f}%",
                    "from": d1["value"], "to": value,
                    "needs": {"dvs": _ceil((1 + bound) * m["dynamicsBase"] - m["dvs"])}})
    return out


def _rub(x: float) -> str:
    return f"{x:,.0f} ₽".replace(",", " ")


def plan(service: "KvService", agent: str, nxt) -> dict:
    """Steps and combined options for quarter `nxt`, whose reporting quarter is the open one."""
    open_q = nxt - 1
    if open_q != service.inputs.current:
        return {"available": False, "reason": f"Ставку {label(nxt)} определяют завершённые кварталы — повлиять уже нельзя"}
    rule = service.rule_for(nxt)
    base = service.rate(agent, nxt)
    comp, m = base["components"], base["metrics"]
    prol = m["prolongation"]
    above = rule.penetration.above

    steps = _volume_steps(base)
    if comp["d2"]["value"] == 0:
        steps.append({"component": "d2", "title": "Доп.АВ2 — доля приоритетных видов", "target": f"доля > {above * 100:.1f}%",
                      "from": 0.0, "to": rule.penetration.bonus,
                      "needs": {"priority": _ceil((above * m["dvs"] - m["priority"]) / (1 - above))}})
    prolonged_needed = None
    if comp["d3"]["value"] == 0:
        step = {"component": "d3", "title": "Доп.АВ3 — пролонгация",
                "target": f"пролонгировано ≥ {rule.prolongation.at_least * 100:.2f}% договоров",
                "from": 0.0, "to": rule.prolongation.bonus}
        if prol["due"]:
            prolonged_needed = math.ceil(rule.prolongation.at_least * prol["due"] - 1e-9)
            step["needs"] = {"prolonged": prolonged_needed, "due": prol["due"], "dueEstimated": prol["dueEstimated"]}
        else:
            step.update(needs={}, blocked="нет договоров к пролонгации")
        steps.append(step)

    for s in steps:  # verify each step alone and report the real rate gain (the КАСКО cap may eat it)
        n = s["needs"]
        if s.get("blocked"):
            s["gain"] = {}
            continue
        adds = Additions(priority=n.get("priority", n.get("dvs", 0.0)), prolonged=n.get("prolonged"))
        s["gain"] = rate_gain(base, service.rate(agent, nxt, additions=adds))
        s["salesNote"] = "любые добровольные виды (в проверке — приоритетные)" if "dvs" in n else None

    volume = max([s["needs"]["dvs"] for s in steps if "dvs" in s["needs"]], default=0.0)
    penetration = max([s["needs"]["priority"] for s in steps if "priority" in s["needs"]], default=0.0)
    options = [
        _option(service, agent, nxt, base, "priority", "Только приоритетные виды",
                Additions(priority=max(volume, penetration), prolonged=prolonged_needed)),
    ]
    share = _kasko_share(base, rule.kasko.line)
    if share and volume > 0:
        options.append(_option(service, agent, nxt, base, "current_mix", "Текущая структура продаж",
                               _mix_additions(base, above, share, volume, penetration > 0, prolonged_needed)))
    return {
        "available": True,
        "quarter": label(nxt),
        "salesQuarter": label(open_q),
        "steps": steps,
        "options": [o for o in options if o is not None],
        "note": (f"Продажи {label(open_q)} поднимут ставки {label(nxt)}, но станут базой динамики для {label(nxt + 1)}. "
                 "Каждый план пересчитан по правилам; суммы — наименьшие при указанной структуре продаж."),
    }


def _kasko_share(rate: dict, kasko_line: str) -> float | None:
    amounts = rate["amountsReporting"]
    total = sum(max(0.0, a) for a in amounts.values())
    return None if total <= 0 else max(0.0, amounts.get(kasko_line, 0.0)) / total


def _mix_additions(rate: dict, above: float, w: float, volume: float, needs_penetration: bool,
                   prolonged: int | None) -> Additions | None:
    """Smallest total s split as КАСКО w·s and priority (1−w)·s that meets the volume and penetration steps."""
    s, m = volume, rate["metrics"]
    if needs_penetration:
        slope = (1 - w) - above
        if slope <= 0:
            return None  # with this mix penetration never rises above the threshold
        s = max(s, _ceil((above * m["dvs"] - m["priority"]) / slope))
    return Additions(kasko=round(s * w, 2), priority=round(s * (1 - w), 2), prolonged=prolonged)


def _option(service: "KvService", agent: str, nxt, base: dict, key: str, title: str, adds: Additions | None) -> dict | None:
    if adds is None or not adds.has_inputs():
        return None
    after = service.rate(agent, nxt, additions=adds)
    return {
        "key": key,
        "title": title,
        "kasko": adds.kasko,
        "priority": adds.priority,
        "prolonged": adds.prolonged,
        "contracts": service.contracts_estimate(agent, adds),
        "rates": after["rates"],
        "components": component_values(after),
        "gain": rate_gain(base, after),
        "effects": service.effects(agent, nxt, adds, base, after),
    }


def component_values(rate: dict) -> dict[str, float | None]:
    c = rate["components"]
    return {"kaskoBase": c["kaskoBase"]["rate"], "d1": c["d1"]["value"], "d2": c["d2"]["value"], "d3": c["d3"]["value"]}
