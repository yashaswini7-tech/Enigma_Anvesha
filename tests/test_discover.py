from datetime import date, timedelta

import pandas as pd
import pytest

from anvesha.discover.inventory import build_inventory
from anvesha.discover.recurring import clean_narration, detect_series, infer_frequency
from anvesha.discover.rules import IGNORE, classify_ais, classify_text, match_institution
from anvesha.ingest.ais import load_ais
from anvesha.ingest.statement import load_statement
from eval.score import score


def _stmt(rows):
    df = pd.DataFrame(rows, columns=["date", "narration", "debit", "credit"])
    df["date"] = pd.to_datetime(df["date"])
    df["balance"] = 0.0
    df["ref"] = [f"R{i}" for i in range(len(df))]
    df["line_ref"] = df["ref"]
    df["source"] = "statement"
    return df


def test_clean_narration_drops_numbers_and_masks():
    assert clean_narration("ACH D- PNBMET TRM 004512XXXX") == "ACH D PNBMET TRM"
    assert clean_narration("POS 4591XXXXXXXX2231 NETFLIX.COM") == "POS NETFLIX COM"


def test_infer_frequency():
    start = date(2024, 1, 5)
    monthly = [start + timedelta(days=30 * i + (i % 2) * 3) for i in range(6)]
    assert infer_frequency(monthly) == "monthly"
    assert infer_frequency([date(2024, 6, 18), date(2025, 6, 17)]) == "annual"
    assert infer_frequency([date(2024, 1, 1), date(2024, 1, 20), date(2024, 4, 2)]) is None


def test_series_tolerates_small_amount_changes_and_flags_closed():
    rows = [(f"2024-{m:02d}-10", "ACH D- CAMS AXIS MF SIP", 5000 + m * 20, 0) for m in range(1, 5)]
    rows.append(("2025-06-30", "UPI/P2M/SHOP", 100, 0))
    series, singles = detect_series(_stmt(rows))
    assert len(series) == 1 and series[0].count == 4
    assert series[0].status == "possibly_closed"
    assert len(singles) == 1


@pytest.mark.parametrize(
    "narration,direction,expected_type,institution",
    [
        ("ECS DR LIC OF INDIA PREM POL 8812XXXX34", "debit", "life_insurance", "LIC"),
        ("NACH DR HDFC BANK LTD HL EMI 6600XXXX91", "debit", "home_loan", "HDFC Bank"),
        ("ACH D- BAJAJ FINANCE LTD 4XXXXXX2201", "debit", "personal_loan", "Bajaj Finance"),
        ("BIL/ACH/CAMS/AXIS MUTUAL FUND SIP", "debit", "mutual_fund", "Axis Mutual Fund"),
        ("TRANSFER TO PPF A/C XXXXXXX7730", "debit", "ppf", "SBI-main"),
        ("POS 4591XXXXXXXX2231 NETFLIX.COM", "debit", "subscription", "Netflix"),
        ("ACH C- INFOSYS LTD FINAL DIV", "credit", "demat_account", "Demat account"),
        ("UPI/P2P/SUNITA R KULKARNI/HOUSEHOLD", "debit", IGNORE, ""),
        ("INT.PD SB QTRLY", "credit", IGNORE, ""),
    ],
)
def test_rules(narration, direction, expected_type, institution):
    cls = classify_text(narration, direction, True, main_bank="SBI-main")
    assert cls is not None and cls.type == expected_type
    assert cls.institution == institution


def test_rules_leave_opaque_narrations_unresolved():
    assert classify_text("ACH D- PNBMET TRM 004512XXXX", "debit", True) is None
    assert classify_text("UPI/MANDATE/PWRZONE CLUB/MTHLY", "debit", True) is None


def test_amc_preferred_over_registrar():
    assert match_institution("ACH D- CAMS ICICI PRU MF SIP").name == "ICICI Prudential Mutual Fund"


def test_ais_main_bank_interest_is_not_a_new_item():
    row = {"category": "Interest from savings bank", "entity": "STATE BANK OF INDIA"}
    assert classify_ais(row, "State Bank of India").type == IGNORE
    row = {"category": "Interest from savings bank", "entity": "CANARA BANK"}
    assert classify_ais(row, "State Bank of India").type == "bank_account"


def test_demo_rules_only_discovery(demo_paths):
    import json

    stmt = load_statement(demo_paths["statement_csv"])
    ais = load_ais(demo_paths["ais_csv"])
    truth = json.loads(demo_paths["ground_truth"].read_text())
    items = build_inventory(stmt, ais, "State Bank of India", date(2025, 7, 12))
    result = score(items, truth)
    assert result["true_positives"] >= 10
    assert result["precision"] >= 0.9
    assert result["closed_items"] == [{"id": "CL01", "flagged_possibly_closed": True}]
    assert all(i.evidence for i in items)
    assert result["items_debiting_after_death"] >= 2
