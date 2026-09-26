"""Detect recurring series in a normalised statement."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from anvesha import config

_NON_ALNUM = re.compile(r"[^A-Z0-9 ]+")


def clean_narration(text: str) -> str:
    """Upper-case, drop punctuation and any token carrying digits or X-masks."""
    words = _NON_ALNUM.sub(" ", str(text).upper()).split()
    kept = [w for w in words if not re.search(r"\d", w) and not re.fullmatch(r"X{3,}\w*", w)]
    return " ".join(kept)


@dataclass
class Series:
    series_id: str
    key: str
    direction: str  # "debit" | "credit"
    refs: list[str]
    dates: list[date]
    amounts: list[float]
    narrations: list[str]
    line_refs: list[str]
    frequency: str  # monthly | quarterly | annual | single
    status: str = "active"  # active | possibly_closed
    extra: dict = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.refs)

    @property
    def median_amount(self) -> float:
        return float(statistics.median(self.amounts))

    @property
    def first(self) -> date:
        return min(self.dates)

    @property
    def last(self) -> date:
        return max(self.dates)


def _amount_clusters(rows: pd.DataFrame, col: str) -> list[pd.DataFrame]:
    rows = rows.sort_values(col)
    clusters: list[list[int]] = []
    current: list[int] = []
    for idx, amt in rows[col].items():
        if current and abs(amt - statistics.median(rows.loc[current, col])) > (
            config.AMOUNT_TOLERANCE * statistics.median(rows.loc[current, col])
        ):
            clusters.append(current)
            current = []
        current.append(idx)
    if current:
        clusters.append(current)
    return [rows.loc[c].sort_values("date") for c in clusters]


def _tolerance(period: float) -> float:
    return max(config.DAY_TOLERANCE, 0.02 * period)


def infer_frequency(dates: list[date]) -> str | None:
    if len(dates) < config.MIN_SPARSE_OCCURRENCES:
        return None
    ordered = sorted(dates)
    gaps = [(b - a).days for a, b in zip(ordered, ordered[1:], strict=False)]
    median_gap = statistics.median(gaps)
    for name, period in config.FREQUENCY_DAYS.items():
        tol = _tolerance(period)
        if abs(median_gap - period) > tol:
            continue
        fit = sum(abs(g - period) <= tol for g in gaps) / len(gaps)
        min_n = (
            config.MIN_MONTHLY_OCCURRENCES if name == "monthly" else config.MIN_SPARSE_OCCURRENCES
        )
        if fit >= config.GAP_CONSISTENCY and len(dates) >= min_n:
            return name
    return None


def detect_series(df: pd.DataFrame) -> tuple[list[Series], pd.DataFrame]:
    """Return recurring series and the transactions not in any series."""
    work = df.copy()
    work["key"] = work["narration"].map(clean_narration)
    work["direction"] = work["debit"].gt(0).map({True: "debit", False: "credit"})
    work["amount"] = work["debit"].where(work["debit"] > 0, work["credit"])
    statement_end = work["date"].max().date()
    series: list[Series] = []
    used: set[int] = set()
    for (key, direction), group in work.groupby(["key", "direction"], sort=True):
        for cluster in _amount_clusters(group, "amount"):
            dates = [d.date() for d in cluster["date"]]
            freq = infer_frequency(dates)
            if not freq:
                continue
            s = Series(
                series_id=f"S{len(series) + 1:02d}",
                key=key,
                direction=direction,
                refs=list(cluster["ref"]),
                dates=dates,
                amounts=list(cluster["amount"]),
                narrations=list(dict.fromkeys(cluster["narration"])),
                line_refs=list(cluster["line_ref"]),
                frequency=freq,
            )
            silent_days = (statement_end - s.last).days
            if silent_days > config.CLOSED_AFTER_CYCLES * config.FREQUENCY_DAYS[freq]:
                s.status = "possibly_closed"
            series.append(s)
            used.update(cluster.index)
    singles = work.loc[~work.index.isin(used)].drop(columns=["key"])
    return series, singles
