"""LLM fallback for recurring series the rules could not settle.

Input is redacted. Output must be strict JSON with a known type; anything else is dropped.
"""

from __future__ import annotations

import hashlib
import json

from anvesha import config
from anvesha.discover.recurring import Series
from anvesha.discover.rules import IGNORE, Classification
from anvesha.llm import LLMClient, complete_json, get_client
from anvesha.privacy.redact import redact

ALLOWED_TYPES = [
    "life_insurance",
    "term_insurance",
    "health_insurance",
    "home_loan",
    "personal_loan",
    "loan",
    "credit_card",
    "mutual_fund",
    "ppf",
    "fixed_deposit",
    "bank_account",
    "demat_account",
    "epf",
    "subscription",
    "cloud_storage",
    "not_financial_item",
]
LLM_CONFIDENCE_CAP = 0.85  # LLM guesses never outrank rule matches backed by aliases

SYSTEM = (
    "You classify recurring transactions from an Indian savings-account statement of a person "
    "who has died, so the family can find policies, loans, investments and subscriptions. "
    "Narrations are abbreviated bank text; identifiers are masked. "
    "Answer with one JSON object with keys in this order: rationale, type, institution, "
    "confidence. Write the rationale first, then choose the type that matches it. "
    f"type must be one of: {', '.join(ALLOWED_TYPES)}. "
    "Use not_financial_item for groceries, utilities, fuel, shopping or transfers to people. "
    "Credit card bill payments change in amount every month; the same amount debited on the "
    "same day every month usually means an insurance premium, loan EMI, SIP or subscription. "
    "Indian narrations often shorten names: LIFE, INS, TRM (term), HLTH, FIN, MF. "
    'institution is your best guess of the full organisation name, or "unknown". '
    "rationale is one short sentence. confidence is a number from 0 to 1."
)


def build_prompt(series: Series) -> str:
    samples = "; ".join(redact(n) for n in series.narrations[:3])
    return (
        f"Direction: {series.direction}\n"
        f"Frequency: {series.frequency}, {series.count} times "
        f"from {series.first} to {series.last}\n"
        f"Typical amount: Rs {series.median_amount:,.0f}\n"
        f"Narration(s): {samples}\n"
        "What is this?"
    )


def validate(payload: dict | None) -> Classification | None:
    if not payload:
        return None
    typ = str(payload.get("type", "")).strip().lower()
    if typ not in ALLOWED_TYPES:
        return None
    try:
        conf = float(payload.get("confidence", 0))
    except (TypeError, ValueError):
        return None
    if not 0 <= conf <= 1:
        return None
    if typ == "not_financial_item":
        return Classification(IGNORE, "", conf, "LLM: not a financial item.", origin="llm")
    if conf < config.LLM_MIN_CONFIDENCE:
        return None
    inst = str(payload.get("institution") or "unknown").strip()[:60]
    if inst.lower() in {"", "unknown", "none", "n/a"}:
        inst = "Unidentified institution"
    rationale = str(payload.get("rationale", "")).strip()[:200]
    return Classification(
        typ,
        inst,
        round(min(conf, LLM_CONFIDENCE_CAP), 2),
        f"LLM suggestion: {rationale}",
        origin="llm",
    )


def _load_cache() -> dict:
    try:
        return json.loads(config.LLM_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cache(cache: dict) -> None:
    config.LLM_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.LLM_CACHE_PATH.write_text(json.dumps(cache, indent=1), encoding="utf-8")


def classify_with(client: LLMClient, series: Series, cache: dict | None = None) -> dict | None:
    prompt = build_prompt(series)
    key = hashlib.sha256(f"{client.name}|{client.model}|{SYSTEM}|{prompt}".encode()).hexdigest()
    if cache is not None and key in cache:
        return cache[key]
    payload = complete_json(client, SYSTEM, prompt)
    if cache is not None:
        cache[key] = payload
    return payload


def make_classifier(provider: str, model: str | None = None):
    client = get_client(provider, model)
    if client is None:
        raise RuntimeError(f"LLM provider '{provider}' is not available")
    cache = _load_cache()

    def classify(series: Series) -> Classification | None:
        payload = classify_with(client, series, cache)
        _save_cache(cache)
        return validate(payload)

    return classify
