import pytest

from anvesha.privacy.redact import contains_identifier, redact


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("mail ramesh.k@example.co.in now", "mail [EMAIL] now"),
        ("UPI/P2P/sunita@okbank/rent", "UPI/P2P/[UPI_ID]/rent"),
        ("PAN ABCPK1234L on file", "PAN [PAN] on file"),
        ("aadhaar 2345 6789 0123", "aadhaar [AADHAAR]"),
        ("aadhaar 234567890123", "aadhaar [AADHAAR]"),
        ("call +91 98220 12345", "call [PHONE]"),
        ("call 9822012345", "call [PHONE]"),
        ("ACH D- PNBMET TRM 004512XXXX", "ACH D- PNBMET TRM [ACCT]"),
        ("POS 4591XXXXXXXX2231 NETFLIX.COM", "POS [ACCT] NETFLIX.COM"),
        ("TRANSFER TO PPF A/C XXXXXXX7730", "TRANSFER TO PPF A/C [ACCT]"),
        ("A/C 30012345678", "A/C [ACCT]"),
    ],
)
def test_redact_masks_identifiers(raw, expected):
    assert redact(raw) == expected


@pytest.mark.parametrize(
    "safe",
    [
        "NACH DR HDFC BANK LTD HL EMI",
        "UPI/MANDATE/PWRZONE CLUB/MTHLY",
        "Rs 1,318 monthly",
        "INT.PD SB QTRLY",
        "GOOGLE*GOOGLE ONE",
    ],
)
def test_redact_keeps_ordinary_text(safe):
    assert redact(safe) == safe


def test_redacted_text_has_no_identifiers_left():
    raw = "Ramesh ABCPK1234L 9822012345 a/c 004512XXXX r@x.com 2345 6789 0123"
    assert not contains_identifier(redact(raw))
