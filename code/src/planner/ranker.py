from __future__ import annotations
from datetime import date
from src.data.models import Plan


def rank(plans: list[Plan]) -> Plan:
    passing = [p for p in plans if p.passes_90_day_check and p.method != "not_recommended"]
    if not passing:
        not_rec = [p for p in plans if p.method == "not_recommended"]
        return not_rec[0] if not_rec else plans[-1]

    return min(passing, key=lambda p: (
        not p.completes_by_deadline,
        len(p.spending_changes) > 0,
        p.total_amount_paid,
        p.first_payment_date or date.max,
        p.num_payments,
        p.payment_option_id or "zzzzz",
    ))
