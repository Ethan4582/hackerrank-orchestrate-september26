from __future__ import annotations
from datetime import date, timedelta

from src.data.models import (
    Request, UserProfile, PaymentOption, RecurringStream, SpendingChange, Plan
)
from src.simulation.engine import simulate
from src.simulation.solvers import (
    solve_amount_safe_to_pay, solve_earliest_date, check_installments_feasible
)
from src.planner.spending_solver import find_spending_changes
from src.planner.schedule_options import (
    add_installment_plans, add_partial_payment_plans, fmt_amount, parse_date
)


def build_all_plans(
    request: Request,
    profile: UserProfile,
    base_balance: float,
    pending_debit_total: float,
    scheduled_flows: list[tuple[date, float]],
    streams: list[RecurringStream],
    payment_options: list[PaymentOption],
) -> list[Plan]:
    min_bal = profile.minimum_balance_to_keep
    req_amt = request.requested_amount
    req_date = request.request_date
    deadline = request.desired_completion_date
    methods = profile.payment_methods_user_will_consider

    baseline = simulate(
        base_balance=base_balance,
        pending_debit_total=pending_debit_total,
        scheduled_flows=scheduled_flows,
        streams=streams,
        request_date=req_date,
    )

    safe_amt = solve_amount_safe_to_pay(baseline, min_bal, req_amt)
    if safe_amt >= req_amt:
        earliest = req_date.isoformat()
    else:
        earliest = solve_earliest_date(
            base_balance=base_balance,
            pending_debit_total=pending_debit_total,
            scheduled_flows=scheduled_flows,
            streams=streams,
            request_date=req_date,
            requested_amount=req_amt,
            min_balance=min_bal,
        )

    plans: list[Plan] = []
    candidate_streams_for_spending = [
        s for s in streams
        if s.flexibility in ("stoppable", "reducible")
    ]

    _add_full_payment_plans(
        plans, request, profile, base_balance, pending_debit_total,
        scheduled_flows, streams, payment_options, safe_amt, earliest,
        candidate_streams_for_spending,
    )

    _add_wait_plans(plans, request, profile, earliest, safe_amt)

    add_installment_plans(
        plans, request, profile, base_balance, pending_debit_total,
        scheduled_flows, streams, payment_options, min_bal, safe_amt, earliest,
    )

    add_partial_payment_plans(
        plans, request, profile, base_balance, pending_debit_total,
        scheduled_flows, streams, safe_amt, earliest, min_bal,
    )

    plans.append(_make_not_recommended(request, safe_amt, earliest, min_bal))

    return plans


def _add_full_payment_plans(
    plans, request, profile, base_balance, pending_debit_total,
    scheduled_flows, streams, payment_options, safe_amt, earliest,
    candidate_streams,
):
    if "full_payment" not in profile.payment_methods_user_will_consider:
        return
    req_amt = request.requested_amount
    req_date = request.request_date
    deadline = request.desired_completion_date
    min_bal = profile.minimum_balance_to_keep

    full_opts = [o for o in payment_options if o.payment_method == "full_payment"]
    pay_date_str = full_opts[0].first_payment_date.isoformat() if full_opts else req_date.isoformat()
    pay_date = full_opts[0].first_payment_date if full_opts else req_date

    if safe_amt >= req_amt:
        plans.append(Plan(
            method="full_payment",
            affordability_status="affordable_now",
            amount_safe_to_pay=req_amt,
            earliest_date_for_full_payment=req_date.isoformat(),
            payment_plan=f"{pay_date_str}:{fmt_amount(req_amt)}",
            spending_changes=[],
            total_amount_paid=req_amt,
            first_payment_date=pay_date,
            num_payments=1,
            payment_option_id=full_opts[0].payment_option_id if full_opts else None,
            completes_by_deadline=pay_date <= deadline,
            passes_90_day_check=True,
        ))

    spending_changes = find_spending_changes(
        base_balance=base_balance,
        pending_debit_total=pending_debit_total,
        scheduled_flows=scheduled_flows,
        streams=streams,
        request_date=req_date,
        min_balance=min_bal,
        extra_outflows=[(pay_date, req_amt)],
        candidate_streams=candidate_streams,
        stop_categories=profile.expense_categories_user_is_willing_to_stop,
        reduce_categories=profile.expense_categories_user_is_willing_to_reduce,
    )
    if spending_changes and safe_amt < req_amt:
        plans.append(Plan(
            method="full_payment",
            affordability_status="affordable_with_plan",
            amount_safe_to_pay=safe_amt,
            earliest_date_for_full_payment=earliest,
            payment_plan=f"{pay_date_str}:{fmt_amount(req_amt)}",
            spending_changes=spending_changes,
            total_amount_paid=req_amt,
            first_payment_date=pay_date,
            num_payments=1,
            payment_option_id=full_opts[0].payment_option_id if full_opts else None,
            completes_by_deadline=pay_date <= deadline,
            passes_90_day_check=True,
        ))


def _add_wait_plans(plans, request, profile, earliest, safe_amt):
    if "full_payment" not in profile.payment_methods_user_will_consider:
        return
    if not earliest:
        return
    earliest_date = parse_date(earliest)
    deadline = request.desired_completion_date
    req_date = request.request_date
    if earliest_date <= req_date:
        return
    plans.append(Plan(
        method="wait",
        affordability_status="affordable_later",
        amount_safe_to_pay=safe_amt,
        earliest_date_for_full_payment=earliest,
        payment_plan=f"{earliest}:{fmt_amount(request.requested_amount)}",
        spending_changes=[],
        total_amount_paid=request.requested_amount,
        first_payment_date=earliest_date,
        num_payments=1,
        payment_option_id=None,
        completes_by_deadline=earliest_date <= deadline,
        passes_90_day_check=True,
    ))


def _make_not_recommended(request, safe_amt, earliest, min_bal) -> Plan:
    return Plan(
        method="not_recommended",
        affordability_status="not_affordable",
        amount_safe_to_pay=safe_amt,
        earliest_date_for_full_payment="",
        payment_plan="none",
        spending_changes=[],
        total_amount_paid=0.0,
        first_payment_date=None,
        num_payments=0,
        payment_option_id=None,
        completes_by_deadline=False,
        passes_90_day_check=False,
    )
