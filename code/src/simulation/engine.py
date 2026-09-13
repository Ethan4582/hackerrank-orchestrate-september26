from __future__ import annotations
from datetime import date, timedelta

from src.data.models import RecurringStream, SpendingChange
from src.ledger.recurring import project_recurring_flows


def simulate(
    base_balance: float,
    pending_debit_total: float,
    scheduled_flows: list[tuple[date, float]],
    streams: list[RecurringStream],
    request_date: date,
    horizon: int = 90,
    extra_outflows: list[tuple[date, float]] | None = None,
    spending_overrides: list[SpendingChange] | None = None,
) -> list[float]:
    if extra_outflows is None:
        extra_outflows = []
    if spending_overrides is None:
        spending_overrides = []

    stop_ids = {sc.event_id for sc in spending_overrides if sc.action == "stop"}
    reduce_map = {sc.event_id: sc.new_amount for sc in spending_overrides if sc.action == "reduce_to"}

    end_date = request_date + timedelta(days=horizon)
    recurring_flows = project_recurring_flows(streams, request_date, end_date)

    extra_by_date: dict[date, float] = {}
    for dt, amt in extra_outflows:
        extra_by_date[dt] = extra_by_date.get(dt, 0.0) + amt

    scheduled_by_date: dict[date, float] = {}
    for dt, signed in scheduled_flows:
        scheduled_by_date[dt] = scheduled_by_date.get(dt, 0.0) + signed

    recurring_by_date: dict[date, float] = {}
    for dt, signed, stream in recurring_flows:
        if stream.event_id in stop_ids:
            continue
        if stream.event_id in reduce_map:
            new_amt = reduce_map[stream.event_id]
            signed = new_amt if stream.direction == "credit" else -new_amt
        recurring_by_date[dt] = recurring_by_date.get(dt, 0.0) + signed

    balances: list[float] = [0.0] * (horizon + 1)
    balances[0] = (
        base_balance
        - pending_debit_total
        + scheduled_by_date.get(request_date, 0.0)
        + recurring_by_date.get(request_date, 0.0)
        - extra_by_date.get(request_date, 0.0)
    )

    for d in range(1, horizon + 1):
        current_date = request_date + timedelta(days=d)
        balances[d] = (
            balances[d - 1]
            + scheduled_by_date.get(current_date, 0.0)
            + recurring_by_date.get(current_date, 0.0)
            - extra_by_date.get(current_date, 0.0)
        )

    return balances
