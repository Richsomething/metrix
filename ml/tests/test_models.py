import numpy as np
import pytest

from metrixs_ml.backtest import compare, plannable_quarters, walk_forward
from metrixs_ml.features import build_frame, has_features
from metrixs_ml.models import candidate_factories


@pytest.fixture
def frame(raw):
    return build_frame(raw)


@pytest.mark.parametrize("name", ["naive", "trend", "ridge", "gbm"])
def test_contributions_sum_to_plan(frame, name):
    model = candidate_factories()[name]().fit(frame)
    rows = frame[has_features(frame) & frame["fact"].notna()]

    plans = model.predict(rows)
    explanations = model.explain(rows)

    for plan, items in zip(plans, explanations):
        assert sum(v for _, v in items) == pytest.approx(plan, rel=1e-6)


def test_walk_forward_never_trains_on_the_planned_quarter(frame):
    seen = []

    class Spy:
        title = "spy"

        def fit(self, train):
            seen.append(train["quarter"].max())
            return self

        def predict(self, test):
            seen[-1] = (seen[-1], test["quarter"].iloc[0])
            return test["lag1"].to_numpy()

    walk_forward(frame, Spy)

    assert seen and all(last_train < planned for last_train, planned in seen)


def test_steady_growth_is_planned_better_than_naive(frame):
    scores = {s.name: s for s in compare(frame, candidate_factories())}

    assert scores["ridge"].wape < scores["naive"].wape
    assert scores["naive"].bias > 0  # naive plans lag steady growth


def test_plannable_quarters_leave_enough_history(frame):
    quarters = plannable_quarters(frame)

    assert quarters
    assert np.all([q > frame["quarter"].min() for q in quarters])
