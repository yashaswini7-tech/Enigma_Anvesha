"""Bank statement (CSV or PDF) -> normalised transactions.

Output columns: ref, date, narration, debit, credit, balance, source, line_ref.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import BinaryIO

import pandas as pd

COLUMNS = ["ref", "date", "narration", "debit", "credit", "balance", "source", "line_ref"]

HEADER_ALIASES = {
    "date": ["txn date", "transaction date", "date", "value date", "tran date"],
    "ref": ["ref no", "ref no.", "reference", "chq/ref no", "cheque no", "ref"],
    "narration": ["description", "narration", "particulars", "remarks", "details"],
    "debit": ["debit", "withdrawal", "withdrawal amt", "dr", "withdrawals"],
    "credit": ["credit", "deposit", "deposit amt", "cr", "deposits"],
    "balance": ["balance", "closing balance", "running balance"],
}

_PDF_ROW = re.compile(r"^(\d{2}-\d{2}-\d{4})\s+(\S+)\s+(.+?)\s+(\S+)\s+(\S+)\s+([\d,]+\.\d{2})$")
_AMOUNT = re.compile(r"^[\d,]+(\.\d+)?$")


def _to_amount(value: object) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "nan"}:
        return 0.0
    return float(text)


def _map_headers(columns: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    lowered = {c.strip().lower(): c for c in columns}
    for field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                mapping[field] = lowered[alias]
                break
    missing = {"date", "narration", "debit", "credit"} - set(mapping)
    if missing:
        raise ValueError(f"Statement is missing columns: {sorted(missing)}")
    return mapping


def _finalise(df: pd.DataFrame) -> pd.DataFrame:
    df["date"] = pd.to_datetime(df["date"], dayfirst=True).dt.normalize()
    df["narration"] = df["narration"].astype(str).str.strip()
    for col in ("debit", "credit", "balance"):
        df[col] = df[col].map(_to_amount).astype(float)
    return df[COLUMNS].reset_index(drop=True)


def load_statement_csv(src: str | Path | BinaryIO) -> pd.DataFrame:
    raw = pd.read_csv(src, dtype=str, keep_default_na=False)
    cols = _map_headers(list(raw.columns))
    df = pd.DataFrame({field: raw[col] for field, col in cols.items()})
    if "balance" not in df:
        df["balance"] = ""
    df["line_ref"] = [f"statement row {i}" for i in range(2, len(df) + 2)]
    if "ref" not in df:
        df["ref"] = [f"ROW{i:05d}" for i in range(1, len(df) + 1)]
    df["source"] = "statement"
    return _finalise(df)


def parse_pdf_lines(pages: list[str]) -> pd.DataFrame:
    rows = []
    for page_no, text in enumerate(pages, start=1):
        for line_no, line in enumerate(text.splitlines(), start=1):
            m = _PDF_ROW.match(line.strip())
            if not m:
                continue
            day, ref, narration, debit, credit, balance = m.groups()
            if not (_AMOUNT.match(debit) or debit == "-") or not (
                _AMOUNT.match(credit) or credit == "-"
            ):
                continue
            rows.append(
                {
                    "date": day,
                    "ref": ref,
                    "narration": narration,
                    "debit": debit,
                    "credit": credit,
                    "balance": balance,
                    "line_ref": f"PDF page {page_no}, line {line_no}",
                    "source": "statement",
                }
            )
    if not rows:
        raise ValueError("No transaction lines recognised in the PDF.")
    return _finalise(pd.DataFrame(rows))


def load_statement_pdf(src: str | Path | BinaryIO) -> pd.DataFrame:
    import pdfplumber

    if isinstance(src, bytes):
        src = io.BytesIO(src)
    with pdfplumber.open(src) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return parse_pdf_lines(pages)


def load_statement(src: str | Path | BinaryIO, filename: str | None = None) -> pd.DataFrame:
    name = (filename or str(getattr(src, "name", src))).lower()
    if name.endswith(".pdf"):
        return load_statement_pdf(src)
    return load_statement_csv(src)
