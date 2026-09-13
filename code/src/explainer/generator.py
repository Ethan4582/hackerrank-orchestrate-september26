from __future__ import annotations
from src.data.models import Plan, OutputRow, SpendingChange


def _fmt_amount(amount: float, currency: str) -> str:
    if amount == int(amount):
        formatted = f"{int(amount):,}"
    else:
        formatted = f"{amount:,.2f}"
    return f"{currency} {formatted}"


def _spending_desc(sc: SpendingChange, streams_by_eid: dict) -> str:
    stream = streams_by_eid.get(sc.event_id)
    return stream.description if stream else sc.event_id


def generate_explanation(
    plan: Plan,
    currency: str,
    min_balance: float,
    streams_by_eid: dict,
    request_deadline: str = "",
    requested_amount: float = 0.0,
) -> str:
    method = plan.method
    status = plan.affordability_status
    amt = plan.amount_safe_to_pay
    cur = currency
    min_b = min_balance

    if method == "not_recommended":
        if amt > 0:
            return (
                f"Do not proceed with the {_fmt_amount(requested_amount, cur)} request. "
                f"Although {_fmt_amount(amt, cur)} is available today, "
                f"the full amount cannot be completed safely within 90 days."
            )
        return (
            f"Do not make this payment by {request_deadline}. "
            f"None of the available options keeps the {_fmt_amount(min_b, cur)} minimum protected."
        )

    if method == "wait":
        earliest = plan.earliest_date_for_full_payment
        return (
            f"Pay {_fmt_amount(plan.total_amount_paid, cur)} in full on {earliest}. "
            f"Paying earlier would take the balance below the {_fmt_amount(min_b, cur)} minimum."
        )

    if method == "partial_payment":
        parts = plan.payment_plan.split("|")
        p1_parts = parts[0].split(":")
        p2_parts = parts[1].split(":") if len(parts) > 1 else []
        p1_amt = float(p1_parts[1]) if len(p1_parts) > 1 else amt
        p2_date = p2_parts[0] if p2_parts else ""
        p2_amt = float(p2_parts[1]) if len(p2_parts) > 1 else 0.0
        return (
            f"Pay {_fmt_amount(p1_amt, cur)} today and the remaining {_fmt_amount(p2_amt, cur)} on {p2_date}. "
            f"This completes the full request and keeps the {_fmt_amount(min_b, cur)} minimum protected."
        )

    if method == "installments":
        parts = plan.payment_plan.split("|")
        n = len(parts)
        first_parts = parts[0].split(":")
        inst_amt = float(first_parts[1]) if len(first_parts) > 1 else 0.0
        start_date = first_parts[0] if first_parts else ""
        return (
            f"Use {n} installments of {_fmt_amount(inst_amt, cur)}, starting {start_date}. "
            f"This leaves at least {_fmt_amount(min_b, cur)} available."
        )

    if method == "full_payment":
        changes = plan.spending_changes
        if not changes:
            return (
                f"Pay {_fmt_amount(amt, cur)} today. "
                f"This leaves at least {_fmt_amount(min_b, cur)} available over the next 90 days."
            )
        stops = [sc for sc in changes if sc.action == "stop"]
        reduces = [sc for sc in changes if sc.action == "reduce_to"]
        parts = []
        for sc in stops:
            desc = _spending_desc(sc, streams_by_eid)
            parts.append(f"Stop the {desc}")
        for sc in reduces:
            desc = _spending_desc(sc, streams_by_eid)
            new_a = sc.new_amount or 0.0
            parts.append(f"reduce the {desc} to {_fmt_amount(new_a, cur)}")
        prefix = ", and ".join(parts) if len(parts) > 1 else parts[0]
        prefix = prefix[0].upper() + prefix[1:]
        return (
            f"{prefix}, then pay {_fmt_amount(plan.total_amount_paid, cur)} today. "
            f"This leaves at least {_fmt_amount(min_b, cur)} available."
        )

    return f"Pay {_fmt_amount(amt, cur)} today."


def build_output_row(
    request_id: str,
    plan: Plan,
    currency: str,
    min_balance: float,
    streams_by_eid: dict,
    request_deadline: str,
    requested_amount: float,
) -> OutputRow:
    explanation = generate_explanation(
        plan=plan,
        currency=currency,
        min_balance=min_balance,
        streams_by_eid=streams_by_eid,
        request_deadline=request_deadline,
        requested_amount=requested_amount,
    )
    spending_str = "|".join(sc.to_str() for sc in plan.spending_changes) or "none"
    earliest = plan.earliest_date_for_full_payment
    if plan.method == "not_recommended":
        earliest = ""

    return OutputRow(
        request_id=request_id,
        amount_safe_to_pay=round(plan.amount_safe_to_pay, 2),
        affordability_status=plan.affordability_status,
        recommended_payment_method=plan.method,
        payment_plan=plan.payment_plan,
        earliest_date_for_full_payment=earliest,
        spending_changes_needed=spending_str,
        decision_explanation=explanation,
    )
