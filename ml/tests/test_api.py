import json

import pytest
from fastapi.testclient import TestClient

from metrixs_ml.api import create_app

ROW = {"approvedPlan": None, "bonusBasis": "recommended_plan", "contributions": []}
PLANS = [
    {**ROW, "agent": "Агент А", "quarter": "2025Q1", "kind": "completed", "isForecast": False, "recommendedPlan": 100_000, "fact": 110_000, "refundShare": 0.01},
    {**ROW, "agent": "Агент А", "quarter": "2025Q2", "kind": "completed", "isForecast": False, "recommendedPlan": 100_000, "fact": 90_000, "refundShare": 0.01},
    {**ROW, "agent": "Агент А", "quarter": "2025Q3", "kind": "forecast", "isForecast": True, "recommendedPlan": 120_000, "fact": None, "refundShare": None, "bonusBasis": None},
]
METRICS = {"chosen": "ridge", "scores": [], "agents": ["Агент А"], "forecastQuarter": "2025Q3"}
CONFIG = {"rate": 0.05, "threshold": 0.0, "cap_per_quarter": 150000, "max_refund_share": 0.1, "refund_penalty": 0.5}


@pytest.fixture
def client(tmp_path):
    (tmp_path / "plans.json").write_text(json.dumps(PLANS, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "metrics.json").write_text(json.dumps(METRICS, ensure_ascii=False), encoding="utf-8")
    config = tmp_path / "bonus.json"
    config.write_text(json.dumps(CONFIG), encoding="utf-8")
    with TestClient(create_app(artifacts_dir=tmp_path, bonus_config_file=config)) as test_client:
        yield test_client


def test_plans_include_bonus_for_completed_quarters_only(client):
    data = client.get("/plans", params={"agent": "Агент А"}).json()["data"]

    assert data[0]["bonus"]["amount"] == pytest.approx(500)
    assert data[1]["bonus"]["amount"] == 0
    assert data[2]["kind"] == "forecast" and data[2]["bonus"] is None


def test_bonuses_aggregate_completed_quarters_per_agent(client):
    data = client.get("/bonuses", params={"year": "2025"}).json()["data"]

    assert data == [
        {"agent": "Агент А", "bonus": 500.0, "recommendedPlan": 200000.0, "fact": 200000.0, "quarters": 2, "completion": 1.0}
    ]


def test_forecast_has_no_bonus_and_states_limitation(client):
    data = client.get("/forecast").json()["data"]

    assert data["quarter"] == "2025Q3"
    assert data["totalRecommendedPlan"] == pytest.approx(120_000)
    assert "bonus" not in data["rows"][0]
    assert "премия по построению будет 0" in data["limitation"]


def test_scenarios_use_config_and_forecast_plan(client):
    data = client.get("/bonus/scenarios", params={"agent": "Агент А"}).json()["data"]

    assert data["demo"] is True and data["plan"] == pytest.approx(120_000)
    assert data["config"] == CONFIG
    amounts = {s["key"]: s["amount"] for s in data["scenarios"]}
    assert amounts["shortfall"] == 0 and amounts["at_cap"] == pytest.approx(150_000)


def test_bonus_forecast_curve_marks_forecast_threshold_and_cap(client):
    data = client.get("/bonus/forecast", params={"agent": "Агент А"}).json()["data"]

    assert data["forecastCollections"] == pytest.approx(120_000)
    assert data["forecastBonus"] == 0  # plan = forecast, so no overperformance by construction
    assert data["capReachedAt"] == pytest.approx(120_000 + 150_000 / 0.05)
    bonuses = [p["bonus"] for p in data["curve"]]
    assert bonuses == sorted(bonuses) and max(bonuses) == pytest.approx(150_000)
    assert any(p["fact"] == pytest.approx(data["threshold"]) and p["bonus"] == 0 for p in data["curve"])
    # amounts are rounded to kopecks after the multiplier, so allow one kopeck
    assert all(p["bonus_high_refunds"] == pytest.approx(p["bonus"] * 0.5, abs=0.01) for p in data["curve"])
    assert data["lastQuarter"] == "2025Q2"


def test_root_redirects_to_docs(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307 and response.headers["location"] == "/docs"


def test_rejects_unknown_agent_and_bad_year(client):
    assert client.get("/plans", params={"agent": "Чужой"}).status_code == 400
    assert client.get("/plans", params={"year": "20x5"}).status_code == 400
    assert client.get("/bonus/scenarios", params={"agent": "Чужой"}).status_code == 400
