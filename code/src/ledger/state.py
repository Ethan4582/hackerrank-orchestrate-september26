from __future__ import annotations
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import TYPE_CHECKING

from src.data.models import FinancialEvent, ExchangeRate, RecurringStream, MessageEffect
from src.data.currency import convert_to_home

if TYPE_CHECKING:
    pass


def normalize_description(desc: str) -> str:
    desc = desc.lower()
    desc = re.sub(r"\d+", "", desc)
    desc = re.sub(r"\b(the|a|an|and|or|of|in|on|at|to|for|is|was|my|your|our)\b", "", desc)
    desc = re.sub(r"\s+", " ", desc).strip()
    return desc


def build_active_events(
    events: list[FinancialEvent],
    image_amounts: dict[str, float],
) -> list[FinancialEvent]:
    resolved = list(events)

    for ev in resolved:
        if ev.event_id in image_amounts and ev.amount is None:
            ev.amount = image_amounts[ev.event_id]

    parent_superseded: set[str] = set()
    parent_child: dict[str, list[FinancialEvent]] = defaultdict(list)
    ev_by_id: dict[str, FinancialEvent] = {e.event_id: e for e in resolved}

    for ev in resolved:
        if ev.linked_event_id and ev.linked_event_id in ev_by_id:
            parent_child[ev.linked_event_id].append(ev)

    internal_transfer_ids: set[str] = set()
    for parent_id, children in parent_child.items():
        parent = ev_by_id.get(parent_id)
        if parent is None:
            continue
        for child in children:
            if child.status in ("settled", "cancelled"):
                parent_superseded.add(parent_id)
            if child.status == "cancelled":
                internal_transfer_ids.add(child.event_id)

    for parent_id, children in parent_child.items():
        parent = ev_by_id.get(parent_id)
        if parent is None or parent.amount is None:
            continue
        for child in children:
            if child.amount is None:
                continue
            if (
                parent.user_id == child.user_id
                and abs(parent.amount - child.amount) < 0.01
                and parent.direction != child.direction
                and parent.settlement_date == child.settlement_date
            ):
                internal_transfer_ids.add(parent_id)
                internal_transfer_ids.add(child.event_id)

    active = [
        ev for ev in resolved
        if ev.event_id not in parent_superseded
        and ev.event_id not in internal_transfer_ids
        and ev.status not in ("failed", "cancelled", "unrealized")
    ]
    return active


def compute_pending_debit_total(
    events: list[FinancialEvent],
    home_currency: str,
    rates: list[ExchangeRate],
    as_of: date,
) -> float:
    total = 0.0
    for ev in events:
        if ev.status == "pending" and ev.direction == "debit" and ev.amount is not None:
            converted = convert_to_home(ev.amount, ev.currency, home_currency, ev.settlement_date, rates)
            total += converted
    return total


def compute_scheduled_flows(
    events: list[FinancialEvent],
    home_currency: str,
    rates: list[ExchangeRate],
    from_date: date,
    to_date: date,
) -> list[tuple[date, float]]:
    flows = []
    for ev in events:
        if ev.status not in ("settled", "scheduled"):
            continue
        if ev.amount is None:
            continue
        if not (from_date <= ev.settlement_date <= to_date):
            continue
        converted = convert_to_home(ev.amount, ev.currency, home_currency, ev.settlement_date, rates)
        signed = converted if ev.direction == "credit" else -converted
        flows.append((ev.settlement_date, signed))
    return flows
