"""One consolidated document checklist, built from the plan's KB entries."""

from __future__ import annotations

from dataclasses import dataclass, field

from anvesha import config
from anvesha.discover.inventory import Item
from anvesha.plan.engine import Action


@dataclass
class DocumentNeed:
    name: str
    needed_for: list[str] = field(default_factory=list)
    count: int | None = None
    explanation: str = ""


def death_certificate_copies(items: list[Item], main_bank: str = "") -> tuple[int, list[str]]:
    institutions = {i.institution for i in items if i.status != "possibly_closed"}
    if main_bank:
        institutions.add(main_bank)
    names = sorted(institutions)
    return len(names) + config.DEATH_CERT_BUFFER, names


def build_checklist(
    actions: list[Action], items: list[Item], main_bank: str = ""
) -> list[DocumentNeed]:
    needs: dict[str, DocumentNeed] = {}
    for a in actions:
        for doc in a.documents:
            key = "death certificate" if "death certificate" in doc.lower() else doc.lower()
            need = needs.setdefault(key, DocumentNeed(name=doc))
            label = a.institution or "the estate as a whole"
            if label not in need.needed_for:
                need.needed_for.append(label)
    count, names = death_certificate_copies(items, main_bank)
    death = needs.setdefault("death certificate", DocumentNeed(name="Death certificate"))
    death.name = "Certified copies of the death certificate"
    death.count = count
    death.explanation = (
        f"One for each of the {len(names)} institutions we found, plus "
        f"{config.DEATH_CERT_BUFFER} spare in case one is lost or asked for again. "
        "Ask each institution whether it needs a certified copy or will return the original."
    )
    ordered = sorted(needs.values(), key=lambda n: (n.count is None, -len(n.needed_for), n.name))
    return ordered
