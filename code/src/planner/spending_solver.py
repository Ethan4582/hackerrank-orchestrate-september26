from __future__ import annotations
from itertools import combinations
from datetime import date, timedelta

from src.data.models import (
    RecurringStream, SpendingChange, FinancialEvent
)
from src.simulation.engine import simulate


def find_spending_changes(
    base_balance: float,
    pending_debit_total: float,
    scheduled_flows: list[tuple[date, float]],
    streams: list[RecurringStream],
    request_date: date,
    min_balance: float,
    extra_outflows: list[tuple[date, float]],
    candidate_streams: list[RecurringStream],
    stop_categories: list[str],
    reduce_categories: list[str],
) -> list[SpendingChange]:
    candidates: list[SpendingChange] = []

    for stream in candidate_streams:
        if "stoppable" in stream.flexibility and stream.category in stop_categories:
            candidates.append(SpendingChange(action="stop", event_id=stream.event_id))
        if "reducible" in stream.flexibility and stream.category in reduce_categories:
            if stream.minimum_allowed_amount is not None:
                candidates.append(SpendingChange(
                    action="reduce_to",
                    event_id=stream.event_id,
                    new_amount=stream.minimum_allowed_amount,
                ))

    for size in range(1, min(4, len(candidates) + 1)):
        for subset in combinations(candidates, size):
            event_ids_in_subset = [sc.event_id for sc in subset]
            if len(event_ids_in_subset) != len(set(event_ids_in_subset)):
                continue
            trial = simulate(
                base_balance=base_balance,
                pending_debit_total=pending_debit_total,
                scheduled_flows=scheduled_flows,
                streams=streams,
                request_date=request_date,
                horizon=90,
                extra_outflows=extra_outflows,
                spending_overrides=list(subset),
            )
            if min(trial) >= min_balance:
                return list(subset)

    return []
