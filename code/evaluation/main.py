from __future__ import annotations
import csv
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

DATASET_DIR = Path(__file__).parent.parent.parent / "dataset"
SAMPLE_PATH = DATASET_DIR / "sample_requests.csv"
GOLDEN_FIELDS = [
    "affordability_status", "recommended_payment_method",
    "amount_safe_to_pay", "earliest_date_for_full_payment",
    "spending_changes_needed",
]


def load_golden() -> list[dict]:
    rows = []
    with open(SAMPLE_PATH, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(dict(r))
    return rows


def run_benchmark(predicted_path: Path = None) -> None:
    from main import run
    if predicted_path is None:
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        predicted_path = Path(tmp.name)
        sample_requests = DATASET_DIR / "sample_requests.csv"
        run(requests_path=sample_requests, output_path=predicted_path)

    golden = load_golden()
    golden_by_id = {r["request_id"]: r for r in golden}

    with open(predicted_path, newline="", encoding="utf-8") as f:
        predicted = list(csv.DictReader(f))

    total = 0
    correct = 0
    mismatches = []

    for pred in predicted:
        rid = pred["request_id"]
        gold = golden_by_id.get(rid)
        if gold is None:
            continue
        total += 1
        row_ok = True
        for field in GOLDEN_FIELDS:
            g_val = gold.get(field, "").strip()
            p_val = pred.get(field, "").strip()
            if field == "amount_safe_to_pay":
                try:
                    if abs(float(g_val) - float(p_val)) > 0.02:
                        mismatches.append(f"{rid} {field}: expected={g_val} got={p_val}")
                        row_ok = False
                except ValueError:
                    pass
            else:
                if g_val != p_val:
                    mismatches.append(f"{rid} {field}: expected='{g_val}' got='{p_val}'")
                    row_ok = False
        if row_ok:
            correct += 1

    print(f"\n=== Benchmark Results ===")
    print(f"Correct: {correct}/{total} ({100*correct//max(total,1)}%)")
    if mismatches:
        print("\nMismatches:")
        for m in mismatches[:30]:
            print(f"  {m}")
    else:
        print("All golden samples matched perfectly!")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--predicted", type=Path, default=None)
    parser.add_argument("--mode", choices=["benchmark", "report"], default="benchmark")
    args = parser.parse_args()
    if args.mode == "benchmark":
        run_benchmark(args.predicted)
    elif args.mode == "report":
        from src.evidence.ocr_engine import get_metrics
        import json
        print(json.dumps(get_metrics(), indent=2))
