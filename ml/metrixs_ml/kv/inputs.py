"""АВ inputs built at training time from the data export (backend/data/data.xlsx) → artifacts/kv_inputs.json.

Per agent × line × quarter: facts for quarters completed by the report date; for the running quarter the
contracts signed up to the report date plus a forecast of the rest; a forecast for the quarter after.
Records dated after the report date are never used. Rules are applied later, at request time.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from ..data import to_timestamp

METHODS = {
    "naive": "последний квартал",
    "mean4": "среднее за 4 последних квартала",
    "seasonal": "тот же квартал год назад",
}
SEASON = 4
# the «пролонг» sheet names some lines differently from «сборы»
LINE_ALIASES = {"ИФЛ": "ИМУЩЕСТВО ФИЗ. ЛИЦ"}
MIX_QUARTERS = 4  # product mix: last completed quarters
TOP_PRODUCTS = 5


def _sheet(path: Path, name: str) -> pd.DataFrame:
    """Header = first non-empty row (the «пролонг» sheet starts on row 2)."""
    raw = pd.read_excel(path, sheet_name=name, header=None, engine="openpyxl")
    header = int(raw.notna().any(axis=1).idxmax())
    frame = raw.iloc[header + 1 :].copy()
    frame.columns = [str(c).strip() if pd.notna(c) else f"_{i}" for i, c in enumerate(raw.iloc[header])]
    return frame.reset_index(drop=True)


def _column(frame: pd.DataFrame, name: str) -> pd.Series:
    return frame[name] if name in frame else pd.Series(np.nan, index=frame.index)


def read_workbook(path: Path) -> dict[str, pd.DataFrame]:
    if not path.exists():
        raise FileNotFoundError(f"Нет файла данных: {path}")
    c = _sheet(path, "сборы").dropna(subset=["Договор"])
    collections = pd.DataFrame(
        {
            "period": c["Отч период"].map(to_timestamp),
            "signed_at": _column(c, "Дата заключения").map(to_timestamp),
            "line": c["Линия бизнеса"].astype(str).str.strip(),
            "product": _column(c, "Продукт").astype("string").str.strip().fillna("—"),
            "contract": c["Договор"].astype(str),
            "branch": c["Филиал"].astype(str).str.strip(),
            "agent": c["Агент"].astype(str).str.strip(),
            "amount": pd.to_numeric(c["Сумма сборов"], errors="coerce").fillna(0.0),
        }
    )
    p = _sheet(path, "пролонг").dropna(subset=["Договор к пролонгации"])
    prolong = pd.DataFrame(
        {
            "agent": p["Агент"].astype(str).str.strip(),
            "line": p["Линия бизнеса"].astype(str).str.strip().replace(LINE_ALIASES),
            "product": _column(p, "Продукт страхования").astype("string").str.strip().fillna("—"),
            "contract": p["Договор к пролонгации"].astype(str).str.strip(),
            "end_at": p["Дата окончания"].map(to_timestamp),
            "done": pd.to_numeric(_column(p, "Пролонгировано всего"), errors="coerce"),
        }
    )
    groups = _sheet(path, "группа филиала")
    first_ad = _sheet(path, "дата 1 АД агента")
    return {
        "collections": collections,
        "prolong": prolong,
        "groups": pd.DataFrame({"branch": groups["Филиал"].astype(str).str.strip(), "group": groups["группа"].astype(str).str.strip()}),
        "first_ad": pd.DataFrame({"agent": first_ad["Агент"].astype(str).str.strip(), "first_ad": first_ad["Дата 1 АД"].map(to_timestamp)}),
    }


def _forecast(method: str, history: list[float], horizon: int) -> float:
    """Value `horizon` quarters after the last observed one."""
    if method == "naive":
        value = history[-1]
    elif method == "mean4":
        last = history[-SEASON:]
        value = sum(last) / len(last)
    else:
        back = len(history) + horizon - 1 - SEASON
        value = history[back] if 0 <= back < len(history) else history[-1]
    return max(0.0, float(value))


def backtest(quarterly: pd.DataFrame) -> list[dict]:
    """One-quarter-ahead walk-forward over quarters with ≥4 quarters of history; WAPE across agent × line."""
    values = quarterly.to_numpy(dtype=float)
    scores = []
    for method, title in METHODS.items():
        truth, pred = [], []
        for i in range(SEASON, values.shape[1]):
            for row in values:
                truth.append(row[i])
                pred.append(_forecast(method, list(row[:i]), 1))
        denom = sum(abs(t) for t in truth)
        wape = None if denom == 0 else sum(abs(t - p) for t, p in zip(truth, pred)) / denom
        scores.append({"method": method, "title": title, "wape": wape, "points": len(truth)})
    return sorted(scores, key=lambda s: math.inf if s["wape"] is None else s["wape"])


def _qlabel(q: pd.Period) -> str:
    return f"{q.year}Q{q.quarter}"


def _prolongation(prolong: pd.DataFrame) -> tuple[dict, dict, bool]:
    """Contracts due per agent × end quarter × line; prolonged only where the export has outcomes."""
    p = prolong.dropna(subset=["end_at"]).assign(quarter=lambda f: f["end_at"].dt.to_period("Q"))
    due = p.groupby(["agent", "quarter", "line", "product"]).size().to_dict()
    known = p.dropna(subset=["done"])
    done = known.groupby(["agent", "quarter", "line", "product"])["done"].sum().to_dict()
    return due, done, not known.empty


def _product_mix(closed: pd.DataFrame, last_q: pd.Period) -> dict:
    """Agent → line → top products by collections over the last completed quarters (positive records only)."""
    recent = closed[(closed["quarter"] > last_q - MIX_QUARTERS) & (closed["amount"] > 0)]
    grouped = recent.groupby(["agent", "line", "product"]).agg(amount=("amount", "sum"), contracts=("contract", "nunique"))
    out: dict[str, dict[str, list]] = {}
    for (agent, line), part in grouped.groupby(level=["agent", "line"]):
        top = part.sort_values("amount", ascending=False).head(TOP_PRODUCTS)
        out.setdefault(agent, {})[line] = [
            {"product": idx[2], "amount": round(float(r.amount), 2), "contracts": int(r.contracts)} for idx, r in top.iterrows()
        ]
    return out


def _due_contracts(prolong: pd.DataFrame, quarter: pd.Period) -> dict:
    """Agent → contracts whose term ends in `quarter`, by end date."""
    p = prolong.dropna(subset=["end_at"])
    p = p[p["end_at"].dt.to_period("Q") == quarter].sort_values("end_at")
    return {
        agent: [{"contract": r.contract, "line": r.line, "product": r.product, "endAt": r.end_at.date().isoformat(),
                 "prolonged": None if pd.isna(r.done) else bool(r.done)} for r in part.itertuples()]
        for agent, part in p.groupby("agent")
    }


def build_kv_inputs(path: Path, as_of: pd.Timestamp) -> dict:
    wb = read_workbook(path)
    c = wb["collections"].assign(quarter=lambda f: f["period"].dt.to_period("Q"))
    open_q = pd.Period(as_of, freq="Q")
    elapsed = ((as_of - open_q.start_time).days + 1) / ((open_q.end_time - open_q.start_time).days + 1)

    closed = c[c["quarter"] < open_q]
    running = c[(c["quarter"] == open_q) & (c["signed_at"] <= as_of)]
    excluded = len(c) - len(closed) - len(running)
    if closed.empty:
        raise ValueError(f"Нет завершённых кварталов до {as_of.date()}")

    agents = sorted(closed["agent"].unique())
    lines = sorted(c["line"].unique())
    history_q = pd.period_range(closed["quarter"].min(), open_q - 1, freq="Q")
    quarterly = closed.groupby(["agent", "line", "quarter"])["amount"].sum().unstack("quarter").reindex(columns=history_q)
    quarterly = quarterly.reindex(pd.MultiIndex.from_product([agents, lines], names=["agent", "line"])).fillna(0.0)
    quality = backtest(quarterly)
    method = quality[0]["method"]

    def predict(agent: str, line: str, horizon: int) -> float:
        return _forecast(method, [float(v) for v in quarterly.loc[(agent, line)]], horizon)

    facts = closed.groupby(["agent", "line", "quarter"]).agg(net=("amount", "sum"), contracts=("contract", "nunique"))
    to_date = running.groupby(["agent", "line"]).agg(net=("amount", "sum"), contracts=("contract", "nunique"))
    groups = dict(zip(wb["groups"]["branch"].str.upper(), wb["groups"]["group"]))
    first_ad = dict(zip(wb["first_ad"]["agent"], wb["first_ad"]["first_ad"]))
    due, done, has_outcome = _prolongation(wb["prolong"])

    def prolong_fields(agent: str, q: pd.Period) -> dict:
        due_by: dict[str, dict[str, int]] = {}
        done_by: dict[str, dict[str, int]] = {}
        for (a, pq, line, product), n in due.items():
            if a == agent and pq == q:
                due_by.setdefault(line, {})[product] = int(n)
        for (a, pq, line, product), n in done.items():
            if a == agent and pq == q:
                done_by.setdefault(line, {})[product] = int(n)
        return {
            "prolongDue": sum(sum(v.values()) for v in due_by.values()),
            "prolonged": sum(sum(v.values()) for v in done_by.values()) if done_by else None,
            "prolongDueByProduct": due_by,
            "prolongedByProduct": done_by if done_by else None,
            "prolongDueEstimated": False,
        }

    out: dict[str, dict] = {}
    info: dict[str, dict] = {}
    for agent in agents:
        branch = c.loc[c["agent"] == agent, "branch"].mode().iloc[0]
        fad = first_ad.get(agent)
        info[agent] = {
            "branch": branch,
            "group": groups.get(branch.upper()),
            "firstAd": None if fad is None or pd.isna(fad) else fad.date().isoformat(),
        }
        quarters: dict[str, dict] = {}
        for q in history_q:
            entry_lines = {}
            for line in lines:
                key = (agent, line, q)
                found = key in facts.index
                entry_lines[line] = {"toDate": round(float(facts.at[key, "net"]) if found else 0.0, 2), "remainder": 0.0,
                                     "contracts": int(facts.at[key, "contracts"]) if found else 0}
            quarters[_qlabel(q)] = {"kind": "fact", "lines": entry_lines, **prolong_fields(agent, q)}
        now_lines = {}
        for line in lines:
            key = (agent, line)
            found = key in to_date.index
            now_lines[line] = {"toDate": round(float(to_date.at[key, "net"]) if found else 0.0, 2),
                               "remainder": round(predict(agent, line, 1) * (1 - elapsed), 2),
                               "contracts": int(to_date.at[key, "contracts"]) if found else 0}
        quarters[_qlabel(open_q)] = {"kind": "nowcast", "lines": now_lines, **prolong_fields(agent, open_q)}
        quarters[_qlabel(open_q + 1)] = {
            "kind": "forecast",
            "lines": {line: {"toDate": 0.0, "remainder": round(predict(agent, line, 2), 2), "contracts": 0} for line in lines},
            **prolong_fields(agent, open_q + 1),
        }
        out[agent] = quarters

    return {
        "source": path.name,
        "asOf": as_of.date().isoformat(),
        "currentQuarter": _qlabel(open_q),
        "currentQuarterHasData": not running.empty,
        "elapsedShare": round(elapsed, 4),
        "rowsAfterAsOfExcluded": int(excluded),
        "prolongationOutcomesAvailable": has_outcome,
        "agents": agents,
        "lines": lines,
        "agentInfo": info,
        "quarters": out,
        "productMix": _product_mix(closed, open_q - 1),
        "prolongContracts": _due_contracts(wb["prolong"], open_q),
        "forecastQuality": {
            "scores": quality,
            "chosen": quality[0],
            "quarters": len(history_q),
            "note": f"Поквартальный бэктест на {len(history_q)} завершённых кварталах.",
        },
    }


def round_floats(value):
    """JSON-safe: numpy scalars to Python numbers."""
    if isinstance(value, dict):
        return {k: round_floats(v) for k, v in value.items()}
    if isinstance(value, list):
        return [round_floats(v) for v in value]
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.integer):
        return int(value)
    return value
