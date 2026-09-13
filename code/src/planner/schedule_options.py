from __future__ import annotations
from datetime import date, timedelta, datetime

from src.data.models import (
    Request, UserProfile, PaymentOption, RecurringStream, Plan
)
from src.simulation.solvers import check_installments_feasible


def fmt_amount(amount: float) -> str:
    if amount == int(amount):
        return str(int(amount))
    return str(round(amount, 2))


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def add_installment_plans(
    plans: list[Plan],
    request: Request,
    profile: UserProfile,
    base_balance: float,
    pending_debit_total: float,
    scheduled_flows: list[tuple[date, float]],
    streams: list[RecurringStream],
    payment_options: list[PaymentOption],
    min_bal: float,
    safe_amt: float,
    earliest: str,
) -> None:
    if "installments" not in profile.payment_methods_user_will_consider:
        return
    req_date = request.request_date
    deadline = request.desired_completion_date
    max_months = profile.max_installment_months

    installment_opts = [o for o in payment_options if o.payment_method == "installments"]
    for opt in installment_opts:
        if max_months is not None and opt.number_of_payments > max_months:
            continue
        freq_days = int(opt.payment_frequency_days or 30)
        payment_dates = [
            opt.first_payment_date + timedelta(days=i * freq_days)
            for i in range(opt.number_of_payments)
        ]
        outflows = [(dt, opt.payment_amount) for dt in payment_dates]
        feasible = check_installments_feasible(
            base_balance=base_balance,
            pending_debit_total=pending_debit_total,
            scheduled_flows=scheduled_flows,
            streams=streams,
            request_date=req_date,
            payment_dates_amounts=outflows,
            min_balance=min_bal,
        )
        last_date = payment_dates[-1]
        plan_str = "|".join(f"{dt.isoformat()}:{fmt_amount(opt.payment_amount)}" for dt in payment_dates)
        plans.append(Plan(
            method="installments",
            affordability_status="affordable_with_plan",
            amount_safe_to_pay=safe_amt,
            earliest_date_for_full_payment=earliest,
            payment_plan=plan_str,
            spending_changes=[],
            total_amount_paid=opt.total_payable_amount,
            first_payment_date=opt.first_payment_date,
            num_payments=opt.number_of_payments,
            payment_option_id=opt.payment_option_id,
            completes_by_deadline=last_date <= deadline,
            passes_90_day_check=feasible,
        ))


def add_partial_payment_plans(
    plans: list[Plan],
    request: Request,
    profile: UserProfile,
    base_balance: float,
    pending_debit_total: float,
    scheduled_flows: list[tuple[date, float]],
    streams: list[RecurringStream],
    safe_amt: float,
    earliest: str,
    min_bal: float,
) -> None:
    if "partial_payment" not in profile.payment_methods_user_will_consider:
        return
    if not request.allows_partial_payment:
        return
    if safe_amt <= 0 or safe_amt >= request.requested_amount:
        return
    if not earliest:
        return
    earliest_date = parse_date(earliest)
    if earliest_date > request.desired_completion_date:
        return

    req_amt = request.requested_amount
    p1 = safe_amt
    p2 = round(req_amt - p1, 2)
    plan_str = f"{request.request_date.isoformat()}:{fmt_amount(p1)}|{earliest}:{fmt_amount(p2)}"
    plans.append(Plan(
        method="partial_payment",
        affordability_status="affordable_with_plan",
        amount_safe_to_pay=p1,
        earliest_date_for_full_payment=earliest,
        payment_plan=plan_str,
        spending_changes=[],
        total_amount_paid=req_amt,
        first_payment_date=request.request_date,
        num_payments=2,
        payment_option_id=None,
        completes_by_deadline=earliest_date <= request.desired_completion_date,
        passes_90_day_check=True,
    ))
