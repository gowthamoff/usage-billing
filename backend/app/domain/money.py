"""Money helpers. Amounts are integer minor units (paise); rates are Decimal minor units per unit."""

from decimal import ROUND_HALF_UP, Decimal

_ONE = Decimal(1)
_PAISA = Decimal("0.01")
_HUNDRED = Decimal(100)


def to_minor(value: Decimal) -> int:
    """Round a Decimal minor-unit amount to whole paise, half up. Call once per invoice line."""
    return int(value.quantize(_ONE, rounding=ROUND_HALF_UP))


def format_inr(minor: int) -> str:
    """Format a minor-unit amount as rupees, e.g. ₹1,234.56."""
    sign = "-" if minor < 0 else ""
    rupees, paise = divmod(abs(minor), 100)
    return f"{sign}₹{rupees:,}.{paise:02d}"


def format_inr_rate(rate_minor: Decimal) -> str:
    """Format a per-unit rate in rupees; two decimals unless finer than a paisa (e.g. ₹0.002)."""
    rupees = rate_minor / _HUNDRED
    whole_paise = rupees.quantize(_PAISA)
    text = f"{whole_paise:,.2f}" if whole_paise == rupees else f"{rupees.normalize():,f}"
    return f"₹{text}"
