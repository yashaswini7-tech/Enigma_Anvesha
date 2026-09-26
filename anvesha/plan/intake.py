"""The family's circumstances. Every field is optional; unknown stays unknown."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

YES, NO, UNKNOWN = "Yes", "No", "Not sure"
CHOICES = [UNKNOWN, YES, NO]


@dataclass
class Circumstances:
    deceased_name: str = ""
    date_of_death: date | None = None
    main_bank: str = ""
    relationship: str = ""
    other_heirs: int | None = None
    minors_among_heirs: str = UNKNOWN
    will_exists: str = UNKNOWN
    will_location_known: str = UNKNOWN
    nominees_registered: str = UNKNOWN  # for most accounts and policies
    joint_main_account: str = UNKNOWN  # main account held jointly with survivorship
    dependants: str = UNKNOWN
    dispute: str = UNKNOWN
    property_owned: str = UNKNOWN
    state: str = ""
    notes: list[str] = field(default_factory=list)

    def flags(self, has_home_loan: bool = False) -> set[str]:
        """Named conditions the KB `when` clauses refer to."""
        out: set[str] = set()
        if self.dispute == YES:
            out.add("dispute")
        if self.minors_among_heirs == YES:
            out.add("minors")
        if self.will_exists == NO and (self.other_heirs or 0) >= 1:
            out.add("no_will_multiple_heirs")
        if self.property_owned == YES or has_home_loan:
            out.add("property")
        if self.nominees_registered != YES:
            out.add("no_nominee_items")
        if self.dependants == YES:
            out.add("dependants")
        return out

    def has_nominee(self, item_type: str) -> bool:
        if item_type == "main_account" and self.joint_main_account == YES:
            return True
        return self.nominees_registered == YES

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date_of_death"] = self.date_of_death.isoformat() if self.date_of_death else None
        return d
