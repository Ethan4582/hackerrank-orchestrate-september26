from __future__ import annotations
import csv
from datetime import date, datetime
from pathlib import Path
from src.data.models import (
    Request, UserProfile, FinancialEvent, PaymentOption,
    ExchangeRate,
)


def _parse_date(s: str) -> date:
    s = s.strip()
    if not s:
        return date(1970, 1, 1)
    return datetime.strptime(s, "%Y-%m-%d").date()



def _parse_float_or_none(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    return float(s)


def _parse_int_or_none(s: str) -> int | None:
    s = s.strip()
    if not s:
        return None
    return int(float(s))


def _parse_bool(s: str) -> bool:
    return s.strip().lower() in ("true", "1", "yes")


def _parse_pipe_list(s: str) -> list[str]:
    s = s.strip()
    if not s:
        return []
    return [x.strip() for x in s.split("|") if x.strip()]


def load_requests(path: Path) -> list[Request]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(Request(
                request_id=r["request_id"].strip(),
                user_id=r["user_id"].strip(),
                request_date=_parse_date(r["request_date"]),
                request_type=r["request_type"].strip(),
                requested_amount=float(r["requested_amount"]),
                desired_completion_date=_parse_date(r["desired_completion_date"]),
                allows_partial_payment=_parse_bool(r["allows_partial_payment"]),
                request_text=r["request_text"].strip(),
            ))
    return rows


def load_profiles(path: Path) -> dict[str, UserProfile]:
    profiles: dict[str, UserProfile] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            uid = r["user_id"].strip()
            profiles[uid] = UserProfile(
                user_id=uid,
                home_currency=r["home_currency"].strip(),
                current_available_balance=float(r["current_available_balance"]),
                minimum_balance_to_keep=float(r["minimum_balance_to_keep"]),
                financial_priorities=_parse_pipe_list(r["financial_priorities"]),
                expense_categories_to_protect=_parse_pipe_list(r["expense_categories_to_protect"]),
                expense_categories_user_is_willing_to_reduce=_parse_pipe_list(r["expense_categories_user_is_willing_to_reduce"]),
                expense_categories_user_is_willing_to_stop=_parse_pipe_list(r["expense_categories_user_is_willing_to_stop"]),
                payment_methods_user_will_consider=_parse_pipe_list(r["payment_methods_user_will_consider"]),
                max_installment_months=_parse_int_or_none(r["max_installment_months"]),
            )
    return profiles


def load_events(path: Path) -> list[FinancialEvent]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(FinancialEvent(
                event_id=r["event_id"].strip(),
                user_id=r["user_id"].strip(),
                event_type=r["event_type"].strip(),
                description=r["description"].strip(),
                category=r["category"].strip(),
                direction=r["direction"].strip(),
                amount=_parse_float_or_none(r["amount"]),
                currency=r["currency"].strip(),
                event_date=_parse_date(r["event_date"]),
                settlement_date=_parse_date(r["settlement_date"]),
                status=r["status"].strip(),
                linked_event_id=r["linked_event_id"].strip() or None,
                flexibility=r["flexibility"].strip(),
                minimum_allowed_amount=_parse_float_or_none(r["minimum_allowed_amount"]),
            ))
    return rows


def load_payment_options(path: Path) -> dict[str, list[PaymentOption]]:
    opts: dict[str, list[PaymentOption]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rid = r["request_id"].strip()
            opt = PaymentOption(
                payment_option_id=r["payment_option_id"].strip(),
                request_id=rid,
                payment_method=r["payment_method"].strip(),
                payment_amount=float(r["payment_amount"]),
                number_of_payments=int(r["number_of_payments"]),
                first_payment_date=_parse_date(r["first_payment_date"]),
                payment_frequency_days=_parse_int_or_none(r["payment_frequency_days"]),
                financing_fee=float(r["financing_fee"]),
                total_payable_amount=float(r["total_payable_amount"]),
            )
            opts.setdefault(rid, []).append(opt)
    return opts


def load_exchange_rates(path: Path) -> list[ExchangeRate]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(ExchangeRate(
                rate_date=_parse_date(r["rate_date"]),
                from_currency=r["from_currency"].strip(),
                to_currency=r["to_currency"].strip(),
                rate=float(r["rate"]),
            ))
    return rows


def load_messages(path: Path) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(dict(r))
    return rows


def load_images(path: Path) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(dict(r))
    return rows
