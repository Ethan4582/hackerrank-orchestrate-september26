from __future__ import annotations
import calendar
import statistics
from collections import defaultdict
from datetime import date, timedelta

from src.data.models import FinancialEvent, RecurringStream, MessageEffect, ExchangeRate, UserProfile


COMMITMENT_CATS = {
    "salary", "rent", "utilities", "insurance", "housing", "education",
    "debt_repayment", "healthcare", "family_support", "groceries", "transport",
    "music_subscription", "cloud_storage", "gym", "delivery_membership", "streaming"
}


def add_month(d: date, n: int = 1) -> date:
    year = d.year
    month = d.month + n
    while month > 12:
        year += 1
        month -= 12
    while month < 1:
        year -= 1
        month += 12
    max_days = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, max_days))


def _get_rate(rates: list[ExchangeRate], rate_date: date, from_curr: str, to_curr: str) -> float:
    if from_curr == to_curr:
        return 1.0
    candidates = [
        r for r in rates
        if r.from_currency == from_curr and r.to_currency == to_curr and r.rate_date <= rate_date
    ]
    if candidates:
        candidates.sort(key=lambda x: x.rate_date, reverse=True)
        return candidates[0].rate
    return 1.0


def _convert(amt: float, from_curr: str, to_curr: str, dt: date, rates: list[ExchangeRate]) -> float:
    return amt * _get_rate(rates, dt, from_curr, to_curr)


def _longest_consistent_chain(events: list[FinancialEvent], tolerance_ratio: float = 0.35) -> list[FinancialEvent]:
    n = len(events)
    if n < 2:
        return events
    best = [events[0]]
    for start in range(n):
        chain = [events[start]]
        for i in range(start + 1, n):
            cand = events[i]
            gap = (cand.settlement_date - chain[-1].settlement_date).days
            if len(chain) == 1:
                chain.append(cand)
                continue
            gaps = [(chain[j + 1].settlement_date - chain[j].settlement_date).days for j in range(len(chain) - 1)]
            med = statistics.median(gaps)
            if med > 0 and abs(gap - med) <= med * tolerance_ratio:
                chain.append(cand)
            else:
                break
        if len(chain) > len(best):
            best = chain
    return best


def detect_recurring_streams(
    events: list[FinancialEvent],
    user_id: str,
    home_currency: str = "USD",
    rates: list[ExchangeRate] | None = None,
    profile: UserProfile | None = None,
) -> list[RecurringStream]:
    if rates is None:
        rates = []
    user_events = [e for e in events if e.user_id == user_id]
    streams: list[RecurringStream] = []

    salaries = [
        e for e in user_events
        if e.category == "salary" and e.status in ("settled", "scheduled") and e.amount is not None
        and "commission" not in e.description.lower() and "bonus" not in e.description.lower()
    ]
    if salaries:
        salaries.sort(key=lambda x: x.settlement_date)
        chain_sal = _longest_consistent_chain(salaries)
        last_sal = chain_sal[-1]
        if "final" not in last_sal.description.lower():
            recent_amts = [_convert(e.amount, e.currency, home_currency, e.settlement_date, rates) for e in chain_sal[-3:]]
            amt = statistics.median(recent_amts)
            doms = [e.settlement_date.day for e in chain_sal]
            mode_dom = max(set(doms), key=doms.count)
            ref_date = date(last_sal.settlement_date.year, last_sal.settlement_date.month, mode_dom)
            streams.append(RecurringStream(
                stream_id=f"{user_id}_salary",
                user_id=user_id,
                category="salary",
                direction="credit",
                description=last_sal.description,
                amount=amt,
                currency=home_currency,
                period_days=30,
                last_settlement_date=ref_date,
                event_id=last_sal.event_id,
                flexibility="fixed",
                minimum_allowed_amount=None,
            ))

    settled_evs = [
        e for e in user_events
        if e.status == "settled" and e.amount is not None and e.category != "salary"
    ]
    cat_groups: dict[str, list[FinancialEvent]] = defaultdict(list)
    for e in settled_evs:
        cat_groups[e.category].append(e)

    for cat, ev_list in cat_groups.items():
        if len(ev_list) < 2:
            continue
        is_reducible = profile and cat in profile.expense_categories_user_is_willing_to_reduce
        is_stoppable = profile and cat in profile.expense_categories_user_is_willing_to_stop
        if cat not in COMMITMENT_CATS and not is_reducible and not is_stoppable:
            continue

        ev_sorted = sorted(ev_list, key=lambda x: x.settlement_date)
        chain = _longest_consistent_chain(ev_sorted)
        if len(chain) < 2:
            continue
        gaps = [(chain[i + 1].settlement_date - chain[i].settlement_date).days for i in range(len(chain) - 1)]
        med_gap = round(statistics.median(gaps))
        if med_gap < 5:
            continue

        last_ev = chain[-1]
        if cat in ("groceries", "transport", "dining"):
            cat_amts = [_convert(float(e.amount), e.currency, home_currency, e.settlement_date, rates) for e in chain if e.amount is not None]
            amt = statistics.median(cat_amts) if cat_amts else _convert(last_ev.amount, last_ev.currency, home_currency, last_ev.settlement_date, rates)
        else:
            recent = [_convert(float(e.amount), e.currency, home_currency, e.settlement_date, rates) for e in chain[-3:] if e.amount is not None]
            amt = statistics.median(recent) if recent else _convert(last_ev.amount, last_ev.currency, home_currency, last_ev.settlement_date, rates)

        streams.append(RecurringStream(
            stream_id=f"{user_id}_{cat}_{last_ev.event_id}",
            user_id=user_id,
            category=cat,
            direction=last_ev.direction,
            description=last_ev.description,
            amount=amt,
            currency=home_currency,
            period_days=med_gap,
            last_settlement_date=last_ev.settlement_date,
            event_id=last_ev.event_id,
            flexibility=last_ev.flexibility,
            minimum_allowed_amount=last_ev.minimum_allowed_amount,
        ))

    return streams


def apply_message_effects(
    streams: list[RecurringStream],
    effects: list[MessageEffect],
    user_id: str,
    request_date: date,
) -> list[RecurringStream]:
    result = list(streams)
    for effect in effects:
        if effect.user_id != user_id:
            continue
        if effect.effect_type == "salary_change":
            ref_eid = effect.event_id_reference
            for i, stream in enumerate(result):
                if stream.user_id != user_id:
                    continue
                if stream.category in ("salary", "income", "employment"):
                    if ref_eid is None or stream.event_id == ref_eid:
                        if effect.new_amount is not None:
                            result[i] = RecurringStream(
                                **{**stream.__dict__, "amount": effect.new_amount}
                            )
                        break

        elif effect.effect_type == "salary_end":
            ref_eid = effect.event_id_reference
            to_remove = []
            for i, stream in enumerate(result):
                if stream.user_id != user_id:
                    continue
                if stream.category in ("salary", "income", "employment"):
                    if ref_eid is None or stream.event_id == ref_eid:
                        to_remove.append(i)
            for idx in reversed(to_remove):
                result.pop(idx)

        elif effect.effect_type == "salary_date_change":
            if effect.effective_date is not None:
                for i, stream in enumerate(result):
                    if stream.user_id == user_id and stream.category in ("salary", "income", "employment"):
                        ref_d = add_month(effect.effective_date, -1) if effect.effective_date >= request_date else effect.effective_date
                        result[i] = RecurringStream(
                            **{**stream.__dict__, "last_settlement_date": ref_d}
                        )
                        break

        elif effect.effect_type == "rent_change":
            if effect.new_amount is not None:
                pct = effect.new_amount
                for i, stream in enumerate(result):
                    if stream.user_id == user_id and stream.category == "rent":
                        new_amt = round(stream.amount * (1 + pct / 100), 2)
                        result[i] = RecurringStream(**{**stream.__dict__, "amount": new_amt})
                        break

    return result


def project_recurring_flows(
    streams: list[RecurringStream],
    from_date: date,
    to_date: date,
) -> list[tuple[date, float, RecurringStream]]:
    flows: list[tuple[date, float, RecurringStream]] = []
    for s in streams:
        if s.period_days in (28, 29, 30, 31):
            cur = s.last_settlement_date
            while True:
                cur = add_month(cur, 1)
                if cur > to_date:
                    break
                if cur >= from_date:
                    signed = s.amount if s.direction == "credit" else -s.amount
                    flows.append((cur, signed, s))
        else:
            step = max(1, s.period_days)
            cur = s.last_settlement_date
            while True:
                cur = cur + timedelta(days=step)
                if cur > to_date:
                    break
                if cur >= from_date:
                    signed = s.amount if s.direction == "credit" else -s.amount
                    flows.append((cur, signed, s))
    return flows
