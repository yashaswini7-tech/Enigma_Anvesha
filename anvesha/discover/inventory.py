"""Merge statement and AIS evidence into one item per real-world account or policy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date

import pandas as pd

from anvesha import config
from anvesha.discover.recurring import Series, detect_series
from anvesha.discover.rules import (
    IGNORE,
    Classification,
    classify_ais,
    classify_series,
    classify_single,
)

GROUPS = {
    "life_insurance": "Assets",
    "term_insurance": "Assets",
    "health_insurance": "Assets",
    "mutual_fund": "Assets",
    "ppf": "Assets",
    "fixed_deposit": "Assets",
    "bank_account": "Assets",
    "demat_account": "Assets",
    "epf": "Assets",
    "home_loan": "Liabilities",
    "personal_loan": "Liabilities",
    "loan": "Liabilities",
    "credit_card": "Liabilities",
    "subscription": "Still billing",
    "cloud_storage": "Digital",
    "digital_account": "Digital",
    "other": "Assets",
}
TYPE_LABELS = {
    "life_insurance": "Life insurance policy",
    "term_insurance": "Term insurance policy",
    "health_insurance": "Health insurance policy",
    "mutual_fund": "Mutual fund folio",
    "ppf": "Public Provident Fund account",
    "fixed_deposit": "Fixed deposit",
    "bank_account": "Bank account",
    "demat_account": "Demat account (shares)",
    "epf": "Employees' Provident Fund account",
    "home_loan": "Home loan",
    "personal_loan": "Personal loan",
    "loan": "Loan",
    "credit_card": "Credit card",
    "subscription": "Subscription",
    "cloud_storage": "Cloud storage / online account",
    "digital_account": "Online account",
    "other": "Other",
}
# Items of these types are merged on type alone (one demat view, one EPF account).
MERGE_ON_TYPE = {"demat_account", "epf"}

SeriesClassifier = Callable[[Series], Classification | None]


@dataclass
class Evidence:
    source: str  # statement | ais | manual
    ref: str
    line_ref: str
    date: str
    text: str
    amount: float


@dataclass
class Item:
    id: str
    type: str
    institution: str
    confidence: float
    rationale: str
    origin: str  # rules | llm | manual
    evidence: list[Evidence] = field(default_factory=list)
    frequency: str = ""
    amount: float | None = None
    amount_note: str = ""
    status: str = "active"  # active | possibly_closed
    post_death_debits: int = 0
    post_death_total: float = 0.0

    @property
    def group(self) -> str:
        return GROUPS.get(self.type, "Assets")

    @property
    def label(self) -> str:
        return TYPE_LABELS.get(self.type, self.type.replace("_", " ").title())

    @property
    def still_debiting(self) -> bool:
        return self.post_death_debits > 0

    @property
    def sources(self) -> list[str]:
        return sorted({e.source for e in self.evidence})

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(group=self.group, label=self.label, sources=self.sources)
        return d


@dataclass
class _Candidate:
    cls: Classification
    evidence: list[Evidence]
    series: Series | None = None


def _series_evidence(s: Series) -> list[Evidence]:
    return [
        Evidence("statement", ref, line, d.isoformat(), narr_for(s, i), amt)
        for i, (ref, line, d, amt) in enumerate(
            zip(s.refs, s.line_refs, s.dates, s.amounts, strict=True)
        )
    ]


def narr_for(s: Series, i: int) -> str:
    return s.extra.get("narr_by_ref", {}).get(s.refs[i], s.narrations[0])


def _merge_key(cls: Classification) -> tuple[str, str]:
    if cls.type in MERGE_ON_TYPE:
        return (cls.type, "")
    return (cls.type, cls.institution.lower())


def gather_candidates(
    statement: pd.DataFrame,
    ais: pd.DataFrame | None,
    main_bank: str = "",
    llm_classifier: SeriesClassifier | None = None,
) -> tuple[list[_Candidate], list[Series]]:
    candidates: list[_Candidate] = []
    series, singles = detect_series(statement)
    narr_by_ref = dict(zip(statement["ref"], statement["narration"], strict=True))
    for s in series:
        s.extra["narr_by_ref"] = narr_by_ref
        cls = classify_series(s, main_bank)
        if cls is None and llm_classifier is not None:
            cls = llm_classifier(s)
        s.extra["classification"] = cls
        if cls is not None and cls.type != IGNORE:
            candidates.append(_Candidate(cls, _series_evidence(s), s))
    for row in singles.to_dict("records"):
        cls = classify_single(row, main_bank)
        if cls is None or cls.type == IGNORE:
            continue
        amount = row["debit"] or row["credit"]
        ev = Evidence(
            "statement",
            row["ref"],
            row["line_ref"],
            row["date"].date().isoformat(),
            row["narration"],
            amount,
        )
        candidates.append(_Candidate(cls, [ev]))
    if ais is not None:
        for row in ais.to_dict("records"):
            cls = classify_ais(row, main_bank)
            if cls is None or cls.type == IGNORE:
                continue
            text = f"{row['financial_year']} | {row['category']} | {row['entity']}"
            ev = Evidence(
                "ais",
                row["ref"],
                row["line_ref"],
                f"FY {row['financial_year']}",
                text,
                float(row["amount"]),
            )
            candidates.append(_Candidate(cls, [ev]))
    return candidates, series


def _describe_amount(item: Item, series_list: list[Series]) -> None:
    recurring = [s for s in series_list if s.status == "active"] or series_list
    if recurring:
        s = max(recurring, key=lambda x: x.count)
        item.amount = round(s.median_amount, 2)
        item.frequency = s.frequency
        verb = "debited" if s.direction == "debit" else "credited"
        item.amount_note = f"About Rs {s.median_amount:,.0f} {verb} {s.frequency}"
        return
    stmt = [e for e in item.evidence if e.source == "statement"]
    ais = [e for e in item.evidence if e.source == "ais"]
    if ais:
        latest = max(e.date for e in ais)
        total = sum(e.amount for e in ais if e.date == latest)
        item.amount = total
        item.amount_note = f"Rs {total:,.0f} reported in AIS for {latest}"
    elif stmt:
        total = sum(e.amount for e in stmt)
        item.amount = total
        item.amount_note = f"Rs {total:,.0f} across {len(stmt)} statement line(s)"


def build_inventory(
    statement: pd.DataFrame,
    ais: pd.DataFrame | None = None,
    main_bank: str = "",
    date_of_death: date | None = None,
    llm_classifier: SeriesClassifier | None = None,
) -> list[Item]:
    candidates, _ = gather_candidates(statement, ais, main_bank, llm_classifier)
    merged: dict[tuple[str, str], list[_Candidate]] = {}
    for cand in candidates:
        merged.setdefault(_merge_key(cand.cls), []).append(cand)
    items: list[Item] = []
    for group in merged.values():
        items.append(_to_item(group, date_of_death))
    items.sort(key=lambda i: (list(GROUPS).index(i.type), -i.confidence))
    for n, item in enumerate(items, start=1):
        item.id = f"I{n:02d}"
    return items


def _to_item(group: list[_Candidate], date_of_death: date | None) -> Item:
    best = max(group, key=lambda c: c.cls.confidence)
    evidence = sorted(
        {e.ref: e for c in group for e in c.evidence}.values(), key=lambda e: (e.source, e.date)
    )
    sources = {e.source for e in evidence}
    confidence = best.cls.confidence
    if len(sources) > 1 or len(group) > 1:
        confidence = min(config.CONF_MAX, confidence + config.CONF_CORROBORATION_BONUS)
    rationales = list(dict.fromkeys(c.cls.rationale for c in group))
    item = Item(
        id="",
        type=best.cls.type,
        institution=best.cls.institution,
        confidence=round(confidence, 2),
        rationale=" ".join(rationales),
        origin="llm" if any(c.cls.origin == "llm" for c in group) else "rules",
        evidence=evidence,
    )
    series_list = [c.series for c in group if c.series is not None]
    if series_list and all(s.status == "possibly_closed" for s in series_list):
        item.status = "possibly_closed"
        item.rationale += " The pattern stopped more than three cycles ago: possibly closed."
    _describe_amount(item, series_list)
    if date_of_death:
        after = [
            e
            for e in evidence
            if e.source == "statement"
            and date.fromisoformat(e.date) > date_of_death
            and any(s.direction == "debit" for s in series_list)
        ]
        item.post_death_debits = len(after)
        item.post_death_total = round(sum(e.amount for e in after), 2)
    return item


def manual_item(item_type: str, institution: str, note: str, next_id: int) -> Item:
    return Item(
        id=f"M{next_id:02d}",
        type=item_type,
        institution=institution,
        confidence=1.0,
        rationale="Entered by the family.",
        origin="manual",
        evidence=[Evidence("manual", f"manual-{next_id}", "Entered by the family", "", note, 0.0)],
    )
