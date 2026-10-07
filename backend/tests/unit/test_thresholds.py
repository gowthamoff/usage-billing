"""Proves threshold crossing detection and the percent-used to usage-state band mapping."""

from decimal import Decimal

from app.domain.thresholds import (
    APPROACHING_LIMIT,
    IN_OVERAGE,
    WITHIN_ALLOWANCE,
    crossed_thresholds,
    percent_used,
    usage_state,
)


def test_crossing_from_zero_to_85_fires_50_and_80():
    assert crossed_thresholds(0, 85, 100) == [50, 80]


def test_moving_within_the_same_band_fires_nothing():
    assert crossed_thresholds(85, 90, 100) == []


def test_crossing_100_fires_only_100():
    assert crossed_thresholds(95, 120, 100) == [100]


def test_landing_exactly_on_a_threshold_fires_it():
    assert crossed_thresholds(4999, 5000, 10000) == [50]
    assert crossed_thresholds(5000, 5001, 10000) == []


def test_one_jump_can_fire_every_threshold():
    assert crossed_thresholds(0, 10000, 10000) == [50, 80, 100]


def test_no_change_or_zero_allowance_fires_nothing():
    assert crossed_thresholds(50, 50, 100) == []
    assert crossed_thresholds(0, 5, 0) == []


def test_custom_thresholds_are_honoured_in_order():
    assert crossed_thresholds(0, 100, 100, thresholds=(90, 10)) == [10, 90]


def test_usage_state_bands():
    assert usage_state(0) == WITHIN_ALLOWANCE
    assert usage_state(Decimal("79.99")) == WITHIN_ALLOWANCE
    assert usage_state(80) == APPROACHING_LIMIT
    assert usage_state(Decimal("99.99")) == APPROACHING_LIMIT
    assert usage_state(100) == IN_OVERAGE
    assert usage_state(250) == IN_OVERAGE


def test_percent_used_truncates_so_display_never_crosses_a_band_early():
    assert percent_used(99999, 100000) == Decimal("99.99")
    assert usage_state(percent_used(99999, 100000)) == APPROACHING_LIMIT
    assert percent_used(12000, 10000) == Decimal("120.00")
    assert percent_used(0, 0) == Decimal(0)
    assert percent_used(1, 0) == Decimal(100)
