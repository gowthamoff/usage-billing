"""Proves minor-unit rounding is half-up to int and INR formatting of amounts and rates."""

from decimal import Decimal

from app.domain.money import format_inr, format_inr_rate, to_minor


def test_to_minor_rounds_half_up():
    assert to_minor(Decimal("246.8")) == 247
    assert to_minor(Decimal("246.4")) == 246
    assert to_minor(Decimal("0.5")) == 1
    assert to_minor(Decimal("2.5")) == 3
    assert to_minor(Decimal("100")) == 100


def test_to_minor_returns_int():
    assert isinstance(to_minor(Decimal("1.0")), int)


def test_format_inr():
    assert format_inr(100000) == "₹1,000.00"
    assert format_inr(5) == "₹0.05"
    assert format_inr(0) == "₹0.00"
    assert format_inr(-250) == "-₹2.50"
    assert format_inr(123456789) == "₹1,234,567.89"


def test_format_inr_rate():
    assert format_inr_rate(Decimal("50.000000")) == "₹0.50"
    assert format_inr_rate(Decimal("300.000000")) == "₹3.00"
    assert format_inr_rate(Decimal("0.2")) == "₹0.002"
