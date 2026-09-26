"""All tunable settings in one place. Nothing here is a legal or procedural claim."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = ROOT / "knowledge"
RESULTS_DIR = ROOT / "results"
DEMO_DIR = ROOT / "data" / "demo"
DB_PATH = Path(os.environ.get("ANVESHA_DB", ROOT / "data" / "anvesha.db"))
METRICS_PATH = RESULTS_DIR / "metrics.json"
LLM_CACHE_PATH = RESULTS_DIR / "llm_cache.json"

# --- Recurring-series detection ---
AMOUNT_TOLERANCE = 0.05  # +/- 5% of the series median
DAY_TOLERANCE = 4  # +/- days around the expected interval
MIN_MONTHLY_OCCURRENCES = 3
MIN_SPARSE_OCCURRENCES = 2  # quarterly / annual
GAP_CONSISTENCY = 0.6  # share of gaps that must fit the inferred period
FREQUENCY_DAYS = {"monthly": 30.4, "quarterly": 91.3, "annual": 365.25}
CLOSED_AFTER_CYCLES = 3  # a series silent for longer than this is "possibly closed"
SINGLE_INSURER_DEBIT_MIN = 1000.0  # lone insurer debits above this stay as candidates

# --- Confidence scoring ---
CONF_ALIAS_AND_KEYWORD = 0.9
CONF_ALIAS_ONLY = 0.8
CONF_KEYWORD_ONLY = 0.65
CONF_SINGLE_PENALTY = 0.15
CONF_CORROBORATION_BONUS = 0.08
CONF_MAX = 0.97

# --- LLM ---
LLM_PROVIDER = os.environ.get("ANVESHA_LLM", "ollama")  # ollama | anthropic | none
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("ANVESHA_OLLAMA_MODEL", "llama3.2:3b")
ANTHROPIC_MODEL = os.environ.get("ANVESHA_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
LLM_TIMEOUT_S = 120
LLM_MIN_CONFIDENCE = 0.6

# --- Plan ---
DEATH_CERT_BUFFER = 2  # extra certified copies beyond one per institution
