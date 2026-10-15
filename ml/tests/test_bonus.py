import pytest

from metrixs_ml.bonus import BonusConfig, calculate_bonus, demo_scenarios

CONFIG = BonusConfig(rate=0.05, threshold=0.0, cap_per_quarter=1_000, max_refund_share=0.1, refund_penalty=0.5)


def test_no_bonus_when_plan_not_met():
    result = calculate_bonus(plan=100_000, fact=90_000, refund_share=0.0, config=CONFIG)

    assert result.amount == 0
    assert result.completion == pytest.approx(0.9)


def test_bonus_is_rate_of_overperformance():
    result = calculate_bonus(plan=100_000, fact=110_000, refund_share=0.0, config=CONFIG)

    assert result.overperformance == pytest.approx(10_000)
    assert result.amount == pytest.approx(500)


def test_bonus_is_capped():
    result = calculate_bonus(plan=100_000, fact=200_000, refund_share=0.0, config=CONFIG)

    assert result.amount == pytest.approx(1_000)
    assert result.capped


def test_threshold_raises_the_bar():
    config = CONFIG.model_copy(update={"threshold": 0.05})

    result = calculate_bonus(plan=100_000, fact=110_000, refund_share=0.0, config=config)

    assert result.overperformance == pytest.approx(5_000)


def test_high_refund_share_halves_bonus():
    result = calculate_bonus(plan=100_000, fact=110_000, refund_share=0.2, config=CONFIG)

    assert result.refund_penalized
    assert result.amount == pytest.approx(250)


def test_rejects_non_positive_plan():
    with pytest.raises(ValueError):
        calculate_bonus(plan=0, fact=1, refund_share=0.0, config=CONFIG)


def test_demo_scenarios_hit_every_boundary():
    plan = 1_000_000
    s = {sc.key: sc.result for sc in demo_scenarios(plan, CONFIG)}

    assert s["shortfall"].amount == 0
    assert s["at_threshold"].amount == 0 and s["at_threshold"].completion == pytest.approx(1.0)
    assert s["over"].amount == pytest.approx(CONFIG.cap_per_quarter / 2)
    assert s["at_cap"].amount == pytest.approx(CONFIG.cap_per_quarter) and not s["at_cap"].capped
    assert s["above_cap"].amount == pytest.approx(CONFIG.cap_per_quarter) and s["above_cap"].capped
    assert not s["refunds_at_limit"].refund_penalized  # rule is «above» the share, not «at»
    assert s["refunds_over_limit"].refund_penalized
    assert s["refunds_over_limit"].amount == pytest.approx(s["over"].amount * CONFIG.refund_penalty)


def test_demo_scenarios_follow_config_changes():
    config = CONFIG.model_copy(update={"threshold": 0.1, "cap_per_quarter": 500})

    s = {sc.key: sc for sc in demo_scenarios(100_000, config)}

    assert s["at_threshold"].fact == pytest.approx(110_000)
    assert s["at_cap"].result.amount == pytest.approx(500)


def test_demo_scenarios_skip_overperformance_when_rate_is_zero():
    keys = [sc.key for sc in demo_scenarios(100_000, CONFIG.model_copy(update={"rate": 0.0}))]

    assert keys == ["shortfall", "at_threshold"]


def test_config_rejects_unknown_and_out_of_range_fields():
    with pytest.raises(ValueError):
        BonusConfig(rate=2, threshold=0, cap_per_quarter=1, max_refund_share=0.1, refund_penalty=0.5)
    with pytest.raises(ValueError):
        BonusConfig.model_validate(
            {"rate": 0.1, "threshold": 0, "cap_per_quarter": 1, "max_refund_share": 0.1, "refund_penalty": 0.5, "x": 1}
        )
