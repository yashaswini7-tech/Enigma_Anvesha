from datetime import date

from anvesha.discover.llm_classify import build_prompt, classify_with, validate
from anvesha.discover.recurring import Series
from anvesha.discover.rules import IGNORE
from anvesha.llm import complete_json, get_client, parse_json


class FakeClient:
    name, model = "fake", "fake-1"

    def __init__(self, reply: str) -> None:
        self.reply, self.seen = reply, []

    def complete(self, system: str, prompt: str, json_mode: bool = False) -> str:
        self.seen.append(system + prompt)
        return self.reply


def _series() -> Series:
    return Series(
        "S01",
        "ACH D PNBMET TRM",
        "debit",
        ["R1", "R2", "R3"],
        [date(2024, 1, 5), date(2024, 2, 5), date(2024, 3, 5)],
        [1318.0] * 3,
        ["ACH D- PNBMET TRM 004512XXXX"],
        ["l1", "l2", "l3"],
        "monthly",
    )


def test_prompt_is_redacted():
    assert "004512XXXX" not in build_prompt(_series())
    client = FakeClient("{}")
    complete_json(client, "sys", "call 9822012345 or mail a@b.com, PAN ABCPK1234L")
    sent = client.seen[0]
    assert "9822012345" not in sent and "a@b.com" not in sent and "ABCPK1234L" not in sent


def test_validate_accepts_good_json_and_caps_confidence():
    cls = validate(
        {
            "type": "term_insurance",
            "institution": "PNB MetLife",
            "confidence": 0.95,
            "rationale": "term premium",
        }
    )
    assert cls.type == "term_insurance" and cls.origin == "llm" and cls.confidence == 0.85


def test_validate_rejects_bad_output():
    assert validate(None) is None
    assert validate({"type": "lottery", "confidence": 0.9}) is None
    assert validate({"type": "subscription", "confidence": "high"}) is None
    assert validate({"type": "subscription", "confidence": 0.3}) is None
    assert validate({"type": "not_financial_item", "confidence": 0.9}).type == IGNORE


def test_parse_json_tolerates_wrapping_text():
    assert parse_json('Sure. {"type": "ppf"} done') == {"type": "ppf"}
    assert parse_json("no json here") is None


def test_classify_uses_cache():
    client = FakeClient('{"type": "subscription", "confidence": 0.8}')
    cache: dict = {}
    classify_with(client, _series(), cache)
    classify_with(client, _series(), cache)
    assert len(client.seen) == 1


def test_none_provider_has_no_client():
    assert get_client("none") is None
