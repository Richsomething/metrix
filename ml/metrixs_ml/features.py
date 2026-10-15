"""Agent × quarter panel and plan features.

Every feature for quarter Q is computed only from quarters strictly before Q
(plus calendar facts such as the quarter number and tenure), so a plan never
peeks at the result it is later compared against.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .data import RawData

DAYS_PER_YEAR = 365.25
GROWTH_WINDOW = 3

# Largest business lines; their share of an agent's portfolio is a feature.
SHARE_LINES = {
    "share_kasko": "КАСКО",
    "share_kis": "КИС",
    "share_property": "ИМУЩЕСТВО ФИЗ. ЛИЦ",
}

FEATURES = [
    "growth_last",
    "growth_mean",
    "refund_share_last",
    "log_contracts_last",
    "quarter_of_year",
    "tenure_years",
    *SHARE_LINES,
]

FEATURE_LABELS = {
    "base": "База: сборы прошлого квартала",
    "growth_last": "Рост в прошлом квартале",
    "growth_mean": "Средний рост за 3 квартала",
    "refund_share_last": "Доля возвратов в прошлом квартале",
    "log_contracts_last": "Число договоров в прошлом квартале",
    "quarter_of_year": "Сезонность (номер квартала)",
    "tenure_years": "Стаж агента",
    "share_kasko": "Доля КАСКО в портфеле",
    "share_kis": "Доля КИС в портфеле",
    "share_property": "Доля имущества физлиц в портфеле",
    "trend": "Линейный тренд",
}


def quarter_label(quarter: pd.Period) -> str:
    return f"{quarter.year}Q{quarter.quarter}"


def quarterly_panel(raw: RawData, horizon: int = 1) -> pd.DataFrame:
    """One row per agent and quarter, plus `horizon` future quarters with unknown fact."""
    c = raw.collections.assign(quarter=raw.collections["period"].dt.to_period("Q"))

    base = c.groupby(["agent", "quarter"]).agg(
        fact=("amount", "sum"),
        gross=("amount", lambda s: s[s > 0].sum()),
        refunds=("amount", lambda s: -s[s < 0].sum()),
        contracts=("contract", "nunique"),
    )
    shares = (
        c.pivot_table(index=["agent", "quarter"], columns="line", values="amount", aggfunc="sum", fill_value=0.0)
        .reindex(columns=list(SHARE_LINES.values()), fill_value=0.0)
        .div(base["gross"].replace(0, np.nan), axis=0)
        .fillna(0.0)
        .rename(columns={line: key for key, line in SHARE_LINES.items()})
    )

    quarters = pd.period_range(c["quarter"].min(), c["quarter"].max() + horizon, freq="Q")
    index = pd.MultiIndex.from_product([sorted(c["agent"].unique()), quarters], names=["agent", "quarter"])
    panel = base.join(shares).reindex(index).reset_index()

    first_contract = raw.agents.set_index("agent")["first_contract_at"]
    quarter_start = panel["quarter"].dt.start_time
    # Two agents have collections before their recorded first contract date; tenure is floored at 0.
    tenure = (quarter_start - panel["agent"].map(first_contract)).dt.days / DAYS_PER_YEAR
    return panel.assign(tenure_years=tenure.clip(lower=0).fillna(0.0), quarter_of_year=panel["quarter"].dt.quarter)


def add_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Lagged features per agent; `target_ratio` is fact / previous quarter fact."""
    p = panel.sort_values(["agent", "quarter"]).reset_index(drop=True)
    by_agent = p.groupby("agent", group_keys=False)

    lag1 = by_agent["fact"].shift(1)
    lag2 = by_agent["fact"].shift(2)
    growth = p["fact"] / by_agent["fact"].shift(1)
    past_growth = growth.groupby(p["agent"]).shift(1)

    features = pd.DataFrame(
        {
            "lag1": lag1,
            "growth_last": lag1 / lag2,
            "growth_mean": past_growth.groupby(p["agent"]).transform(
                lambda s: s.rolling(GROWTH_WINDOW, min_periods=1).mean()
            ),
            "refund_share_last": by_agent["refunds"].shift(1) / by_agent["gross"].shift(1),
            "log_contracts_last": np.log1p(by_agent["contracts"].shift(1)),
            **{key: by_agent[key].shift(1) for key in SHARE_LINES},
        }
    )
    out = pd.concat([p.drop(columns=list(SHARE_LINES)), features], axis=1)
    out["target_ratio"] = out["fact"] / out["lag1"]
    out["refund_share"] = out["refunds"] / out["gross"]
    out["quarter_label"] = out["quarter"].map(quarter_label)
    return out


def build_frame(raw: RawData, horizon: int = 1) -> pd.DataFrame:
    return add_features(quarterly_panel(raw, horizon=horizon))


def has_features(frame: pd.DataFrame) -> pd.Series:
    return frame[["lag1", *FEATURES]].notna().all(axis=1) & (frame["lag1"] > 0)
