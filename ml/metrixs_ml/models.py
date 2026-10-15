"""Plan models. Each predicts next-quarter collections and explains the plan additively.

Explanations are lists of (key, value-in-money) whose values sum to the plan:
a «base» term plus one term per driver.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from .features import FEATURES, has_features

Contribution = tuple[str, float]
RANDOM_STATE = 42
TREND_WINDOW = 4


class PlanModel(Protocol):
    name: str
    title: str

    def fit(self, frame: pd.DataFrame) -> "PlanModel": ...
    def predict(self, frame: pd.DataFrame) -> np.ndarray: ...
    def explain(self, frame: pd.DataFrame) -> list[list[Contribution]]: ...


def labelled(frame: pd.DataFrame) -> pd.DataFrame:
    """Rows usable for training: known fact and complete features."""
    return frame[has_features(frame) & frame["target_ratio"].notna()]


@dataclass
class NaiveModel:
    """Plan = last quarter's collections."""

    name: str = "naive"
    title: str = "Как в прошлом квартале"

    def fit(self, frame: pd.DataFrame) -> "NaiveModel":
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return frame["lag1"].to_numpy(dtype=float)

    def explain(self, frame: pd.DataFrame) -> list[list[Contribution]]:
        return [[("base", float(v))] for v in self.predict(frame)]


@dataclass
class TrendModel:
    """Per-agent linear trend over the last `window` known quarters."""

    window: int = TREND_WINDOW
    name: str = "trend"
    title: str = "Линейный тренд агента"
    history: pd.DataFrame = field(default_factory=pd.DataFrame)

    def fit(self, frame: pd.DataFrame) -> "TrendModel":
        self.history = frame.loc[frame["fact"].notna(), ["agent", "quarter", "fact"]]
        return self

    def _plan(self, agent: str, quarter: pd.Period, fallback: float) -> float:
        h = self.history[(self.history["agent"] == agent) & (self.history["quarter"] < quarter)].tail(self.window)
        if len(h) < 2:
            return fallback
        x = h["quarter"].map(lambda q: q.ordinal).to_numpy(dtype=float)
        slope, intercept = np.polyfit(x, h["fact"].to_numpy(dtype=float), 1)
        return float(slope * quarter.ordinal + intercept)

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return np.array([self._plan(r.agent, r.quarter, r.lag1) for r in frame.itertuples()], dtype=float)

    def explain(self, frame: pd.DataFrame) -> list[list[Contribution]]:
        plans = self.predict(frame)
        return [[("base", float(lag1)), ("trend", float(plan - lag1))] for lag1, plan in zip(frame["lag1"], plans)]


@dataclass
class RatioModel:
    """Learns the growth ratio fact / last quarter from FEATURES; plan = last quarter × ratio.

    SHAP values are computed in ratio space and scaled by last quarter, so in money:
    plan = lag1 × E[ratio] + Σ lag1 × shap_i.
    """

    name: str
    title: str
    make_estimator: Callable[[], object]
    scale: bool = False
    estimator: object | None = None
    scaler: StandardScaler | None = None
    background: np.ndarray | None = None

    def _matrix(self, frame: pd.DataFrame) -> np.ndarray:
        x = frame[FEATURES].to_numpy(dtype=float)
        return self.scaler.transform(x) if self.scaler is not None else x

    def fit(self, frame: pd.DataFrame) -> "RatioModel":
        train = labelled(frame)
        if train.empty:
            raise ValueError(f"Нет данных для обучения модели «{self.title}»")
        x = train[FEATURES].to_numpy(dtype=float)
        self.scaler = StandardScaler().fit(x) if self.scale else None
        self.background = self._matrix(train)
        self.estimator = self.make_estimator()
        self.estimator.fit(self.background, train["target_ratio"].to_numpy(dtype=float))
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return frame["lag1"].to_numpy(dtype=float) * self.estimator.predict(self._matrix(frame))

    def _explainer(self) -> shap.Explainer:
        if isinstance(self.estimator, Ridge):
            return shap.LinearExplainer(self.estimator, self.background)
        return shap.TreeExplainer(self.estimator, self.background)

    def explain(self, frame: pd.DataFrame) -> list[list[Contribution]]:
        explainer = self._explainer()
        values = np.atleast_2d(explainer.shap_values(self._matrix(frame)))
        expected = float(np.ravel(explainer.expected_value)[0])
        rows = []
        for lag1, shap_row in zip(frame["lag1"].to_numpy(dtype=float), values):
            rows.append([("base", lag1 * expected), *((f, float(lag1 * v)) for f, v in zip(FEATURES, shap_row))])
        return rows


def candidate_factories() -> dict[str, Callable[[], PlanModel]]:
    return {
        "naive": NaiveModel,
        "trend": TrendModel,
        "ridge": lambda: RatioModel(
            name="ridge", title="Ridge-регрессия на признаках", make_estimator=lambda: Ridge(alpha=1.0), scale=True
        ),
        "gbm": lambda: RatioModel(
            name="gbm",
            title="Градиентный бустинг на признаках",
            make_estimator=lambda: GradientBoostingRegressor(
                n_estimators=200,
                max_depth=2,
                learning_rate=0.05,
                subsample=0.8,
                min_samples_leaf=3,
                random_state=RANDOM_STATE,
            ),
        ),
    }
