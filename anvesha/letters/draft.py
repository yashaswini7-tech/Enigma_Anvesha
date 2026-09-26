"""Fill letter templates. The LLM may polish the opening paragraph's wording only.

Facts (names, dates, amounts, references, requests, enclosures) always come from the
template and the inventory, never from the model.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from anvesha.discover.inventory import Item
from anvesha.llm import LLMClient, complete_text
from anvesha.plan.engine import load_procedures
from anvesha.plan.intake import Circumstances

_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    autoescape=False,  # plain-text letters, never rendered as HTML
)

KIND_BY_TYPE = {
    "home_loan": "lender",
    "personal_loan": "lender",
    "loan": "lender",
    "credit_card": "lender",
    "subscription": "cancellation",
    "cloud_storage": "cancellation",
}
REFERENCE_LABEL = {
    "life_insurance": "Policy number",
    "term_insurance": "Policy number",
    "health_insurance": "Policy number",
    "mutual_fund": "Folio number",
    "home_loan": "Loan account number",
    "personal_loan": "Loan account number",
    "loan": "Loan account number",
    "credit_card": "Card number (last four digits)",
    "fixed_deposit": "Deposit / account number",
    "bank_account": "Account number",
    "ppf": "PPF account number",
    "demat_account": "DP ID / client ID",
    "epf": "UAN or PF number",
    "subscription": "Registered email or customer ID",
    "cloud_storage": "Registered email",
}
RECIPIENT = {
    "lender": "The Branch Manager / Loan Servicing, {inst}",
    "cancellation": "Customer Support, {inst}",
    "intimation": "The Claims / Customer Service Department, {inst}",
}
SUBJECT = {
    "lender": "Intimation of death of the borrower, {deceased}",
    "cancellation": "Cancellation of subscription on the death of {deceased}",
    "intimation": "Intimation of death of {deceased} - {label}",
}
OPENING = {
    "lender": "I am writing to inform you that {deceased}, who held a {label} with you, has "
    "passed away. I am writing on behalf of the family.",
    "cancellation": "I am writing to inform you that {deceased}, who held a subscription with "
    "you, has passed away.",
    "intimation": "I am writing to inform you that {deceased}, who held a {label} with you, "
    "has passed away. I am writing on behalf of the family.",
}


@dataclass
class Sender:
    name: str = ""
    address: str = ""
    contact: str = ""


def letter_kind(item: Item) -> str:
    return KIND_BY_TYPE.get(item.type, "intimation")


def enclosures_for(item: Item) -> list[str]:
    """Documents from the KB entries that apply to this item type."""
    docs = ["Copy of the death certificate"]
    for entry in load_procedures():
        if item.type in entry["applies_to"]:
            for d in entry.get("documents") or []:
                if "death certificate" in d.lower() or "claim form" in d.lower():
                    continue
                if "form" in d.lower() and "(" not in d:
                    continue  # forms the institution will send
                if d not in docs:
                    docs.append(d)
    return docs[:5]


def _evidence_lines(item: Item, limit: int = 2) -> list[str]:
    stmt = [e for e in item.evidence if e.source == "statement"]
    latest = sorted(stmt, key=lambda e: e.date)[-limit:]
    return [f"Rs {e.amount:,.2f} on {e.date} ({e.text})" for e in latest]


def render(
    item: Item,
    circ: Circumstances,
    sender: Sender | None = None,
    opening: str | None = None,
    today: date | None = None,
) -> str:
    sender = sender or Sender()
    kind = letter_kind(item)
    deceased = circ.deceased_name or "[Name of the deceased]"
    fmt = {"inst": item.institution, "deceased": deceased, "label": item.label.lower()}
    template = _ENV.get_template(f"{kind}.txt.j2")
    text = template.render(
        sender_name=sender.name,
        sender_address=sender.address,
        contact=sender.contact,
        relationship=circ.relationship,
        today=(today or date.today()).strftime("%d %B %Y"),
        recipient=RECIPIENT[kind].format(**fmt),
        subject=SUBJECT[kind].format(**fmt),
        opening=opening or OPENING[kind].format(**fmt),
        deceased=circ.deceased_name,
        date_of_death=circ.date_of_death.strftime("%d %B %Y") if circ.date_of_death else "",
        reference_label=REFERENCE_LABEL.get(item.type, "Reference number"),
        reference="",
        evidence_lines=_evidence_lines(item),
        item_label=item.label,
        enclosures=enclosures_for(item),
    )
    return re.sub(r"\n{3,}", "\n\n", text)


def default_opening(item: Item, circ: Circumstances) -> str:
    deceased = circ.deceased_name or "[Name of the deceased]"
    return OPENING[letter_kind(item)].format(
        inst=item.institution, deceased=deceased, label=item.label.lower()
    )


def _facts(text: str) -> set[str]:
    return set(re.findall(r"\d[\d,./-]*", text))


def polish_opening(client: LLMClient, opening: str) -> str:
    """Ask the model for calmer wording of one paragraph. Reject it if facts change."""
    system = (
        "Rewrite the paragraph in plain, calm, formal Indian English for a letter from a "
        "grieving family to an institution. Keep every name, date and number exactly. Do not "
        "add facts, requests, promises or legal claims. No exclamation marks. Reply with the "
        "paragraph only."
    )
    try:
        out = complete_text(client, system, opening)
    except Exception:
        return opening
    out = out.strip().strip('"')
    names = re.findall(r"[A-Z][a-z]+(?: [A-Z][a-z]+)+", opening)
    ok = (
        out
        and "!" not in out
        and "[" not in out.replace("[Name of the deceased]", "")
        and _facts(out) <= _facts(opening)
        and all(n in out for n in names)
        and len(out) < 2 * len(opening) + 80
    )
    return out if ok else opening


def to_docx(text: str) -> bytes:
    from docx import Document

    doc = Document()
    for para in text.split("\n"):
        doc.add_paragraph(para)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
