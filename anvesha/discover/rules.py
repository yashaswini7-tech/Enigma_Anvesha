"""Narration patterns and institution aliases -> item type.

Rules return a Classification, the sentinel type "ignore" for recognised household noise, or
None when they cannot decide (those series go to the LLM fallback when one is configured).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import yaml

from anvesha import config
from anvesha.discover.recurring import Series, clean_narration

IGNORE = "ignore"

INSURANCE_TYPES = {"life_insurance", "term_insurance", "health_insurance"}
LOAN_TYPES = {"home_loan", "personal_loan", "loan"}
# Institution kinds in the order we prefer them when several aliases match one narration.
KIND_PRIORITY = ["amc", "insurer", "housing_finance", "nbfc", "platform", "registrar", "bank"]

KW = {
    "ignore": r"\b(P2P|ATM|WDL|FUEL|ELECTRICITY|ELEC BILL|GAS BILL|WATER BILL)\b",
    "own_interest": r"\b(INT PD SB|SB INT|SB INTEREST|SAVINGS INTEREST|CREDIT INTEREST)\b",
    "salary": r"\b(SALARY|SAL|PAYROLL)\b",
    "dividend": r"\b(DIV|DIVIDEND)\b",
    "interest": r"\b(INT PD|INTEREST|FD INT|TD INT)\b",
    "ppf": r"\bPPF\b",
    "mf": r"\b(SIP|MF|MUTUAL FUND)\b",
    "premium": r"\b(PREM|PREMIUM|POLICY|POL|INSURANCE|INS)\b",
    "term": r"\b(TERM|TERM PLAN)\b",
    "health": r"\b(HEALTH|HLTH|MEDICLAIM)\b",
    "emi": r"\b(EMI|LOAN)\b",
    "home": r"\b(HL|HOME LOAN|HOUSING)\b",
    "mandate": r"\b(NACH|ECS|ACH|MANDATE|SI)\b",
}


@dataclass
class Institution:
    name: str
    kind: str
    default_type: str
    aliases: list[str]


@dataclass
class Classification:
    type: str
    institution: str
    confidence: float
    rationale: str
    origin: str = "rules"


@lru_cache(maxsize=1)
def load_institutions() -> tuple[Institution, ...]:
    raw = yaml.safe_load((config.KNOWLEDGE_DIR / "institutions.yaml").read_text(encoding="utf-8"))
    return tuple(Institution(**entry) for entry in raw["institutions"])


def _has(pattern_name: str, text: str) -> bool:
    return re.search(KW[pattern_name], text) is not None


def match_institution(text: str, kinds: set[str] | None = None) -> Institution | None:
    """Best institution for a cleaned narration: preferred kind, then longest alias."""
    padded = f" {clean_narration(text)} "
    hits: list[tuple[int, int, Institution]] = []
    for inst in load_institutions():
        if kinds and inst.kind not in kinds:
            continue
        for alias in inst.aliases:
            if f" {clean_narration(alias)} " in padded:
                hits.append((KIND_PRIORITY.index(inst.kind), -len(alias), inst))
    if not hits:
        return None
    return sorted(hits, key=lambda h: (h[0], h[1]))[0][2]


def _confidence(alias: bool, keyword: bool, recurring: bool) -> float:
    if alias and keyword:
        base = config.CONF_ALIAS_AND_KEYWORD
    elif alias:
        base = config.CONF_ALIAS_ONLY
    else:
        base = config.CONF_KEYWORD_ONLY
    return round(base if recurring else base - config.CONF_SINGLE_PENALTY, 2)


def _employer(text: str) -> str:
    cleaned = re.sub(r"\b(NEFT|RTGS|IMPS|CR|CREDIT|SALARY|SAL|PAYROLL|FOR|MONTH)\b", " ", text)
    return " ".join(cleaned.split()).title() or "Employer"


def classify_text(
    narration: str, direction: str, recurring: bool, main_bank: str = ""
) -> Classification | None:
    text = clean_narration(narration)
    raw = " ".join(re.sub(r"[^A-Z0-9 ]+", " ", str(narration).upper()).split())
    if _has("ignore", raw) or _has("own_interest", text):
        return Classification(IGNORE, "", 1.0, "Household spending or transfer.")
    inst = match_institution(text)
    if direction == "credit":
        if _has("salary", text):
            return Classification(
                "epf",
                _employer(text),
                _confidence(False, True, recurring),
                "Regular salary credits from an employer suggest an EPF account may exist.",
            )
        if _has("dividend", text):
            return Classification(
                "demat_account",
                "Demat account",
                _confidence(False, True, recurring),
                "Dividend credits suggest shares held in a demat account.",
            )
        if _has("interest", text):
            bank = inst.name if inst and inst.kind == "bank" else "Unknown bank"
            return Classification(
                "fixed_deposit",
                bank,
                _confidence(inst is not None, True, recurring),
                "Interest credits suggest a deposit.",
            )
        return None
    return _classify_debit(text, inst, recurring, main_bank)


def _classify_debit(
    text: str, inst: Institution | None, recurring: bool, main_bank: str
) -> Classification | None:
    if _has("ppf", text):
        return Classification(
            "ppf",
            main_bank or "Account-holding bank",
            _confidence(False, True, recurring),
            "Transfers into a PPF account.",
        )
    if (inst and inst.kind in {"amc", "registrar"}) or _has("mf", text):
        name = inst.name if inst else "Unknown fund house"
        return Classification(
            "mutual_fund",
            name,
            _confidence(inst is not None, _has("mf", text), recurring),
            "Regular debits to a fund house or registrar suggest a mutual fund folio (SIP).",
        )
    if (inst and inst.kind == "insurer") or _has("premium", text) and not _has("emi", text):
        typ = inst.default_type if inst else "life_insurance"
        if _has("term", text):
            typ = "term_insurance"
        elif _has("health", text):
            typ = "health_insurance"
        return Classification(
            typ,
            inst.name if inst else "Unknown insurer",
            _confidence(inst is not None, _has("premium", text), recurring),
            "Premium payments to an insurer suggest a policy.",
        )
    lender = inst and inst.kind in {"nbfc", "housing_finance"}
    if lender or _has("emi", text) or (inst and inst.kind == "bank" and _has("mandate", text)):
        if _has("home", text):
            typ = "home_loan"
        elif inst and inst.kind in {"nbfc", "housing_finance"}:
            typ = inst.default_type
        else:
            typ = "loan"
        keyword = _has("emi", text) or _has("mandate", text)
        return Classification(
            typ,
            inst.name if inst else "Unknown lender",
            _confidence(inst is not None, keyword, recurring),
            "Fixed auto-debits to a lender suggest a loan EMI.",
        )
    if inst and inst.kind == "platform":
        return Classification(
            inst.default_type,
            inst.name,
            _confidence(True, recurring, recurring),
            "Card or mandate payments to a subscription service.",
        )
    return None


def classify_series(series: Series, main_bank: str = "") -> Classification | None:
    return classify_text(series.narrations[0], series.direction, True, main_bank)


def classify_single(row: dict, main_bank: str = "") -> Classification | None:
    """Rules for one-off transactions. Only strong signals are kept."""
    direction = "debit" if row["debit"] > 0 else "credit"
    cls = classify_text(row["narration"], direction, False, main_bank)
    if cls is None or cls.type == IGNORE:
        return cls
    if cls.type in INSURANCE_TYPES and row["debit"] < config.SINGLE_INSURER_DEBIT_MIN:
        return None
    if cls.type in LOAN_TYPES | {"subscription", "cloud_storage", "epf"}:
        return None  # these need a repeating pattern to be believable
    return cls


def classify_ais(row: dict, main_bank: str = "") -> Classification | None:
    cat = str(row["category"]).lower()
    entity = str(row["entity"])
    inst = match_institution(entity)
    name = inst.name if inst else entity.title()
    if "salary" in cat:
        return Classification(
            "epf",
            name,
            0.75,
            "Salary reported by an employer in AIS suggests an EPF account may exist.",
        )
    if "dividend" in cat:
        return Classification(
            "demat_account",
            "Demat account",
            0.85,
            "Dividends reported in AIS imply shares held in a demat account.",
        )
    if "mutual fund" in cat:
        return Classification(
            "mutual_fund",
            name,
            0.85,
            f"AIS reports mutual fund transactions ({row['category']}).",
        )
    if "interest from deposit" in cat or "time deposit" in cat:
        return Classification(
            "fixed_deposit",
            name,
            0.85,
            "AIS reports interest on a deposit at this bank.",
        )
    if "savings" in cat and "interest" in cat:
        if main_bank and inst and inst.name == main_bank:
            return Classification(IGNORE, name, 1.0, "Interest on the account we already have.")
        return Classification(
            "bank_account",
            name,
            0.85,
            "AIS reports savings interest from another bank.",
        )
    return None
