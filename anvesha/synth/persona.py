"""Synthetic demo persona: the late Ramesh Kulkarni.

Produces an 18-month savings-account statement (CSV and PDF), an AIS extract (CSV) and
``ground_truth.json`` listing his 14 real financial items with the exact evidence rows that
belong to each. Everything is invented. Institution names appear only as recognisable
categories inside narrations. Account and policy numbers are masked placeholders.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from anvesha.config import DEMO_DIR

START = date(2024, 3, 1)
END = date(2025, 8, 31)
DATE_OF_DEATH = date(2025, 7, 12)
CARD = "4591XXXXXXXX2231"


@dataclass
class Txn:
    day: date
    narration: str
    debit: float = 0.0
    credit: float = 0.0
    item: str | None = None  # ground-truth item id, or "closed:<id>"
    ref: str = ""
    balance: float = 0.0


@dataclass
class AisRow:
    financial_year: str
    category: str
    entity: str
    entity_identifier: str
    amount: float
    count: int
    item: str | None = None
    ref: str = ""


@dataclass
class Persona:
    meta: dict
    txns: list[Txn] = field(default_factory=list)
    ais: list[AisRow] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)
    closed_items: list[dict] = field(default_factory=list)


GROUND_TRUTH = [
    ("GT01", "life_insurance", "LIC", "Annual endowment premium, auto-debit.", False),
    ("GT02", "term_insurance", "PNB MetLife", "Monthly term premium; abbreviated narration.", True),
    ("GT03", "health_insurance", "Niva Bupa", "Annual family health renewal.", False),
    ("GT04", "home_loan", "HDFC Bank", "Home loan EMI via NACH.", False),
    ("GT05", "personal_loan", "Bajaj Finance", "Personal loan EMI to an NBFC.", False),
    ("GT06", "mutual_fund", "Axis Mutual Fund", "SIP through the CAMS registrar.", False),
    ("GT07", "mutual_fund", "Mirae Asset Mutual Fund", "SIP via KFintech registrar.", False),
    ("GT08", "ppf", "State Bank of India", "Quarterly PPF deposits.", False),
    ("GT09", "fixed_deposit", "Bank of Baroda", "Old FD at a second bank; AIS only.", False),
    ("GT10", "demat_account", "Demat account", "Implied by dividend credits.", False),
    ("GT11", "epf", "Kaveri Engineering Pvt Ltd", "EPF implied by salary.", False),
    ("GT12", "subscription", "Netflix", "Streaming, still billing.", False),
    ("GT13", "cloud_storage", "Google One", "Cloud storage, still billing.", False),
    ("GT14", "subscription", "Powerzone Club", "Gym via UPI mandate; opaque name.", True),
]
CLOSED = [("CL01", "mutual_fund", "ICICI Prudential Mutual Fund", "SIP stopped Aug 2024.")]


def _months(start: date, end: date) -> list[tuple[int, int]]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _business_day(d: date) -> date:
    """Auto-debits falling on a weekend are presented on the next Monday."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _fy(d: date) -> str:
    y = d.year if d.month >= 4 else d.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def _monthly(
    txns: list[Txn],
    dom: int,
    narration: str,
    amount: float,
    item: str | None,
    until: date = END,
    since: date = START,
    credit: bool = False,
) -> None:
    for y, m in _months(since, until):
        d = _business_day(date(y, m, dom))
        if since <= d <= until:
            txns.append(
                Txn(d, narration, 0.0 if credit else amount, amount if credit else 0.0, item)
            )


def _statement(rng: random.Random) -> list[Txn]:
    t: list[Txn] = []
    last_salary = date(2025, 6, 30)
    # --- the 14 items that leave statement traces ---
    for d in (date(2024, 6, 18), date(2025, 6, 17)):
        t.append(Txn(d, "ECS DR LIC OF INDIA PREM POL 8812XXXX34", 24850.0, item="GT01"))
    _monthly(t, 5, "ACH D- PNBMET TRM 004512XXXX", 1318.0, "GT02")
    for d in (date(2024, 5, 22), date(2025, 5, 21)):
        t.append(Txn(d, "BIL/ONL/NIVA BUPA HEALTH INS/RENEWAL", 18640.0, item="GT03"))
    _monthly(t, 5, "NACH DR HDFC BANK LTD HL EMI 6600XXXX91", 38420.0, "GT04")
    _monthly(t, 2, "ACH D- BAJAJ FINANCE LTD 4XXXXXX2201", 9870.0, "GT05")
    _monthly(t, 10, "BIL/ACH/CAMS/AXIS MUTUAL FUND SIP", 5000.0, "GT06")
    _monthly(t, 15, "ACH D- KFINTECH MIRAE ASSET MF SIP", 3000.0, "GT07")
    for d in (
        date(2024, 4, 10),
        date(2024, 7, 10),
        date(2024, 10, 10),
        date(2025, 1, 10),
        date(2025, 4, 10),
    ):
        t.append(Txn(_business_day(d), "TRANSFER TO PPF A/C XXXXXXX7730", 12500.0, item="GT08"))
    for d, co, amt in (
        (date(2024, 6, 26), "INFOSYS LTD FINAL DIV", 3400.0),
        (date(2024, 7, 29), "ITC LTD DIVIDEND", 1860.0),
        (date(2024, 10, 28), "INFOSYS LTD INTERIM DIV", 1820.0),
        (date(2025, 6, 24), "INFOSYS LTD FINAL DIV", 3780.0),
    ):
        t.append(Txn(d, f"ACH C- {co} 00XXXX19", credit=amt, item="GT10"))
    _monthly(
        t,
        28,
        "NEFT CR KAVERI ENGINEERING PVT LTD SALARY",
        146300.0,
        "GT11",
        until=last_salary,
        credit=True,
    )
    _monthly(t, 8, f"POS {CARD} NETFLIX.COM", 649.0, "GT12")
    _monthly(t, 12, f"POS {CARD} GOOGLE*GOOGLE ONE", 130.0, "GT13")
    _monthly(t, 3, "UPI/MANDATE/PWRZONE CLUB/MTHLY", 2500.0, "GT14")
    # --- a SIP cancelled a year before the end: should surface as "possibly closed" ---
    _monthly(t, 20, "ACH D- CAMS ICICI PRU MF SIP", 2000.0, "closed:CL01", until=date(2024, 8, 31))
    # --- noise ---
    _monthly(t, 1, "UPI/P2P/SUNITA R KULKARNI/HOUSEHOLD", 15000.0, None, until=DATE_OF_DEATH)
    for y, m in _months(START, END):
        amt = round(rng.uniform(1650, 3450), 0)
        t.append(Txn(_business_day(date(y, m, 18)), "BILLDESK/MSEDCL ELECTRICITY BILL", amt))
    for q_end in (
        date(2024, 3, 31),
        date(2024, 6, 30),
        date(2024, 9, 30),
        date(2024, 12, 31),
        date(2025, 3, 31),
        date(2025, 6, 30),
    ):
        t.append(Txn(q_end, "INT.PD SB QTRLY", credit=round(rng.uniform(1500, 2300), 0)))
    d = START
    active_until = DATE_OF_DEATH
    while d < active_until:
        d += timedelta(days=rng.randint(4, 11))
        if d >= active_until:
            break
        kind = rng.random()
        if kind < 0.45:
            ref = rng.randint(100000, 999999)
            t.append(
                Txn(d, f"UPI/P2M/DMART AVENUE SUPERMARTS/{ref}", round(rng.uniform(850, 4600), 0))
            )
        elif kind < 0.7:
            t.append(Txn(d, f"POS {CARD} HPCL FUEL STN KOTHRUD", round(rng.uniform(1500, 3600), 0)))
        elif kind < 0.85:
            t.append(Txn(d, "ATM WDL SBI ATM KOTHRUD PUNE", float(rng.choice([2000, 5000, 10000]))))
        else:
            t.append(
                Txn(
                    d,
                    f"UPI/P2P/ANIKET R KULKARNI/{rng.choice(['FEES', 'BOOKS', 'TRIP'])}",
                    float(rng.choice([3000, 7500, 12000])),
                )
            )
    t.append(Txn(date(2024, 10, 30), f"POS {CARD} CROMA RETAIL PUNE", 42990.0))
    t.append(Txn(date(2024, 11, 14), "AMAZON PAY INDIA PVT LTD", 3899.0))
    t.append(Txn(date(2025, 2, 9), "AMAZON PAY INDIA PVT LTD", 1249.0))
    t.append(Txn(date(2024, 12, 20), "UPI/P2M/MAKEMYTRIP INDIA/HOLIDAY", 38450.0))
    return t


def _ais(txns: list[Txn]) -> list[AisRow]:
    def fy_sum(item: str, fy: str, credit: bool) -> tuple[float, int]:
        rows = [x for x in txns if x.item == item and _fy(x.day) == fy]
        return sum(x.credit if credit else x.debit for x in rows), len(rows)

    sal_24, n_24 = fy_sum("GT11", "2024-25", True)
    rows = [
        AisRow(
            "2023-24",
            "Salary",
            "KAVERI ENGINEERING PVT LTD",
            "TAN PNEKXXXXX2B",
            2098400.0,
            12,
            "GT11",
        ),
        AisRow(
            "2024-25",
            "Salary",
            "KAVERI ENGINEERING PVT LTD",
            "TAN PNEKXXXXX2B",
            round(sal_24 * 1.2, 0),
            n_24,
            "GT11",
        ),
        AisRow(
            "2023-24",
            "Interest from savings bank",
            "STATE BANK OF INDIA",
            "TAN MUMSXXXXX1E",
            6420.0,
            1,
        ),
        AisRow(
            "2024-25",
            "Interest from savings bank",
            "STATE BANK OF INDIA",
            "TAN MUMSXXXXX1E",
            7915.0,
            1,
        ),
        AisRow(
            "2023-24",
            "Interest from deposit",
            "BANK OF BARODA",
            "TAN BRDBXXXXX4C",
            21340.0,
            1,
            "GT09",
        ),
        AisRow(
            "2024-25",
            "Interest from deposit",
            "BANK OF BARODA",
            "TAN BRDBXXXXX4C",
            22105.0,
            1,
            "GT09",
        ),
        AisRow("2023-24", "Dividend", "INFOSYS LIMITED", "TAN BLRIXXXXX7F", 4640.0, 2, "GT10"),
    ]
    div_inf, n_inf = 0.0, 0
    for x in txns:
        if x.item == "GT10" and "INFOSYS" in x.narration and _fy(x.day) == "2024-25":
            div_inf, n_inf = div_inf + x.credit, n_inf + 1
    rows.append(
        AisRow("2024-25", "Dividend", "INFOSYS LIMITED", "TAN BLRIXXXXX7F", div_inf, n_inf, "GT10")
    )
    rows.append(AisRow("2024-25", "Dividend", "ITC LIMITED", "TAN KOLIXXXXX3A", 1860.0, 1, "GT10"))
    for item, entity in (("GT06", "AXIS MUTUAL FUND"), ("GT07", "MIRAE ASSET MUTUAL FUND")):
        amt, n = fy_sum(item, "2024-25", False)
        rows.append(
            AisRow(
                "2024-25", "Purchase of mutual fund units", entity, "PAN AAATXXXX1K", amt, n, item
            )
        )
    amt, n = fy_sum("closed:CL01", "2024-25", False)
    rows.append(
        AisRow(
            "2024-25",
            "Purchase of mutual fund units",
            "ICICI PRUDENTIAL MUTUAL FUND",
            "PAN AAAAXXXX3M",
            amt,
            n,
            "closed:CL01",
        )
    )
    rows.append(
        AisRow(
            "2024-25",
            "Sale of mutual fund units",
            "ICICI PRUDENTIAL MUTUAL FUND",
            "PAN AAAAXXXX3M",
            13480.0,
            1,
            "closed:CL01",
        )
    )
    for i, r in enumerate(rows, start=1):
        r.ref = f"AIS-{i}"
    return rows


def build_persona(seed: int = 7) -> Persona:
    rng = random.Random(seed)
    txns = sorted(_statement(rng), key=lambda x: (x.day, x.credit == 0, x.narration))
    balance = 340000.0
    for i, x in enumerate(txns, start=1):
        x.ref = f"TXN{i:05d}"
        balance = round(balance - x.debit + x.credit, 2)
        x.balance = balance
    ais = _ais(txns)
    persona = Persona(
        meta={
            "name": "Ramesh Kulkarni",
            "age": 58,
            "occupation": "Salaried engineer",
            "date_of_death": DATE_OF_DEATH.isoformat(),
            "bank": "State Bank of India",
            "account": "XXXXXXX4821",
            "period_start": START.isoformat(),
            "period_end": END.isoformat(),
            "state": "Maharashtra",
        },
        txns=txns,
        ais=ais,
    )
    for item_id, typ, inst, note, hard in GROUND_TRUTH:
        persona.items.append(_gt_entry(item_id, typ, inst, note, hard, txns, ais))
    for item_id, typ, inst, note in CLOSED:
        persona.closed_items.append(
            _gt_entry(item_id, typ, inst, note, False, txns, ais, tag=f"closed:{item_id}")
        )
    return persona


def _gt_entry(item_id, typ, inst, note, hard, txns, ais, tag=None) -> dict:
    tag = tag or item_id
    stmt = [x.ref for x in txns if x.item == tag]
    ais_refs = [r.ref for r in ais if r.item == tag]
    sources = [s for s, refs in (("statement", stmt), ("ais", ais_refs)) if refs]
    return {
        "id": item_id,
        "type": typ,
        "institution": inst,
        "note": note,
        "hard": hard,
        "sources": sources,
        "statement_refs": stmt,
        "ais_refs": ais_refs,
    }


def _fmt(v: float) -> str:
    return f"{v:,.2f}" if v else ""


def write_outputs(persona: Persona, out_dir: Path = DEMO_DIR) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "statement_csv": out_dir / "statement.csv",
        "statement_pdf": out_dir / "statement.pdf",
        "ais_csv": out_dir / "ais.csv",
        "ground_truth": out_dir / "ground_truth.json",
        "meta": out_dir / "meta.json",
    }
    with paths["statement_csv"].open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Txn Date", "Ref No", "Description", "Debit", "Credit", "Balance"])
        for x in persona.txns:
            w.writerow(
                [
                    x.day.strftime("%d-%m-%Y"),
                    x.ref,
                    x.narration,
                    _fmt(x.debit),
                    _fmt(x.credit),
                    f"{x.balance:,.2f}",
                ]
            )
    with paths["ais_csv"].open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "Sr No",
                "Financial Year",
                "Information Category",
                "Reporting Entity",
                "Entity Identifier",
                "Amount",
                "Transaction Count",
            ]
        )
        for i, r in enumerate(persona.ais, start=1):
            w.writerow(
                [
                    i,
                    r.financial_year,
                    r.category,
                    r.entity,
                    r.entity_identifier,
                    f"{r.amount:.2f}",
                    r.count,
                ]
            )
    _write_pdf(persona, paths["statement_pdf"])
    gt = {"persona": persona.meta, "items": persona.items, "closed_items": persona.closed_items}
    paths["ground_truth"].write_text(json.dumps(gt, indent=2), encoding="utf-8")
    paths["meta"].write_text(json.dumps(persona.meta, indent=2), encoding="utf-8")
    return paths


def _write_pdf(persona: Persona, path: Path) -> None:
    from fpdf import FPDF

    pdf = FPDF(orientation="L", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Courier", size=9)
    m = persona.meta
    for line in (
        f"Savings account statement - {m['bank']}",
        f"Account holder: {m['name'].upper()}   Account: {m['account']}",
        f"Period: {START:%d-%m-%Y} to {END:%d-%m-%Y}",
        "",
    ):
        pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Courier", size=7.5)
    header = (
        f"{'Date':<10}  {'Ref No':<8}  {'Narration':<48}  {'Debit':>12}  {'Credit':>12}  "
        f"{'Balance':>14}"
    )
    pdf.cell(0, 4, header, new_x="LMARGIN", new_y="NEXT")
    for x in persona.txns:
        row = (
            f"{x.day:%d-%m-%Y}  {x.ref:<8}  {x.narration[:48]:<48}  "
            f"{_fmt(x.debit) or '-':>12}  {_fmt(x.credit) or '-':>12}  {x.balance:>14,.2f}"
        )
        pdf.cell(0, 3.6, row, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))


def ensure_demo(out_dir: Path = DEMO_DIR) -> dict[str, Path]:
    """Generate the demo files if they are not already on disk."""
    return write_outputs(build_persona(), out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic demo persona.")
    parser.add_argument("--out", type=Path, default=DEMO_DIR)
    args = parser.parse_args()
    paths = write_outputs(build_persona(), args.out)
    for name, p in paths.items():
        print(f"{name}: {p}")


if __name__ == "__main__":
    main()
