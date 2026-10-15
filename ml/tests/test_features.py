import pandas as pd
import pytest

from metrixs_ml.data import to_timestamp
from metrixs_ml.features import FEATURES, build_frame, quarterly_panel


def test_to_timestamp_handles_excel_serial_and_datetime():
    assert to_timestamp(45382) == pd.Timestamp("2024-03-31")
    assert to_timestamp(pd.Timestamp("2024-03-31")) == pd.Timestamp("2024-03-31")
    assert pd.isna(to_timestamp(None))


def test_panel_adds_future_quarter_with_unknown_fact(raw):
    panel = quarterly_panel(raw, horizon=1)

    future = panel[panel["quarter"] == pd.Period("2026Q3")]

    assert len(future) == 3
    assert future["fact"].isna().all()


def test_tenure_is_floored_at_zero_when_first_contract_is_later(raw):
    panel = quarterly_panel(raw)

    assert (panel.loc[panel["agent"] == "Агент В", "tenure_years"] >= 0).all()


def test_features_do_not_depend_on_current_quarter_fact(raw):
    # Arrange: change only the fact of one quarter
    frame = build_frame(raw)
    changed = raw.collections.copy()
    target = (changed["agent"] == "Агент А") & (changed["period"] == pd.Timestamp("2025-06-30"))
    changed.loc[target, "amount"] *= 10

    # Act
    from metrixs_ml.data import RawData

    frame_changed = build_frame(RawData(changed, raw.prolongations, raw.agents))

    # Assert: that quarter's features are identical, only its fact moved
    row = lambda f: f[(f["agent"] == "Агент А") & (f["quarter_label"] == "2025Q2")].iloc[0]
    assert row(frame)[FEATURES].tolist() == pytest.approx(row(frame_changed)[FEATURES].tolist())
    assert row(frame_changed)["fact"] == pytest.approx(row(frame)["fact"] * 10)


def test_cut_off_drops_unfinished_quarters(raw):
    from metrixs_ml.data import cut_off

    result = cut_off(raw, pd.Timestamp("2026-02-15"))  # 2026Q1 is still running

    assert result.last_completed_quarter == pd.Period("2025Q4")
    assert result.raw.collections["period"].max() == pd.Timestamp("2025-12-31")
    assert result.excluded_rows == len(raw.collections) - len(result.raw.collections) > 0


def test_cut_off_keeps_quarter_ending_on_report_date(raw):
    from metrixs_ml.data import cut_off

    assert cut_off(raw, pd.Timestamp("2025-12-31")).last_completed_quarter == pd.Period("2025Q4")


def test_growth_last_matches_previous_quarter_ratio(raw):
    frame = build_frame(raw)

    row = frame[(frame["agent"] == "Агент Б") & (frame["quarter_label"] == "2025Q1")].iloc[0]

    assert row["growth_last"] == pytest.approx(1.03)
    assert row["target_ratio"] == pytest.approx(1.03)
