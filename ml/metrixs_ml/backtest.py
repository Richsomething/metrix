"""Walk-forward backtest: for each quarter, train only on earlier quarters and plan that quarter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from .features import has_features
from .models import PlanModel

# A model needs at least this many earlier quarters with features before it may plan one.
MIN_TRAIN_QUARTERS = 4


@dataclass(frozen=True)
class ModelScore:
    name: str
    title: str
    wape: float
    mape: float
    bias: float
    quarters: int


def wape(fact: np.ndarray, plan: np.ndarray) -> float:
    """Weighted absolute percentage error: Σ|fact − plan| / Σ|fact|."""
    return float(np.abs(fact - plan).sum() / np.abs(fact).sum())


def mape(fact: np.ndarray, plan: np.ndarray) -> float:
    return float(np.mean(np.abs(fact - plan) / np.abs(fact)))


def bias(fact: np.ndarray, plan: np.ndarray) -> float:
    """Positive bias = plans are systematically below fact (easy plans, overpaid bonuses)."""
    return float((fact - plan).sum() / np.abs(fact).sum())


def plannable_quarters(frame: pd.DataFrame) -> list[pd.Period]:
    with_features = sorted(frame.loc[has_features(frame), "quarter"].unique())
    return with_features[MIN_TRAIN_QUARTERS:]


def walk_forward(
    frame: pd.DataFrame, factory: Callable[[], PlanModel], explain: bool = False
) -> pd.DataFrame:
    """Out-of-sample plans for every plannable quarter with a known fact."""
    rows = []
    for quarter in plannable_quarters(frame):
        test = frame[(frame["quarter"] == quarter) & has_features(frame) & frame["fact"].notna()]
        if test.empty:
            continue
        model = factory().fit(frame[frame["quarter"] < quarter])
        result = test[["agent", "quarter", "quarter_label", "fact", "refund_share"]].assign(plan=model.predict(test))
        if explain:
            result = result.assign(contributions=model.explain(test))
        rows.append(result)
    return pd.concat(rows, ignore_index=True)


def score(name: str, title: str, predictions: pd.DataFrame) -> ModelScore:
    fact = predictions["fact"].to_numpy(dtype=float)
    plan = predictions["plan"].to_numpy(dtype=float)
    return ModelScore(
        name=name,
        title=title,
        wape=wape(fact, plan),
        mape=mape(fact, plan),
        bias=bias(fact, plan),
        quarters=predictions["quarter"].nunique(),
    )


def compare(frame: pd.DataFrame, factories: dict[str, Callable[[], PlanModel]]) -> list[ModelScore]:
    """Scores every candidate on the same walk-forward quarters, best (lowest WAPE) first."""
    scores = [score(name, factory().title, walk_forward(frame, factory)) for name, factory in factories.items()]
    return sorted(scores, key=lambda s: s.wape)
