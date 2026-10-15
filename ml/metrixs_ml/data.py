"""Loads the anonymised Excel export into tidy pandas frames."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

EXCEL_EPOCH = pd.Timestamp("1899-12-30")

SHEET_COLLECTIONS = "сборы"
SHEET_PROLONGATIONS = "пролонг"
SHEET_AGENTS = "дата 1 АД агента"

COLLECTION_COLUMNS = {
    "Отч период": "period",
    "Дата заключения": "signed_at",
    "Линия бизнеса": "line",
    "Договор": "contract",
    "Продукт": "product",
    "Филиал": "branch",
    "AGENTISN": "agent_id",
    "Агент": "agent",
    "Сумма сборов": "amount",
}
PROLONGATION_COLUMNS = {
    "Дата окончания": "end_at",
    "Агент": "agent",
    "Линия бизнеса": "line",
    "Договор к пролонгации": "contract",
    "Пролонгация": "prolonged_contract",
}
AGENT_COLUMNS = {"AGENTISN": "agent_id", "Агент": "agent", "Дата 1 АД": "first_contract_at"}


@dataclass(frozen=True)
class RawData:
    collections: pd.DataFrame
    prolongations: pd.DataFrame
    agents: pd.DataFrame


def to_timestamp(value: object) -> pd.Timestamp:
    """The export mixes real date cells with raw Excel serial numbers in the same column."""
    if isinstance(value, (pd.Timestamp, dt.datetime, dt.date)):
        return pd.Timestamp(value)
    if isinstance(value, (int, float)) and not pd.isna(value):
        return EXCEL_EPOCH + pd.Timedelta(days=float(value))
    return pd.NaT


def _read_sheet(path: Path, sheet: str, columns: dict[str, str]) -> pd.DataFrame:
    """Header is the first non-empty row; only the mapped columns are kept."""
    raw = pd.read_excel(path, sheet_name=sheet, header=None, engine="openpyxl")
    header_index = raw.notna().any(axis=1).idxmax()
    frame = raw.iloc[header_index + 1 :].copy()
    frame.columns = [str(c).strip() if pd.notna(c) else "" for c in raw.iloc[header_index]]

    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"На листе «{sheet}» нет колонок: {', '.join(missing)}")
    return frame[list(columns)].rename(columns=columns).reset_index(drop=True)


@dataclass(frozen=True)
class Cutoff:
    raw: RawData
    as_of: pd.Timestamp
    excluded_rows: int
    last_completed_quarter: pd.Period


def cut_off(raw: RawData, as_of: pd.Timestamp) -> Cutoff:
    """Keeps only quarters that ended on or before `as_of`.

    The synthetic export contains collection records dated after the report date; those quarters
    are not finished, so their «facts» must not reach training, backtest or bonuses.
    """
    quarter_last_day = raw.collections["period"].dt.to_period("Q").dt.end_time.dt.normalize()
    completed = quarter_last_day <= as_of.normalize()
    if not completed.any():
        raise ValueError(f"Нет ни одного завершённого квартала на дату {as_of.date()}")
    collections = raw.collections[completed].reset_index(drop=True)
    return Cutoff(
        raw=RawData(collections=collections, prolongations=raw.prolongations, agents=raw.agents),
        as_of=as_of,
        excluded_rows=int((~completed).sum()),
        last_completed_quarter=collections["period"].dt.to_period("Q").max(),
    )


def load_raw(path: Path) -> RawData:
    if not path.exists():
        raise FileNotFoundError(f"Файл с данными не найден: {path}")

    collections = _read_sheet(path, SHEET_COLLECTIONS, COLLECTION_COLUMNS)
    collections = collections.dropna(subset=["contract"]).assign(
        period=lambda f: f["period"].map(to_timestamp),
        signed_at=lambda f: f["signed_at"].map(to_timestamp),
        amount=lambda f: pd.to_numeric(f["amount"], errors="coerce").fillna(0.0),
        agent=lambda f: f["agent"].astype(str).str.strip(),
    )
    if collections["period"].isna().any():
        raise ValueError("В листе «сборы» есть строки без отчётного периода")

    prolongations = _read_sheet(path, SHEET_PROLONGATIONS, PROLONGATION_COLUMNS)
    prolongations = prolongations.dropna(subset=["contract"]).assign(
        end_at=lambda f: f["end_at"].map(to_timestamp),
        agent=lambda f: f["agent"].astype(str).str.strip(),
    )

    agents = _read_sheet(path, SHEET_AGENTS, AGENT_COLUMNS)
    agents = agents.dropna(subset=["agent_id"]).assign(
        first_contract_at=lambda f: f["first_contract_at"].map(to_timestamp),
        agent=lambda f: f["agent"].astype(str).str.strip(),
    )

    return RawData(collections=collections, prolongations=prolongations, agents=agents)
