from __future__ import annotations
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from src.data.models import MessageEffect

logger = logging.getLogger(__name__)

CACHE_PATH = Path(__file__).parent / "cache" / "message_effects.json"

_ID_SALARY_CHANGE = re.compile(
    r"(?:Gaji\s+(?:bulanan|pokok|rutin|sementara|pertama)?(?:\s+Anda)?(?:\s+sebesar)?(?:\s+yang\s+dikonfirmasi)?)\s+(?:naik\s+menjadi|adalah|untuk\s+penggajian\s+berikutnya\s+adalah)?\s*(?:[A-Z]{3}\s+)?([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
_ID_EFFECTIVE_DATE = re.compile(
    r"(?:berlaku\s+mulai|dikonfirmasi\s+untuk|dijadwalkan\s+pada|diperkirakan\s+masuk\s+pada)\s+(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_ID_SALARY_END = re.compile(
    r"Salah\s+satu\s+sumber\s+pendapatan\s+kerja.*?telah\s+berakhir|telah\s+berakhir",
    re.IGNORECASE | re.DOTALL,
)
_ID_PENDING = re.compile(
    r"belum\s+(?:disetujui|dikonfirmasi)|masih\s+(?:menunggu|tertunda)", re.IGNORECASE
)

_EN_SALARY_INCREASE = re.compile(
    r"(?:monthly|regular)\s+salary\s+has\s+increased\s+to\s+(?:[A-Z]{3}\s+)?([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
_EN_SALARY_NEXT = re.compile(
    r"(?:(?:regular|temporary|next|first|remaining\s+confirmed\s+monthly|confirmed\s+base)\s+(?:salary|pay)|first\s+salary\s+from\s+the\s+new\s+employer|salary\s+of|first\s+salary\s+of)\s+(?:for\s+the\s+next\s+payroll\s+)?(?:is\s+reduced\s+to|will\s+be|is|resumes)\s+(?:[A-Z]{3}\s+)?([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
_EN_SALARY_DATE = re.compile(
    r"(?:expected\s+on|updated\s+to|credit\s+date\s+is|confirmed\s+for|scheduled\s+for)\s+(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_EN_SALARY_RESUME = re.compile(
    r"[Rr]egular\s+salary.*?resumes\s+on\s+(\d{4}-\d{2}-\d{2})", re.IGNORECASE | re.DOTALL
)
_EN_SALARY_END = re.compile(
    r"(?:seasonal\s+contract|employment\s+record|employment)\s+has\s+ended|No\s+off-season\s+income",
    re.IGNORECASE,
)
_EN_RENT_CHANGE = re.compile(
    r"increases?\s+(?:monthly\s+)?rent\s+by\s+([\d.]+)\s*%", re.IGNORECASE
)
_EN_INTERNAL_TRANSFER = re.compile(
    r"transfer\s+between\s+your\s+two\s+accounts", re.IGNORECASE
)
_EN_REFUND_PENDING = re.compile(
    r"refund\s+has\s+been\s+initiated\s+but\s+has\s+not\s+reached", re.IGNORECASE
)
_EN_PENDING_CREDIT = re.compile(
    r"payout\s+is\s+still\s+pending|balance\s+isn'?t\s+withdrawable", re.IGNORECASE
)
_EN_PRIZE_SETTLED = re.compile(
    r"prize\s+proceeds\s+have\s+reached\s+your\s+account", re.IGNORECASE
)


def _parse_amount(s: str) -> float:
    return float(s.replace(",", ""))


def _parse_date_str(s: str) -> datetime | None:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d")
    except Exception:
        return None


def parse_message(msg: dict) -> list[MessageEffect]:
    text = msg.get("message_text", "")
    uid = msg.get("user_id", "")
    mid = msg.get("message_id", "")
    effects: list[MessageEffect] = []

    m = _ID_SALARY_CHANGE.search(text)
    if m:
        amount = _parse_amount(m.group(1))
        ed = _ID_EFFECTIVE_DATE.search(text)
        eff_date = _parse_date_str(ed.group(1)).date() if ed else None
        effects.append(MessageEffect(
            effect_type="salary_change", user_id=uid,
            effective_date=eff_date, new_amount=amount,
            event_id_reference=msg.get("related_event_id") or None,
            source_message_id=mid,
        ))
        return effects

    if _ID_PENDING.search(text):
        effects.append(MessageEffect(
            effect_type="pending_credit_ignore", user_id=uid,
            effective_date=None, new_amount=None,
            event_id_reference=msg.get("related_event_id") or None,
            source_message_id=mid,
        ))
        return effects

    if _ID_SALARY_END.search(text):
        effects.append(MessageEffect(
            effect_type="salary_end", user_id=uid,
            effective_date=None, new_amount=None,
            event_id_reference=msg.get("related_event_id") or None,
            source_message_id=mid,
        ))
        return effects

    m = _EN_SALARY_INCREASE.search(text)
    if m:
        amount = _parse_amount(m.group(1))
        effects.append(MessageEffect(
            effect_type="salary_change", user_id=uid,
            effective_date=None, new_amount=amount,
            event_id_reference=msg.get("related_event_id") or None,
            source_message_id=mid,
        ))
        return effects

    m = _EN_SALARY_NEXT.search(text)
    if m:
        amount = _parse_amount(m.group(1))
        effects.append(MessageEffect(
            effect_type="salary_change", user_id=uid,
            effective_date=None, new_amount=amount,
            event_id_reference=msg.get("related_event_id") or None,
            source_message_id=mid,
        ))
        return effects

    m_date = _EN_SALARY_DATE.search(text)
    if m_date and not any(k in text.lower() for k in ("resumes", "ended")):
        dt_val = _parse_date_str(m_date.group(1))
        if dt_val:
            effects.append(MessageEffect(
                effect_type="salary_date_change", user_id=uid,
                effective_date=dt_val.date(), new_amount=None,
                event_id_reference=msg.get("related_event_id") or None,
                source_message_id=mid,
            ))
            if not any(k in text.lower() for k in ("increase", "reduced", "salary of", "first salary")):
                return effects

    m_res = _EN_SALARY_RESUME.search(text)
    if m_res:
        eff_date = _parse_date_str(m_res.group(1))
        effects.append(MessageEffect(
            effect_type="salary_resume", user_id=uid,
            effective_date=eff_date.date() if eff_date else None,
            new_amount=None,
            event_id_reference=msg.get("related_event_id") or None,
            source_message_id=mid,
        ))
        return effects

    if _EN_SALARY_END.search(text):
        ref_eid = msg.get("related_event_id") or None
        effects.append(MessageEffect(
            effect_type="salary_end", user_id=uid,
            effective_date=None, new_amount=None,
            event_id_reference=ref_eid,
            source_message_id=mid,
        ))
        return effects

    m = _EN_RENT_CHANGE.search(text)
    if m:
        pct = float(m.group(1))
        effects.append(MessageEffect(
            effect_type="rent_change", user_id=uid,
            effective_date=None, new_amount=pct,
            event_id_reference=msg.get("related_event_id") or None,
            source_message_id=mid,
        ))
        return effects

    if _EN_INTERNAL_TRANSFER.search(text):
        effects.append(MessageEffect(
            effect_type="internal_transfer", user_id=uid,
            effective_date=None, new_amount=None,
            event_id_reference=msg.get("related_event_id") or None,
            source_message_id=mid,
        ))
        return effects

    if _EN_REFUND_PENDING.search(text):
        effects.append(MessageEffect(
            effect_type="refund_pending", user_id=uid,
            effective_date=None, new_amount=None,
            event_id_reference=msg.get("related_event_id") or None,
            source_message_id=mid,
        ))
        return effects

    if _EN_PENDING_CREDIT.search(text):
        effects.append(MessageEffect(
            effect_type="pending_credit_ignore", user_id=uid,
            effective_date=None, new_amount=None,
            event_id_reference=msg.get("related_event_id") or None,
            source_message_id=mid,
        ))
        return effects

    return effects


def parse_all_messages(messages: list[dict]) -> dict[str, list[MessageEffect]]:
    use_cache = os.getenv("CACHE_EVIDENCE", "true").lower() in ("true", "1")
    result: dict[str, list[MessageEffect]] = {}

    for msg in messages:
        uid = msg.get("user_id", "")
        effects = parse_message(msg)
        if uid not in result:
            result[uid] = []
        result[uid].extend(effects)

    return result
