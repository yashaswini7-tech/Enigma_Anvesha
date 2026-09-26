"""One call from files to inventory, shared by the app and the evaluator."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from anvesha.discover.inventory import Item, SeriesClassifier, build_inventory
from anvesha.ingest.ais import load_ais
from anvesha.ingest.statement import load_statement
from anvesha.synth.persona import ensure_demo


def llm_classifier_for(provider: str, model: str | None = None) -> SeriesClassifier | None:
    if provider == "none":
        return None
    from anvesha.discover.llm_classify import make_classifier

    return make_classifier(provider, model)


def run(
    statement: pd.DataFrame,
    ais: pd.DataFrame | None,
    main_bank: str,
    date_of_death: date | None,
    provider: str = "none",
    model: str | None = None,
) -> list[Item]:
    classifier = llm_classifier_for(provider, model)
    return build_inventory(statement, ais, main_bank, date_of_death, classifier)


def load_demo(out_dir: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    paths = ensure_demo(out_dir) if out_dir else ensure_demo()
    statement = load_statement(paths["statement_pdf"])
    ais = load_ais(paths["ais_csv"])
    meta = json.loads(paths["meta"].read_text(encoding="utf-8"))
    truth = json.loads(paths["ground_truth"].read_text(encoding="utf-8"))
    return statement, ais, meta, truth
