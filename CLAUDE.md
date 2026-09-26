# Anvesha — finding and closing a deceased person's financial life

## Time budget: 6-hour hackathon

Coding stops at 5h15. The last 45 minutes are for rehearsing the demo and recording a 2-minute fallback video. A smaller thing that runs end to end beats a bigger thing that half runs. When in doubt, cut scope, not rules.

## Hackathon rules this build must respect

- The repository is named `Enigma_<TeamName>`, is created after the 9:00 AM start, and has `csisiesgst` added as a collaborator. All code is written fresh during the event; nothing is copied from other repos or hackathon projects.
- **Commit and push at the end of every build block** (and at least every 45 minutes), with clear messages describing what was built. The commit history is our evidence of fresh work, and nothing may be left unpushed at submission.
- Only open-source libraries and frameworks. Before adding any dependency, confirm its licence is OSI-approved and list it in the README. No paid APIs are required for the app to work (see Stack).
- No external images or icons. Use Streamlit's built-in components and plain text/Unicode only. No bank, insurer or platform logos anywhere.
- The README must contain these sections: Team Name & Members, Problem Statement, Tech Stack (with licences), Setup Instructions. Also include How It Works, Results (the discovery metrics), Limitations, and an AI Usage note saying the code was written with Claude Code during the hackathon.

## The problem, and the angle that makes this different

When someone in India dies, the family has to work out what the person owned and owed, then deal with each institution's separate death-claim process. The hardest part is not the paperwork. It is **discovery**: money sits unclaimed because nobody knew the policy, the PF account, the old savings account or the mutual fund folio existed.

Most teams will build a checklist with a chatbot. Anvesha instead starts from evidence the family already has or can legally get:

- **Bank statements** of the deceased's main account. Recurring debits and credits are a map of their financial life. A monthly debit to an insurer suggests a life or health policy. An ECS/NACH debit to a finance company suggests a loan. A SIP debit suggests a mutual fund folio. Interest or dividend credits suggest deposits and shares. Card-like merchant debits reveal subscriptions still billing.
- **The Annual Information Statement (AIS / Form 26AS)** from the income tax portal, which legal heirs can access after registering as the legal representative. It lists interest, dividends and securities transactions reported by institutions, which exposes accounts the family never saw.
- **Documents found at home**: policy bonds, passbooks, loan letters. These get photographed or typed in.

From that evidence Anvesha builds an **inventory** (assets, liabilities, subscriptions, digital accounts). It turns the inventory into a **prioritised action plan** tailored to the family's circumstances, with the documents each step needs and drafted letters. It also points to the official discovery channels for what the evidence can't reveal: RBI's UDGAM portal for unclaimed deposits, insurers' unclaimed-amount search pages, IEPF for unclaimed shares and dividends, and EPFO.

Headline demo: upload a synthetic statement plus AIS for "late Ramesh Kulkarni". The tool finds 12 of his 14 hidden financial items, with the exact statement lines as evidence. It flags two auto-debits still draining the account, and it produces a week-by-week plan and ready-to-send intimation letters. The detection rate is measured against ground truth, not asserted.

## Non-negotiable rules

1. **No invented facts about law or procedure.** Every procedural claim (which form, which documents, who to contact, any time limit or threshold) comes from `knowledge/*.yaml`. Every entry there carries an official `source_url` and a `verified` flag. Entries you could not check against an official source are marked `verified: false`, and the UI shows them with a "confirm with the institution" badge. Never put a specific rupee threshold or deadline in the KB without a source.
2. **Not legal or financial advice.** The UI states this once, plainly, on the plan screen. The tool also tells the user when a step needs a lawyer, for example a disputed estate, no will with multiple heirs, or property.
3. **Evidence for every finding.** Each inventory item links to the statement lines or AIS rows that produced it, plus a confidence score. No item appears without evidence, except items the user entered manually, which are labelled as such.
4. **Privacy of a grieving family's data.** Everything runs locally. Uploaded files and extracted data live in memory or a local SQLite file that can be deleted from the UI in one click. Before any text is sent to an LLM, mask account numbers, PAN, Aadhaar, phone numbers and emails with a tested redaction function. The LLM never sees raw identifiers.
5. **Measured, not claimed.** Discovery precision and recall are computed against the synthetic ground truth by `eval/score.py` and written to `results/metrics.json`. The UI reads them from there.
6. **Tone.** Plain, calm, short sentences. No cheerful copy, no emojis, no exclamation marks. This is for people in the worst week of their year.

## Stack

Python 3.11 managed with `uv`. Streamlit for the UI. pandas for statements, `pdfplumber` for PDF statements, Jinja2 for letter templates, `python-docx` for .docx letters, and the standard library's SQLite for the tracker. pytest and ruff for tests and linting. All of these are open source.

The LLM is used for two jobs only: classifying transactions the rules can't settle, and polishing letter wording. It sits behind one interface in `anvesha/llm.py`, with the provider set in config:

- `ollama` (default): a small open-weight model served locally by Ollama, e.g. `qwen2.5:3b` or `llama3.2:3b`. It is free, open, and keeps family data on the machine.
- `anthropic` (optional): Claude via the Anthropic SDK, if an `ANTHROPIC_API_KEY` is set.
- `none`: rules-only discovery and template-only letters.

The app must run fully with `none`. Report metrics for rules-only and for whichever LLM provider was used.

## Repository layout

```
anvesha/
  config.py
  llm.py                 # provider switch: ollama | anthropic | none
  synth/
    persona.py           # generates the demo persona: statement CSV + PDF, AIS CSV, ground truth
  ingest/
    statement.py         # CSV/PDF -> normalised transactions (date, narration, debit, credit, balance)
    ais.py               # AIS/26AS CSV -> normalised rows
  discover/
    recurring.py         # detects recurring series (amount/day tolerance, frequency)
    rules.py             # narration patterns -> item type (insurer names, NACH/ECS, SIP, EMI, interest...)
    llm_classify.py      # fallback for unresolved recurring series, redacted input, JSON output
    inventory.py         # merges evidence into items with type, institution, confidence, evidence refs
  plan/
    intake.py            # the family's circumstances (see below)
    engine.py            # inventory + circumstances + KB -> ordered actions by stage
    documents.py         # consolidated document checklist, incl. how many certified death-certificate copies
  letters/
    templates/           # Jinja2 templates per letter type
    draft.py             # fills templates; optional LLM polish of wording only, never of facts
  privacy/
    redact.py
  track/
    store.py             # SQLite: item status (not started / intimated / docs sent / settled / closed)
knowledge/
  institutions.yaml      # insurer, lender, AMC, platform names and narration aliases
  procedures.yaml        # per item type: steps, documents, channel, source_url, verified
  discovery_channels.yaml# UDGAM, IEPF, EPFO, insurer unclaimed search, MF consolidated statements, etc.
eval/
  score.py
app/
  streamlit_app.py
tests/
results/
Makefile
README.md
```

## Synthetic demo persona

`synth/persona.py` generates Ramesh Kulkarni, 58, a salaried engineer. It produces 18 months of a savings-account statement (CSV and a simple PDF), an AIS extract, and `ground_truth.json` listing his 14 real items. Mix of:

- Life insurance premium (annual), term plan (monthly), health policy (annual)
- Home loan EMI via NACH, personal loan EMI to an NBFC
- Two SIPs through different AMCs or registrars
- PPF deposits, an old fixed deposit visible only through interest credits in AIS
- A second bank account visible only through AIS interest
- Dividend credits from shares (implies a demat account)
- EPF, visible through the salary credit narration and AIS
- Three subscriptions still billing: streaming, cloud storage, a gym

Add realistic noise: groceries, fuel, UPI transfers to family, one-off purchases, a cancelled SIP that stopped a year ago (should be flagged "possibly closed", not ignored). Make two items deliberately hard, for example an insurer referenced only by an abbreviation. Use invented but realistic-looking narrations. Do not use real account numbers. Use real institution names only as recognisable categories in narrations, with no logos or branding.

## Intake: circumstances that change the plan

Ask briefly, one screen, all optional:

- Relationship of the user to the deceased; other legal heirs (count, any minors)
- Was there a will? Is it known where it is?
- Joint accounts and whether nominees were registered, where known
- Were there dependants relying on the salary or pension?
- Any known disputes among heirs
- State of residence (some procedures vary; show "varies by state" rather than guessing)

The plan engine uses these to branch. Examples: a joint account with survivorship takes a simpler path than a sole account; a nominee-registered item takes a different path from one needing a legal heir or succession certificate; minors among heirs or a dispute trigger a "speak to a lawyer" step. Branch logic must reference KB entries, not hard-coded legal claims.

## Plan engine

Group actions into stages, with each action saying why it's there:

1. **This week**: get certified copies of the death certificate (count needed = number of institutions in the inventory, plus a buffer), secure documents, and stop harm. That means flagging auto-debits that should be paused or cancelled, and informing lenders to check whether any loan carried insurance cover. It must not advise stopping loan payments. It tells the family to talk to the lender first, because missed EMIs have consequences.
2. **First month**: intimate each insurer, bank and AMC; file claims where a nominee exists; cancel subscriptions; secure digital accounts (email, phone number, cloud).
3. **Months 2–6**: legal-heir or succession documentation where needed, transmission of shares and MF units, EPF claims, closing accounts, income tax filing for the deceased by the legal representative.
4. **Search for what's missing**: for categories the evidence can't cover, point to the official discovery channels in `discovery_channels.yaml`, with what details each needs.

Order within a stage by urgency, then by money at stake.

## Discovery method

1. Normalise transactions.
2. Detect recurring series: group by cleaned narration tokens, allowing about ±5% amount tolerance and about ±4 days date tolerance. Infer frequency (monthly, quarterly, annual). Keep single annual debits to known insurers as candidates.
3. Apply `rules.py` using `institutions.yaml` aliases and keywords (NACH, ECS, SIP, EMI, PREM, INT.PD, DIV).
4. Send series the rules can't resolve to the LLM with redacted narrations. It returns strict JSON: type, institution guess, confidence, one-line rationale. Validate the schema and drop low-confidence output.
5. Merge statement and AIS evidence into one item per real-world account or policy.
6. Mark items whose recurring pattern stopped more than 3 cycles ago as "possibly closed — confirm".

`eval/score.py` reports precision and recall per item type, plus overall, both rules-only and rules+LLM. That comparison is part of the demo.

## UI (Streamlit, tabs in demo order)

1. **Start**: one-paragraph explanation, intake form, file upload (or "load demo family").
2. **What we found**: inventory cards grouped as Assets / Liabilities / Still billing / Digital. Each card shows institution, type, estimated amount, confidence and an expandable evidence panel with the source lines. There is also an "Add something we missed" form.
3. **Plan**: staged actions with checkboxes, why each matters, documents needed and a KB source link. Unverified KB entries are badged.
4. **Documents**: one consolidated checklist, with the death-certificate copy count explained.
5. **Letters**: pick an item, preview the intimation or cancellation letter, download as .docx or .txt.
6. **Missing pieces**: official discovery channels with what to have ready.
7. **Tracker**: status per item and a "delete all our data" button.
8. **How well it works** (for judges): precision and recall from `results/metrics.json`, rules-only vs rules+LLM.

## Build order, time-boxed

If a block overruns by more than 20 minutes, simplify it and move on.

- **0:00–1:00. Persona and ingestion.** Build `persona.py` with ground truth, CSV/PDF statement ingestion and AIS ingestion. Checkpoint: normalised DataFrames print, and ground truth has 14 items.
- **1:00–2:15. Discovery.** Build recurring detection, rules, `institutions.yaml`, inventory merge and `score.py`. Checkpoint: rules-only recall printed; aim for 10 or more of 14 without the LLM.
- **2:15–3:00. Knowledge base and redaction.** Write `procedures.yaml` and `discovery_channels.yaml`. Use web fetches to check entries against official sites (RBI, IRDAI, EPFO, SEBI/IEPF, income tax portal) and record source URLs; mark anything unchecked `verified: false`. Build `redact.py` with tests. Then the LLM fallback classifier. Checkpoint: rules+LLM metrics written.
- **3:00–4:30. Plan engine and UI.** Build intake, the plan engine, the documents checklist, and UI tabs 1–4 and 8. Checkpoint: the demo family runs end to end in the browser.
- **4:30–5:15. Letters, missing pieces, tracker, README.** In that order; drop the tracker first if time is short. The README follows the required sections in the hackathon rules above. Leave `<Team Name>` and `<Members>` placeholders for the team to fill in.
- **5:15–6:00. No new code.** Final commit and push, check `csisiesgst` has access, rehearse, record the fallback video.

Out of scope: real bank or Account Aggregator integration (AA needs the account holder's own consent, which is not possible after death, so say that in the pitch), OCR of photographed documents, multi-user accounts, Hindi/regional-language UI. These are good next-step slides.

## Conventions

- Type hints, small functions, `ruff` clean, `uv run pytest -q` passing before each new block.
- All config (tolerances, thresholds, model name) in `config.py`.
- Log real trade-offs in `DECISIONS.md` in one or two sentences each.
- Don't add features not listed here without saying so first.
