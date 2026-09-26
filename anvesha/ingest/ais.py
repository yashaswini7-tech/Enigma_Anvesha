"""AIS / Form 26AS extract (CSV) -> normalised rows.

Output columns: ref, financial_year, category, entity, entity_identifier, amount, count,
source, line_ref.
"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

import pandas as pd

COLUMNS = [
    "ref",
    "financial_year",
    "category",
    "entity",
    "entity_identifier",
    "amount",
    "count",
    "source",
    "line_ref",
]

HEADER_ALIASES = {
    "financial_year": ["financial year", "fy", "assessment year"],
    "category": ["information category", "information description", "category", "nature"],
    "entity": ["reporting entity", "information source", "deductor", "source", "entity"],
    "entity_identifier": ["entity identifier", "tan", "pan of entity", "identifier"],
    "amount": ["amount", "amount (rs)", "reported amount"],
    "count": ["transaction count", "count", "no. of transactions"],
}


def load_ais(src: str | Path | BinaryIO) -> pd.DataFrame:
    raw = pd.read_csv(src, dtype=str, keep_default_na=False)
    lowered = {c.strip().lower(): c for c in raw.columns}
    df = pd.DataFrame(index=raw.index)
    for field, aliases in HEADER_ALIASES.items():
        col = next((lowered[a] for a in aliases if a in lowered), None)
        df[field] = raw[col] if col else ""
    if (df["category"] == "").all() or (df["entity"] == "").all():
        raise ValueError("AIS file needs an information category and a reporting entity column.")
    df["category"] = df["category"].str.strip()
    df["entity"] = df["entity"].str.strip().str.upper()
    df["amount"] = df["amount"].str.replace(",", "").replace("", "0").astype(float)
    df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(1).astype(int)
    df["ref"] = [f"AIS-{i}" for i in range(1, len(df) + 1)]
    df["line_ref"] = [f"AIS row {i}" for i in range(1, len(df) + 1)]
    df["source"] = "ais"
    return df[COLUMNS].reset_index(drop=True)
