from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date


@dataclass
class Request:
    request_id: str
    user_id: str
    request_date: date
    request_type: str
    requested_amount: float
    desired_completion_date: date
    allows_partial_payment: bool
    request_text: str


@dataclass
class UserProfile:
    user_id: str
    home_currency: str
    current_available_balance: float
    minimum_balance_to_keep: float
    financial_priorities: list[str]
    expense_categories_to_protect: list[str]
    expense_categories_user_is_willing_to_reduce: list[str]
    expense_categories_user_is_willing_to_stop: list[str]
    payment_methods_user_will_consider: list[str]
    max_installment_months: int | None


@dataclass
class FinancialEvent:
    event_id: str
    user_id: str
    event_type: str
    description: str
    category: str
    direction: str
    amount: float | None
    currency: str
    event_date: date
    settlement_date: date
    status: str
    linked_event_id: str | None
    flexibility: str
    minimum_allowed_amount: float | None


@dataclass
class PaymentOption:
    payment_option_id: str
    request_id: str
    payment_method: str
    payment_amount: float
    number_of_payments: int
    first_payment_date: date
    payment_frequency_days: int | None
    financing_fee: float
    total_payable_amount: float


@dataclass
class ExchangeRate:
    rate_date: date
    from_currency: str
    to_currency: str
    rate: float


@dataclass
class MessageEffect:
    effect_type: str
    user_id: str
    effective_date: date | None
    new_amount: float | None
    event_id_reference: str | None
    source_message_id: str = ""


@dataclass
class RecurringStream:
    stream_id: str
    user_id: str
    category: str
    direction: str
    description: str
    amount: float
    currency: str
    period_days: int
    last_settlement_date: date
    event_id: str
    flexibility: str
    minimum_allowed_amount: float | None


@dataclass
class SpendingChange:
    action: str
    event_id: str
    new_amount: float | None = None

    def to_str(self) -> str:
        if self.action == "stop":
            return f"stop:{self.event_id}"
        return f"reduce_to:{self.event_id}:{self.new_amount}"


@dataclass
class Plan:
    method: str
    affordability_status: str
    amount_safe_to_pay: float
    earliest_date_for_full_payment: str
    payment_plan: str
    spending_changes: list[SpendingChange]
    total_amount_paid: float
    first_payment_date: date | None
    num_payments: int
    payment_option_id: str | None
    completes_by_deadline: bool
    passes_90_day_check: bool
    min_balance_headroom: float = 0.0


@dataclass
class OutputRow:
    request_id: str
    amount_safe_to_pay: float
    affordability_status: str
    recommended_payment_method: str
    payment_plan: str
    earliest_date_for_full_payment: str
    spending_changes_needed: str
    decision_explanation: str
