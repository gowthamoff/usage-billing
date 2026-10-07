"""Proves overage rating bills only units over allowance and rounds once per line, not per unit."""

from decimal import Decimal

from app.domain.rating import PlanMeterRate, rate_meter, rate_period


def test_no_overage_costs_nothing():
    line = rate_meter("api_calls", 5000, 10000, Decimal("50.000000"))
    assert line.overage_units == 0
    assert line.amount_minor == 0
    assert line.quantity == 5000
    assert line.allowance == 10000


def test_overage_is_units_over_allowance_times_rate():
    line = rate_meter("api_calls", 12000, 10000, Decimal("50.000000"))
    assert line.overage_units == 2000
    assert line.amount_minor == 100_000  # 2,000 x ₹0.50 = ₹1,000.00
    assert line.rate_minor == Decimal("50.000000")


def test_sub_paisa_rate_rounds_once_on_the_line_total():
    line = rate_meter("api_calls", 1234, 0, Decimal("0.2"))
    assert line.amount_minor == 247  # 246.8 paise, not 1234 x round(0.2) = 0


def test_rounding_happens_once_not_per_unit():
    assert rate_meter("m", 3, 0, Decimal("0.5")).amount_minor == 2  # 1.5 -> 2, per-unit rounding would give 3
    assert rate_meter("m", 3, 0, Decimal("0.4")).amount_minor == 1  # 1.2 -> 1, per-unit rounding would give 0


def test_amount_is_int_never_float():
    assert isinstance(rate_meter("m", 7, 1, Decimal("33.333333")).amount_minor, int)


def test_rate_period_emits_one_line_per_plan_meter_in_plan_order():
    plan = [
        PlanMeterRate("api_calls", 10000, Decimal("50.000000")),
        PlanMeterRate("storage_gb", 10, Decimal("300.000000")),
    ]
    lines = rate_period({"storage_gb": 13, "unpriced_meter": 99}, plan)
    assert [line.meter_id for line in lines] == ["api_calls", "storage_gb"]
    assert lines[0].quantity == 0 and lines[0].amount_minor == 0
    assert lines[1].overage_units == 3 and lines[1].amount_minor == 900
