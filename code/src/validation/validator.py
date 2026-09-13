from __future__ import annotations
import csv
from pathlib import Path
from src.data.models import OutputRow


VALID_STATUS = {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}
VALID_METHODS = {"full_payment", "partial_payment", "installments", "wait", "not_recommended"}
VALID_CURRENCIES = {"ZAR", "IDR", "INR", "EUR", "USD", "GBP", "AUD", "SGD"}


def validate_output(
    rows: list[OutputRow],
    requests_by_id: dict,
    payment_options_by_rid: dict,
    events_by_id: dict,
    recurring_event_ids: set,
) -> list[str]:
    errors: list[str] = []
    expected_ids = set(requests_by_id.keys())
    actual_ids = {r.request_id for r in rows}

    expected_count = len(expected_ids)
    if len(rows) != expected_count:
        errors.append(f"R01: expected {expected_count} rows, got {len(rows)}")
    missing = expected_ids - actual_ids
    if missing:
        errors.append(f"R01: missing request_ids: {list(missing)[:5]}")

    for row in rows:
        rid = row.request_id
        req = requests_by_id.get(rid)
        if req is None:
            continue

        if not (0 <= row.amount_safe_to_pay <= req.requested_amount + 0.02):
            errors.append(f"R03 [{rid}]: amount_safe_to_pay={row.amount_safe_to_pay} out of range [0, {req.requested_amount}]")

        if row.affordability_status not in VALID_STATUS:
            errors.append(f"R04 [{rid}]: invalid affordability_status={row.affordability_status}")

        if row.recommended_payment_method not in VALID_METHODS:
            errors.append(f"R05 [{rid}]: invalid method={row.recommended_payment_method}")

        if row.affordability_status == "affordable_now" and row.earliest_date_for_full_payment != req.request_date.isoformat():
            errors.append(f"R07 [{rid}]: affordable_now but earliest_date={row.earliest_date_for_full_payment} != {req.request_date.isoformat()}")

        if row.affordability_status == "not_affordable" and row.earliest_date_for_full_payment != "":
            errors.append(f"R08 [{rid}]: not_affordable but earliest_date not empty")

        if row.recommended_payment_method == "not_recommended" and row.payment_plan != "none":
            errors.append(f"R09 [{rid}]: not_recommended but payment_plan={row.payment_plan}")

        if row.recommended_payment_method == "partial_payment":
            parts = row.payment_plan.split("|")
            if len(parts) != 2:
                errors.append(f"R10 [{rid}]: partial_payment must have 2 payments, got {len(parts)}")
            else:
                p1_amt = float(parts[0].split(":")[1])
                p2_amt = float(parts[1].split(":")[1])
                total = round(p1_amt + p2_amt, 2)
                if abs(total - req.requested_amount) > 0.02:
                    errors.append(f"R10 [{rid}]: partial payments {p1_amt}+{p2_amt}={total} != {req.requested_amount}")

        if row.spending_changes_needed != "none":
            changes = row.spending_changes_needed.split("|")
            seen_ids = set()
            for change in changes:
                if change.startswith("stop:"):
                    eid = change[5:]
                    if eid in seen_ids:
                        errors.append(f"R13 [{rid}]: event_id {eid} appears multiple times in spending_changes")
                    seen_ids.add(eid)
                elif change.startswith("reduce_to:"):
                    parts2 = change.split(":")
                    if len(parts2) >= 2:
                        eid = parts2[1]
                        if eid in seen_ids:
                            errors.append(f"R13 [{rid}]: event_id {eid} appears in both stop and reduce_to")
                        seen_ids.add(eid)

        if not row.decision_explanation or len(row.decision_explanation) < 20:
            errors.append(f"R14 [{rid}]: explanation too short")

        has_currency = any(c in row.decision_explanation for c in VALID_CURRENCIES)
        if not has_currency:
            errors.append(f"R14 [{rid}]: explanation missing currency code")

    return errors


def write_output_csv(rows: list[OutputRow], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "request_id", "amount_safe_to_pay", "affordability_status",
            "recommended_payment_method", "payment_plan",
            "earliest_date_for_full_payment", "spending_changes_needed",
            "decision_explanation",
        ])
        for row in rows:
            writer.writerow([
                row.request_id,
                row.amount_safe_to_pay,
                row.affordability_status,
                row.recommended_payment_method,
                row.payment_plan,
                row.earliest_date_for_full_payment,
                row.spending_changes_needed,
                row.decision_explanation,
            ])
