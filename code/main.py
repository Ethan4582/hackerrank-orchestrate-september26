from __future__ import annotations
import logging
import os
import sys
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
sys.path.insert(0, str(Path(__file__).parent))

from src.data.loader import (
    load_requests, load_profiles, load_events,
    load_payment_options, load_exchange_rates,
    load_messages, load_images,
)
from src.data.models import OutputRow
from src.evidence.ocr_engine import extract_amount
from src.evidence.message_parser import parse_all_messages
from src.ledger.state import (
    build_active_events, compute_pending_debit_total, compute_scheduled_flows
)
from src.ledger.recurring import (
    detect_recurring_streams, apply_message_effects
)
from src.planner.candidate_gen import build_all_plans
from src.planner.ranker import rank
from src.explainer.generator import build_output_row
from src.validation.validator import validate_output, write_output_csv

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DATASET_DIR = Path(__file__).parent.parent / "dataset"
OUTPUT_PATH = Path(__file__).parent.parent / "output.csv"


def run(requests_path: Path = None, output_path: Path = None) -> list[OutputRow]:
    req_path = requests_path or DATASET_DIR / "requests.csv"
    out_path = output_path or OUTPUT_PATH

    logger.info("Loading dataset...")
    requests = load_requests(req_path)
    profiles = load_profiles(DATASET_DIR / "financial_profiles.csv")
    events = load_events(DATASET_DIR / "financial_events.csv")
    payment_options_all = load_payment_options(DATASET_DIR / "request_payment_options.csv")
    rates = load_exchange_rates(DATASET_DIR / "exchange_rates.csv")
    messages = load_messages(DATASET_DIR / "messages.csv")
    images_meta = load_images(DATASET_DIR / "images.csv")

    logger.info("Resolving OCR for %d image events...", len(images_meta))
    image_amounts: dict[str, float] = {}
    for img in images_meta:
        amount = extract_amount(img["related_event_id"], img["image_id"])
        if amount is not None:
            image_amounts[img["related_event_id"]] = amount

    logger.info("Parsing messages...")
    message_effects_by_user = parse_all_messages(messages)

    logger.info("Building active events...")
    active_events = build_active_events(events, image_amounts)

    events_by_id = {e.event_id: e for e in events}
    events_by_user: dict[str, list] = {}
    for ev in active_events:
        events_by_user.setdefault(ev.user_id, []).append(ev)

    output_rows: list[OutputRow] = []

    for i, req in enumerate(requests):
        uid = req.user_id
        profile = profiles.get(uid)
        if profile is None:
            logger.error("No profile for user %s (request %s)", uid, req.request_id)
            continue

        user_events = events_by_user.get(uid, [])
        end_90 = req.request_date + timedelta(days=90)

        pending_debit = compute_pending_debit_total(
            user_events, profile.home_currency, rates, req.request_date
        )
        scheduled_flows = compute_scheduled_flows(
            user_events, profile.home_currency, rates, req.request_date, end_90
        )
        streams = detect_recurring_streams(
            user_events, uid,
            home_currency=profile.home_currency,
            rates=rates,
            profile=profile,
        )
        user_effects = message_effects_by_user.get(uid, [])
        streams = apply_message_effects(streams, user_effects, uid, req.request_date)

        payment_opts = payment_options_all.get(req.request_id, [])

        plans = build_all_plans(
            request=req,
            profile=profile,
            base_balance=profile.current_available_balance,
            pending_debit_total=pending_debit,
            scheduled_flows=scheduled_flows,
            streams=streams,
            payment_options=payment_opts,
        )

        best_plan = rank(plans)
        streams_by_eid = {s.event_id: s for s in streams}

        row = build_output_row(
            request_id=req.request_id,
            plan=best_plan,
            currency=profile.home_currency,
            min_balance=profile.minimum_balance_to_keep,
            streams_by_eid=streams_by_eid,
            request_deadline=req.desired_completion_date.isoformat(),
            requested_amount=req.requested_amount,
        )
        output_rows.append(row)

        if (i + 1) % 25 == 0:
            logger.info("Processed %d/%d requests", i + 1, len(requests))

    logger.info("Validating output...")
    requests_by_id = {r.request_id: r for r in requests}
    errors = validate_output(
        rows=output_rows,
        requests_by_id=requests_by_id,
        payment_options_by_rid=payment_options_all,
        events_by_id=events_by_id,
        recurring_event_ids=set(),
    )
    if errors:
        for e in errors:
            logger.warning("Validation: %s", e)
    else:
        logger.info("All validation rules passed.")

    write_output_csv(output_rows, out_path)
    logger.info("Output written to %s", out_path)
    return output_rows


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Buy or Wait? Financial Decision Agent")
    parser.add_argument("--requests", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    run(requests_path=args.requests, output_path=args.output)
