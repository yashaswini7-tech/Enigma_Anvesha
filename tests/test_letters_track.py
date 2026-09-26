from datetime import date

import pytest

from anvesha import config
from anvesha.discover.inventory import Evidence, Item
from anvesha.letters import draft
from anvesha.plan.intake import Circumstances
from anvesha.track import store

CIRC = Circumstances(
    deceased_name="Ramesh Kulkarni", date_of_death=date(2025, 7, 12), relationship="Spouse"
)


def _item(t="home_loan", inst="HDFC Bank"):
    ev = Evidence(
        "statement", "TXN1", "row 2", "2025-08-05", "NACH DR HDFC BANK LTD HL EMI", 38420.0
    )
    return Item("I01", t, inst, 0.9, "r", "rules", [ev], "monthly", 38420.0)


class FakeClient:
    name, model = "fake", "f"

    def __init__(self, reply):
        self.reply = reply

    def complete(self, system, prompt, json_mode=False):
        return self.reply


def test_lender_letter_keeps_payments_and_asks_about_cover():
    text = draft.render(_item(), CIRC, draft.Sender(name="Sunita Kulkarni"))
    assert "Ramesh Kulkarni" in text and "12 July 2025" in text
    assert "insurance cover" in text and "before any EMI is missed" in text
    assert "!" not in text and "Sunita Kulkarni" in text


@pytest.mark.parametrize(
    "t,kind",
    [
        ("subscription", "cancellation"),
        ("life_insurance", "intimation"),
        ("personal_loan", "lender"),
    ],
)
def test_letter_kind(t, kind):
    assert draft.letter_kind(_item(t)) == kind
    assert "Copy of the death certificate" in draft.render(_item(t), CIRC)


def test_docx_export():
    assert draft.to_docx("hello\nworld")[:2] == b"PK"


def test_polish_rejects_changed_facts_and_accepts_rewording():
    opening = draft.default_opening(_item(), CIRC)
    bad = FakeClient("Ramesh Kulkarni died on 3 March owing Rs 5,00,000!")
    assert draft.polish_opening(bad, opening) == opening
    good = FakeClient(
        "With sadness I write to tell you that Ramesh Kulkarni, who held a home "
        "loan with you, has died. I write for the family."
    )
    assert draft.polish_opening(good, opening).startswith("With sadness")


def test_tracker_roundtrip_and_delete(tmp_path, monkeypatch):
    db = tmp_path / "t.db"
    monkeypatch.setattr(config, "LLM_CACHE_PATH", tmp_path / "cache.json")
    (tmp_path / "cache.json").write_text("{}")
    item = _item()
    store.sync_items([item], db)
    store.set_status(store.item_key(item), "intimated", "letter posted", db)
    store.sync_items([item], db)  # must not reset status
    rows = store.all_rows(db)
    assert rows[0]["status"] == "intimated" and rows[0]["note"] == "letter posted"
    with pytest.raises(ValueError):
        store.set_status(store.item_key(item), "lost", db_path=db)
    removed = store.delete_all_data(db)
    assert not db.exists() and not (tmp_path / "cache.json").exists() and len(removed) == 2
