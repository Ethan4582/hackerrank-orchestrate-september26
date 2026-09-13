from __future__ import annotations
from datetime import date
from src.data.models import ExchangeRate


def convert_to_home(
    amount: float,
    from_currency: str,
    home_currency: str,
    settlement_date: date,
    rates: list[ExchangeRate],
) -> float:
    if from_currency == home_currency:
        return amount
    candidates = [
        r for r in rates
        if r.from_currency == from_currency
        and r.to_currency == home_currency
        and r.rate_date <= settlement_date
    ]
    if candidates:
        rate = max(candidates, key=lambda r: r.rate_date).rate
        return round(amount * rate, 2)
    reverse = [
        r for r in rates
        if r.from_currency == home_currency
        and r.to_currency == from_currency
        and r.rate_date <= settlement_date
    ]
    if reverse:
        rate = max(reverse, key=lambda r: r.rate_date).rate
        return round(amount / rate, 2)
    result = _try_via_usd(amount, from_currency, home_currency, settlement_date, rates)
    if result is not None:
        return result
    raise ValueError(
        f"No FX rate for {from_currency}→{home_currency} on or before {settlement_date}"
    )


def _try_via_usd(
    amount: float,
    from_currency: str,
    home_currency: str,
    settlement_date: date,
    rates: list[ExchangeRate],
) -> float | None:
    if from_currency == "USD" or home_currency == "USD":
        return None
    via_usd = _floor_rate(from_currency, "USD", settlement_date, rates)
    usd_to_home = _floor_rate("USD", home_currency, settlement_date, rates)
    if via_usd is not None and usd_to_home is not None:
        return round(amount * via_usd * usd_to_home, 2)
    return None


def _floor_rate(
    from_cur: str, to_cur: str, as_of: date, rates: list[ExchangeRate]
) -> float | None:
    candidates = [
        r for r in rates
        if r.from_currency == from_cur and r.to_currency == to_cur and r.rate_date <= as_of
    ]
    if candidates:
        return max(candidates, key=lambda r: r.rate_date).rate
    reverse = [
        r for r in rates
        if r.from_currency == to_cur and r.to_currency == from_cur and r.rate_date <= as_of
    ]
    if reverse:
        return 1.0 / max(reverse, key=lambda r: r.rate_date).rate
    return None
