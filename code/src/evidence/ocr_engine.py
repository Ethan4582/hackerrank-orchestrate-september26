from __future__ import annotations
import base64
import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_PATH = Path(__file__).parent / "cache" / "image_amounts.json"
DATASET_IMAGES = Path(__file__).parent.parent.parent.parent / "dataset" / "media" / "images"


_metrics: dict = {
    "model": "mistral-ocr-latest",
    "provider": "Mistral AI",
    "calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cost_usd": 0.0,
    "cache_hits": 0,
}

AMOUNT_PATTERNS = [
    r"(?:Net\s+Salary|Total\s+Due|Amount\s+Due|Grand\s+Total|Total\s+Amount|Total|Amount)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
]
FALLBACK_NUMBER = re.compile(r"\b([\d]{3,}(?:[,.][\d]+)*)\b")


def _extract_amount_from_text(text: str) -> float | None:
    for pat in AMOUNT_PATTERNS:
        matches = re.findall(pat, text, re.IGNORECASE)
        if matches:
            nums = [float(m.replace(",", "")) for m in matches]
            return max(nums)
    numbers = FALLBACK_NUMBER.findall(text)
    if numbers:
        nums = [float(n.replace(",", "").replace(".", "")) if "," in n else float(n.replace(",", "")) for n in numbers]
        return max(nums)
    return None


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def extract_amount(event_id: str, image_id: str) -> float | None:
    use_cache = os.getenv("CACHE_EVIDENCE", "true").lower() in ("true", "1")
    cache = _load_cache()

    if use_cache and event_id in cache:
        _metrics["cache_hits"] += 1
        return float(cache[event_id])

    amount = _try_mistral(image_id)
    if amount is None:
        amount = _try_gemini(image_id)
    if amount is None:
        amount = _try_openai(image_id)

    if amount is not None and amount > 0:
        cache[event_id] = amount
        _save_cache(cache)

    return amount


def _image_b64(image_id: str) -> str:
    img_path = DATASET_IMAGES / f"{image_id}.png"
    with open(img_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _try_mistral(image_id: str) -> float | None:
    api_key = os.getenv("MISTRAL_API_KEY", "")
    if not api_key:
        return None
    try:
        from mistralai import Mistral
        client = Mistral(api_key=api_key)
        b64 = _image_b64(image_id)
        resp = client.ocr.process(
            model="mistral-ocr-latest",
            document={"type": "image_url", "image_url": f"data:image/png;base64,{b64}"},
        )
        _metrics["calls"] += 1
        text = ""
        for page in resp.pages:
            text += page.markdown + "\n"
        return _extract_amount_from_text(text)
    except Exception as e:
        logger.warning("Mistral OCR failed for %s: %s", image_id, e)
        return None


def _try_gemini(image_id: str) -> float | None:
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        img_path = DATASET_IMAGES / f"{image_id}.png"
        from PIL import Image
        img = Image.open(img_path)
        resp = model.generate_content([
            "Extract the total payable amount from this document as a single number. "
            "Return only the number, no units or symbols.",
            img,
        ])
        _metrics["calls"] += 1
        text = resp.text.strip()
        return float(text.replace(",", ""))
    except Exception as e:
        logger.warning("Gemini OCR failed for %s: %s", image_id, e)
        return None


def _try_openai(image_id: str) -> float | None:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        b64 = _image_b64(image_id)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "Extract the total payable amount from this document. Return only the number."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]}],
            max_tokens=50,
        )
        _metrics["calls"] += 1
        text = resp.choices[0].message.content.strip()
        return float(text.replace(",", ""))
    except Exception as e:
        logger.warning("OpenAI OCR failed for %s: %s", image_id, e)
        return None


def get_metrics() -> dict:
    return dict(_metrics)


def populate_cache_for_all_images(images_meta: list[dict]) -> dict:
    results = {}
    for img in images_meta:
        image_id = img["image_id"]
        event_id = img["related_event_id"]
        amount = extract_amount(event_id, image_id)
        results[event_id] = amount
        logger.info("OCR %s → event %s → %s", image_id, event_id, amount)
    return results
