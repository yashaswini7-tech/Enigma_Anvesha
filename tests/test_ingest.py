import json

from anvesha.ingest.ais import load_ais
from anvesha.ingest.statement import load_statement, parse_pdf_lines


def test_ground_truth_has_14_items_with_evidence(demo_paths):
    gt = json.loads(demo_paths["ground_truth"].read_text())
    assert len(gt["items"]) == 14
    assert all(i["statement_refs"] or i["ais_refs"] for i in gt["items"])
    assert len(gt["closed_items"]) == 1


def test_csv_and_pdf_statements_agree(demo_paths):
    csv_df = load_statement(demo_paths["statement_csv"])
    pdf_df = load_statement(demo_paths["statement_pdf"])
    cols = ["ref", "date", "narration", "debit", "credit", "balance"]
    assert len(csv_df) == len(pdf_df) > 200
    assert csv_df[cols].equals(pdf_df[cols])


def test_statement_is_consistent(demo_paths):
    df = load_statement(demo_paths["statement_csv"])
    assert ((df["debit"] > 0) ^ (df["credit"] > 0)).all()
    assert (df["balance"] >= 0).all()
    assert df["ref"].is_unique


def test_pdf_parser_skips_non_rows():
    page = "Savings account statement\n01-03-2024  TXN00001  UPI/P2P/X  15,000.00  -  1,000.00"
    df = parse_pdf_lines([page])
    assert len(df) == 1 and df.loc[0, "debit"] == 15000.0 and df.loc[0, "credit"] == 0.0


def test_ais_loads(demo_paths):
    df = load_ais(demo_paths["ais_csv"])
    assert len(df) == 13
    assert set(df["category"]) >= {"Salary", "Dividend", "Interest from deposit"}
