"""Inventory + circumstances + knowledge base -> ordered actions by stage.

The engine never writes procedural text itself. Every action is a KB entry from
knowledge/procedures.yaml, selected by its `applies_to` and `when` fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import yaml

from anvesha import config
from anvesha.discover.inventory import Item
from anvesha.plan.intake import Circumstances

STAGES = {
    "this_week": "This week",
    "first_month": "First month",
    "months_2_6": "Months 2 to 6",
}
ANNUAL_MULTIPLIER = {"monthly": 12, "quarterly": 4, "annual": 1}


@dataclass
class Action:
    key: str
    kb_id: str
    stage: str
    urgency: int
    text: str
    why: str
    documents: list[str]
    source_name: str
    source_url: str
    verified: bool
    note: str = ""
    item_id: str = ""
    institution: str = ""
    money_at_stake: float = 0.0
    reasons: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def load_procedures() -> tuple[dict, ...]:
    raw = yaml.safe_load((config.KNOWLEDGE_DIR / "procedures.yaml").read_text(encoding="utf-8"))
    return tuple(raw["entries"])


@lru_cache(maxsize=1)
def load_channels() -> tuple[dict, ...]:
    path = config.KNOWLEDGE_DIR / "discovery_channels.yaml"
    return tuple(yaml.safe_load(path.read_text(encoding="utf-8"))["channels"])


def money_at_stake(item: Item) -> float:
    if item.amount is None:
        return 0.0
    return item.amount * ANNUAL_MULTIPLIER.get(item.frequency, 1)


def _main_account(c: Circumstances) -> Item | None:
    if not c.main_bank:
        return None
    return Item(
        id="MAIN",
        type="main_account",
        institution=c.main_bank,
        confidence=1.0,
        rationale="The account whose statement was uploaded.",
        origin="statement",
    )


def _when_ok(entry: dict, flags: set[str], item: Item | None, c: Circumstances) -> bool:
    when = entry.get("when") or {}
    if "any_of" in when and not flags & set(when["any_of"]):
        return False
    if when.get("item_flag") == "still_debiting" and not (item and item.still_debiting):
        return False
    wants_nominee = when.get("nominee_or_survivor")
    return wants_nominee is None or (item is not None and c.has_nominee(item.type) == wants_nominee)


def _action(entry: dict, item: Item | None, reasons: list[str]) -> Action:
    inst = item.institution if item else ""
    return Action(
        key=f"{entry['id']}:{item.id if item else 'all'}",
        kb_id=entry["id"],
        stage=entry["stage"],
        urgency=int(entry["urgency"]),
        text=entry["action"].replace("{institution}", inst or "the institution"),
        why=entry["why"],
        documents=list(entry.get("documents") or []),
        source_name=entry["source_name"],
        source_url=entry["source_url"],
        verified=bool(entry["verified"]),
        note=entry.get("note", ""),
        item_id=item.id if item else "",
        institution=inst,
        money_at_stake=money_at_stake(item) if item else 0.0,
        reasons=reasons,
    )


def _reasons(entry: dict, flags: set[str], item: Item | None) -> list[str]:
    reasons = []
    matched = flags & set((entry.get("when") or {}).get("any_of", []))
    labels = {
        "dispute": "There is a dispute among heirs.",
        "minors": "There are minors among the heirs.",
        "no_will_multiple_heirs": "There is no will and more than one heir.",
        "property": "There is property (a home loan or property was reported).",
        "no_nominee_items": "Nominees are not confirmed for every item.",
    }
    reasons += [labels[m] for m in sorted(matched) if m in labels]
    if item is not None and item.still_debiting:
        reasons.append(
            f"{item.post_death_debits} debit(s) totalling Rs {item.post_death_total:,.0f} "
            "after the date of death."
        )
    return reasons


def build_plan(items: list[Item], c: Circumstances) -> list[Action]:
    has_home_loan = any(i.type == "home_loan" for i in items)
    flags = c.flags(has_home_loan)
    targets = [i for i in items if i.status != "possibly_closed"]
    main = _main_account(c)
    if main:
        targets.append(main)
    actions: list[Action] = []
    for entry in load_procedures():
        applies = entry["applies_to"]
        if "*" in applies:
            if _when_ok(entry, flags, None, c):
                actions.append(_action(entry, None, _reasons(entry, flags, None)))
            continue
        for item in targets:
            if item.type in applies and _when_ok(entry, flags, item, c):
                actions.append(_action(entry, item, _reasons(entry, flags, item)))
    for item in items:
        if item.status == "possibly_closed":
            actions.append(_confirm_closed(item))
    order = list(STAGES)
    actions.sort(key=lambda a: (order.index(a.stage), a.urgency, -a.money_at_stake, a.key))
    return actions


def _confirm_closed(item: Item) -> Action:
    """Items that look closed still get a check, using the same KB entry as live ones."""
    entry = next(
        (e for e in load_procedures() if item.type in e["applies_to"] and not e.get("when")),
        None,
    )
    text = f"Confirm with {item.institution} whether this is closed or still holds money."
    if entry is None:
        return Action(
            key=f"confirm_closed:{item.id}",
            kb_id="",
            stage="first_month",
            urgency=3,
            text=text,
            why="The payments stopped, but the account may still hold a balance.",
            documents=["Death certificate"],
            source_name="",
            source_url="",
            verified=False,
            item_id=item.id,
            institution=item.institution,
        )
    act = _action(entry, item, ["Payments stopped more than three cycles ago."])
    act.key, act.stage, act.urgency = f"confirm_closed:{item.id}", "first_month", 3
    act.text = f"{text} If it is open: {act.text}"
    return act


def lawyer_step(actions: list[Action]) -> Action | None:
    return next((a for a in actions if a.kb_id == "lawyer_needed"), None)
