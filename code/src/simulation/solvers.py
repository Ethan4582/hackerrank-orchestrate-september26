from __future__ import annotations
from datetime import date, timedelta

from src.data.models import RecurringStream, SpendingChange
from src.simulation.engine import simulate


def solve_amount_safe_to_pay(
    baseline: list[float],
    min_balance: float,
    requested_amount: float,
) -> float:
    headroom = min(baseline) - min_balance
    return max(0.0, min(headroom, requested_amount))


def solve_earliest_date(
    base_balance: float,
    pending_debit_total: float,
    scheduled_flows: list[tuple[date, float]],
    streams: list[RecurringStream],
    request_date: date,
    requested_amount: float,
    min_balance: float,
    spending_overrides: list[SpendingChange] | None = None,
    horizon: int = 90,
) -> str:
    for d in range(horizon + 1):
        candidate_date = request_date + timedelta(days=d)
        trial = simulate(
            base_balance=base_balance,
            pending_debit_total=pending_debit_total,
            scheduled_flows=scheduled_flows,
            streams=streams,
            request_date=request_date,
            horizon=horizon,
            extra_outflows=[(candidate_date, requested_amount)],
            spending_overrides=spending_overrides,
        )
        if min(trial[d:]) >= min_balance:
            return candidate_date.isoformat()
    return ""


def check_installments_feasible(
    base_balance: float,
    pending_debit_total: float,
    scheduled_flows: list[tuple[date, float]],
    streams: list[RecurringStream],
    request_date: date,
    payment_dates_amounts: list[tuple[date, float]],
    min_balance: float,
    spending_overrides: list[SpendingChange] | None = None,
) -> bool:
    if not payment_dates_amounts:
        return True
    last_dt = max(dt for dt, _ in payment_dates_amounts)
    max_day = max(0, (last_dt - request_date).days)
    horizon = max(90, max_day)
    trial = simulate(
        base_balance=base_balance,
        pending_debit_total=pending_debit_total,
        scheduled_flows=scheduled_flows,
        streams=streams,
        request_date=request_date,
        horizon=horizon,
        extra_outflows=payment_dates_amounts,
        spending_overrides=spending_overrides,
    )
    return min(trial[:max_day + 1]) >= min_balance
