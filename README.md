# Anvesha

Finding and closing a deceased person's financial life, starting from the evidence the family already has.

## Team Name & Members

- **Team name:** `<Team Name>`
- **Members:**
  - Yashaswini Patil
  - Mahima Rai
  - Aditi Bhosale

## Problem Statement

When someone in India dies, the family has to work out what the person owned and owed. Then they must follow each institution's separate death-claim process. The hardest part is not the paperwork. It is **discovery**. Money sits unclaimed because nobody knew the policy, the PF account, the old deposit or the mutual fund folio existed. Meanwhile, auto-debits keep draining the account.

Anvesha starts from two kinds of evidence the family already has or can legally get:

- the **bank statement** of the deceased's main account, and
- the **Annual Information Statement (AIS)** from the income tax portal, which a legal heir can see after registering as the legal representative.

From these it builds an evidence-linked **inventory**, a staged **action plan**, one **document checklist**, draft **letters**, and pointers to the **official discovery channels** for what the evidence cannot show.

## How It Works

1. **Ingest.** Statement CSV or PDF (pdfplumber) and AIS CSV are normalised into transactions and rows.
2. **Detect recurring series.** Narrations are cleaned and grouped. Amounts are clustered within ±5% and frequency is inferred (monthly, quarterly, annual) within ±4 days. Series silent for more than three cycles are marked "possibly closed — confirm".
3. **Rules.** Institution aliases in `knowledge/institutions.yaml` and keywords (NACH, ECS, SIP, EMI, PREM, INT.PD, DIV, SALARY, PPF) assign an item type and a confidence.
4. **LLM fallback (optional).** Only series the rules cannot settle go to a language model. PAN, Aadhaar, phone, email, UPI and account numbers are redacted first, and redaction is enforced inside `anvesha/llm.py`. The model must return strict JSON with a known type, or its answer is dropped. Providers: `ollama` (local, default), `anthropic` (optional), `none`.
5. **Merge.** Statement and AIS evidence become one item per real account or policy. Every item keeps its source lines and a confidence score. Items still being debited after the date of death are flagged.
6. **Plan.** `anvesha/plan/engine.py` selects entries from `knowledge/procedures.yaml` using the family's circumstances: nominee or survivor, joint account, will, dispute, minors, property. Steps are grouped into This week / First month / Months 2–6, ordered by urgency, then money at stake. The engine writes no procedural text of its own.
7. **Knowledge base discipline.** Every entry in `knowledge/*.yaml` carries an official `source_url` and a `verified` flag. Unverified entries show a "Confirm with the institution" badge.
8. **Measure.** `eval/score.py` scores discovery against the synthetic ground truth and writes `results/metrics.json`. The app's "How well it works" tab reads that file.

The UI tabs are Start, What we found, Plan, Documents, Letters, Missing pieces, Tracker, and How well it works.

## Tech Stack

All dependencies are open source under OSI-approved licences.

| Component | Use | Licence |
|---|---|---|
| Python 3.11 | Language | PSF-2.0 |
| uv | Environment and dependency management | MIT / Apache-2.0 |
| Streamlit | UI | Apache-2.0 |
| pandas | Tabular processing | BSD-3-Clause |
| pdfplumber (with pdfminer.six) | PDF statement parsing | MIT |
| fpdf2 | Generating the synthetic PDF statement | LGPL-3.0 |
| Jinja2 | Letter templates | BSD-3-Clause |
| python-docx | .docx letters | MIT |
| PyYAML | Knowledge base files | MIT |
| SQLite (Python standard library) | Local tracker | Public domain |
| pytest, ruff | Tests and linting | MIT |
| Ollama | Local model server (optional) | MIT |
| anthropic SDK | Optional Claude provider | MIT |

**Model weights.** The default local model is `qwen2.5:7b` (Apache-2.0). We also measured `llama3.2:3b`, whose weights use the Llama 3.2 Community License. That licence is not OSI-approved, so it is not the default. No paid API is needed: the app runs fully with the `none` provider.

## Setup Instructions

```bash
git clone https://github.com/yashaswini7-tech/Enigma_Anvesha.git
cd Enigma_Anvesha
uv sync                                          # installs Python 3.11 deps from uv.lock
uv run python -m anvesha.synth.persona           # writes the demo family to data/demo/
uv run python eval/score.py --provider none      # rules-only metrics -> results/metrics.json
uv run streamlit run app/streamlit_app.py        # open http://localhost:8501
```

Optional local model:

```bash
ollama pull qwen2.5:7b
uv run python eval/score.py --provider ollama    # adds the rules + LLM run
```

Settings live in `anvesha/config.py`. Environment overrides:

- `ANVESHA_LLM=none|ollama|anthropic`
- `ANVESHA_OLLAMA_MODEL`
- `ANTHROPIC_API_KEY` (only for the optional Claude provider)

A `Makefile` wraps these steps as `make demo`, `make eval`, `make app` and `make test`.

## Results

Discovery on the synthetic persona (the late Ramesh Kulkarni: 14 real items, plus one SIP that was closed). This section is written by `eval/score.py` from `results/metrics.json`. Do not edit it by hand.

<!-- metrics:start -->
| Run | Found | Recall | Precision | False positives | Missed | Closed SIP flagged |
|---|---|---|---|---|---|---|
| Rules only | 12/14 | 0.857 | 1.0 | 0 | GT02 term_insurance, GT14 subscription | yes |
| Rules + LLM (ollama: `qwen2.5:7b`) | 14/14 | 1.0 | 1.0 | 0 | none | yes |
| Rules + LLM (ollama: `llama3.2:3b`) | 14/14 | 1.0 | 1.0 | 0 | none | yes |

_Generated 2026-09-26T11:29:35 by `eval/score.py`._
<!-- metrics:end -->

A predicted item counts as a true positive only when its evidence lines overlap the ground-truth item's lines and the type family matches (for example, term insurance vs life insurance is the same family). Duplicates count as false positives.

## Limitations

- **Synthetic evaluation only.** The persona, its narrations and the rules were written by the same team. Real statements are messier, so expect lower numbers on real data. The two "hard" items were designed to be outside the rules' vocabulary.
- **The LLM prompt was tuned on the demo's hard items.** The rules + LLM figure is therefore not a held-out result (see `DECISIONS.md`).
- **PDF parsing** targets text-based statements with one transaction per line. Scanned statements need OCR, which is out of scope.
- **Knowledge base coverage is partial.** Some entries are `verified: false`. Rupee thresholds for simplified claims are left out on purpose. Procedures can change, so always confirm with the institution.
- **One statement, one account.** Money that never touched that account (cash, physical share certificates, property) needs the discovery channels.
- **Account Aggregator is not used.** AA needs the account holder's own consent, which is impossible after death.
- **Not legal or financial advice.** The plan says when to speak to a lawyer.

## Privacy

Everything runs locally. Uploaded files are read in memory and never written to disk. The tracker is one local SQLite file. The "Delete all our data" button removes the tracker, the LLM cache and the session. Text is redacted before any LLM call.

## AI Usage

The code in this repository was written with Claude Code (Anthropic) during the hackathon, following the spec in `CLAUDE.md`. The team reviewed the output, ran the tests and made the design decisions recorded in `DECISIONS.md`. At runtime, a language model is optional: it is used only to classify transactions the rules cannot settle and to polish the wording of one letter paragraph. It never supplies facts.
