"""Synthetic fixtures — tests never read the real export."""

import pandas as pd
import pytest

from metrixs_ml.data import RawData

AGENTS = ["Агент А", "Агент Б", "Агент В"]
QUARTER_ENDS = pd.date_range("2024-03-31", periods=10, freq="QE")


def _collections() -> pd.DataFrame:
    rows = []
    for a_index, agent in enumerate(AGENTS):
        base = 1_000_000 * (a_index + 1)
        for q_index, period in enumerate(QUARTER_ENDS):
            amount = base * (1.03**q_index)
            for line, share in [("КАСКО", 0.5), ("КИС", 0.3), ("ИМУЩЕСТВО ФИЗ. ЛИЦ", 0.2)]:
                rows.append(
                    {
                        "period": period,
                        "signed_at": period - pd.Timedelta(days=30),
                        "line": line,
                        "contract": f"POL-{a_index}-{q_index}-{line}",
                        "product": "П",
                        "branch": "Ф",
                        "agent_id": str(a_index),
                        "agent": agent,
                        "amount": amount * share,
                    }
                )
            rows.append({**rows[-1], "contract": f"REF-{a_index}-{q_index}", "amount": -amount * 0.02})
    return pd.DataFrame(rows)


@pytest.fixture
def raw() -> RawData:
    agents = pd.DataFrame(
        {"agent_id": ["0", "1", "2"], "agent": AGENTS, "first_contract_at": pd.to_datetime(["2015-01-01", "2020-06-01", "2025-01-01"])}
    )
    prolongations = pd.DataFrame(columns=["end_at", "agent", "line", "contract"])
    return RawData(collections=_collections(), prolongations=prolongations, agents=agents)
