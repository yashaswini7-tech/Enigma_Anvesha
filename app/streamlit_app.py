"""Anvesha - Streamlit UI. Run: uv run streamlit run app/streamlit_app.py"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anvesha import config  # noqa: E402
from anvesha.discover.inventory import TYPE_LABELS, Item, manual_item  # noqa: E402
from anvesha.ingest.ais import load_ais  # noqa: E402
from anvesha.ingest.statement import load_statement  # noqa: E402
from anvesha.letters import draft  # noqa: E402
from anvesha.llm import get_client  # noqa: E402
from anvesha.pipeline import load_demo, run  # noqa: E402
from anvesha.plan import intake  # noqa: E402
from anvesha.plan.documents import build_checklist  # noqa: E402
from anvesha.plan.engine import STAGES, build_plan, load_channels  # noqa: E402
from anvesha.track import store  # noqa: E402

st.set_page_config(page_title="Anvesha", layout="wide")

PROVIDERS = {
    "none": "Rules only (no language model)",
    "ollama": f"Local model on this computer (Ollama, {config.OLLAMA_MODEL})",
    "anthropic": "Claude (needs ANTHROPIC_API_KEY; redacted text leaves this computer)",
}
GROUP_ORDER = ["Assets", "Liabilities", "Still billing", "Digital"]
DISCLAIMER = (
    "This is not legal or financial advice. It is a plan built from the documents you gave us "
    "and from official sources listed with each step. Where a step says so, speak to a lawyer."
)


def _state() -> dict:
    ss = st.session_state
    ss.setdefault("items", None)
    ss.setdefault("manual", [])
    ss.setdefault("circ", intake.Circumstances())
    ss.setdefault("statement", None)
    ss.setdefault("ais", None)
    ss.setdefault("provider_used", "none")
    ss.setdefault("run_note", "")
    return ss


def all_items() -> list[Item]:
    ss = st.session_state
    return (ss["items"] or []) + ss["manual"]


def _resolve_provider(choice: str) -> tuple[str, str]:
    if choice == "none":
        return "none", ""
    if get_client(choice) is None:
        return "none", f"{PROVIDERS[choice]} is not available here, so we used rules only."
    return choice, ""


def discover(statement: pd.DataFrame, ais: pd.DataFrame | None, choice: str) -> None:
    ss = st.session_state
    provider, note = _resolve_provider(choice)
    circ: intake.Circumstances = ss["circ"]
    with st.spinner("Reading the statement and looking for patterns..."):
        ss["items"] = run(statement, ais, circ.main_bank, circ.date_of_death, provider)
    ss["statement"], ss["ais"] = statement, ais
    ss["provider_used"], ss["run_note"] = provider, note


# ------------------------------------------------------------------------------- Start
def tab_start() -> None:
    ss = st.session_state
    st.header("Start")
    st.write(
        "When someone dies, the hardest part is often finding out what they had. Anvesha reads "
        "the bank statement of their main account and, if you have it, their Annual Information "
        "Statement (AIS) from the income tax portal. Regular payments and credits show policies, "
        "loans, investments and subscriptions. You get a list with the evidence for each item, "
        "a plan in stages, the documents you will need, and draft letters. Everything stays on "
        "this computer."
    )
    choice = st.radio(
        "How should unclear transactions be read?",
        list(PROVIDERS),
        format_func=PROVIDERS.get,
        index=list(PROVIDERS).index(config.LLM_PROVIDER) if config.LLM_PROVIDER in PROVIDERS else 0,
        horizontal=False,
    )
    st.subheader("Try it with a made-up family")
    if st.button("Load demo family (the late Ramesh Kulkarni, synthetic data)"):
        statement, ais, meta, _ = load_demo()
        ss["circ"] = intake.Circumstances(
            deceased_name=meta["name"],
            date_of_death=date.fromisoformat(meta["date_of_death"]),
            main_bank=meta["bank"],
            relationship="Spouse",
            other_heirs=2,
            will_exists=intake.NO,
            nominees_registered=intake.UNKNOWN,
            joint_main_account=intake.NO,
            dependants=intake.YES,
            dispute=intake.NO,
            minors_among_heirs=intake.NO,
            state=meta["state"],
        )
        ss["manual"] = []
        discover(statement, ais, choice)
    st.subheader("Or use your own documents")
    with st.form("intake_form"):
        c = ss["circ"]
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Name of the person who died", c.deceased_name)
            dod = st.date_input(
                "Date of death", c.date_of_death or date.today(), max_value=date.today()
            )
            bank = st.text_input("Bank of the uploaded account", c.main_bank)
            stmt_file = st.file_uploader("Bank statement (CSV or PDF)", type=["csv", "pdf"])
            ais_file = st.file_uploader("AIS or Form 26AS extract (CSV, optional)", type=["csv"])
        with col2:
            rel = st.text_input("Your relationship to them", c.relationship)
            heirs = st.number_input(
                "Other legal heirs (count)", min_value=0, max_value=20, value=c.other_heirs or 0
            )
            minors = _choice("Are any heirs under 18?", c.minors_among_heirs)
            will = _choice("Was there a will?", c.will_exists)
            will_loc = _choice("Do you know where the will is?", c.will_location_known)
            nominees = _choice("Were nominees registered on most accounts?", c.nominees_registered)
            joint = _choice(
                "Was the main account joint, with 'either or survivor'?", c.joint_main_account
            )
            deps = _choice("Did anyone depend on their income?", c.dependants)
            dispute = _choice("Is there any disagreement among heirs?", c.dispute)
            prop = _choice("Did they own a house or land?", c.property_owned)
            state = st.text_input("State of residence", c.state)
        submitted = st.form_submit_button("Save and find what they had")
    if submitted:
        ss["circ"] = intake.Circumstances(
            deceased_name=name,
            date_of_death=dod,
            main_bank=bank,
            relationship=rel,
            other_heirs=int(heirs),
            minors_among_heirs=minors,
            will_exists=will,
            will_location_known=will_loc,
            nominees_registered=nominees,
            joint_main_account=joint,
            dependants=deps,
            dispute=dispute,
            property_owned=prop,
            state=state,
        )
        if stmt_file is not None:
            try:
                statement = load_statement(stmt_file, stmt_file.name)
                ais = load_ais(ais_file) if ais_file is not None else None
            except ValueError as exc:
                st.error(f"We could not read that file. {exc}")
                return
            discover(statement, ais, choice)
        elif ss["items"] is None:
            st.warning("Add a bank statement, or load the demo family.")
    if ss["items"] is not None:
        n_stmt = 0 if ss["statement"] is None else len(ss["statement"])
        n_ais = 0 if ss["ais"] is None else len(ss["ais"])
        st.success(
            f"Read {n_stmt} statement lines and {n_ais} AIS rows. Found {len(ss['items'])} "
            "items. Open 'What we found' to review them."
        )
        if ss["run_note"]:
            st.caption(ss["run_note"])


def _choice(label: str, value: str) -> str:
    return st.selectbox(label, intake.CHOICES, index=intake.CHOICES.index(value))


# ------------------------------------------------------------------------------- Found
def _evidence_frame(item: Item) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Source": e.source.upper() if e.source == "ais" else e.source.title(),
                "Where": e.line_ref,
                "Date": e.date,
                "Text": e.text,
                "Amount (Rs)": e.amount,
            }
            for e in item.evidence
        ]
    )


def item_card(item: Item) -> None:
    with st.container(border=True):
        top = st.columns([4, 1])
        top[0].markdown(f"**{item.label}** — {item.institution}")
        top[1].markdown(f"Confidence {item.confidence:.0%}")
        details = [item.amount_note] if item.amount_note else []
        details.append(
            "Seen in: " + ", ".join(s.upper() if s == "ais" else s for s in item.sources)
        )
        st.caption(" · ".join(details))
        if item.still_debiting:
            st.warning(
                f"Still being debited: {item.post_death_debits} payment(s), "
                f"Rs {item.post_death_total:,.0f}, after the date of death."
            )
        if item.status == "possibly_closed":
            st.info("Payments stopped more than three cycles ago. Possibly closed — confirm.")
        if item.origin == "llm":
            st.caption("Identified with help from the language model. Check the evidence.")
        if item.origin == "manual":
            st.caption("Entered by you. No statement evidence.")
        with st.expander(f"Evidence ({len(item.evidence)} line(s)) and reasoning"):
            st.write(item.rationale)
            st.dataframe(_evidence_frame(item), hide_index=True, width="stretch")


def tab_found() -> None:
    ss = st.session_state
    st.header("What we found")
    items = all_items()
    if ss["items"] is None:
        st.info("Start by loading the demo family or uploading a statement.")
        return
    draining = [i for i in items if i.still_debiting]
    st.write(
        f"{len(items)} items. {len(draining)} are still taking money from the account after the "
        "date of death. Each item lists the statement lines or AIS rows it comes from."
    )
    for group in GROUP_ORDER:
        members = [i for i in items if i.group == group]
        if not members:
            continue
        st.subheader(f"{group} ({len(members)})")
        cols = st.columns(2)
        for n, item in enumerate(members):
            with cols[n % 2]:
                item_card(item)
    st.subheader("Add something we missed")
    with st.form("manual_form", clear_on_submit=True):
        types = [t for t in TYPE_LABELS if t not in {"other"}]
        t = st.selectbox("What is it?", types, format_func=TYPE_LABELS.get)
        inst = st.text_input("Institution")
        note = st.text_input("What you know (policy number not needed)")
        if st.form_submit_button("Add") and inst.strip():
            ss["manual"].append(manual_item(t, inst.strip(), note.strip(), len(ss["manual"]) + 1))
            st.rerun()


# -------------------------------------------------------------------------------- Plan
def current_plan():
    ss = st.session_state
    return build_plan(all_items(), ss["circ"])


def tab_plan() -> None:
    ss = st.session_state
    st.header("Plan")
    st.info(DISCLAIMER)
    if ss["items"] is None:
        st.write("The plan appears after we have read a statement.")
        return
    actions = current_plan()
    lawyer = next((a for a in actions if a.kb_id == "lawyer_needed"), None)
    if lawyer:
        st.warning("Speak to a lawyer before filing claims. " + " ".join(lawyer.reasons))
    for stage, title in STAGES.items():
        stage_actions = [a for a in actions if a.stage == stage]
        st.subheader(f"{title} ({len(stage_actions)})")
        for a in stage_actions:
            with st.container(border=True):
                st.checkbox(a.text, key=f"plan::{a.key}")
                st.caption(f"Why: {a.why}")
                for r in a.reasons:
                    st.caption(f"Because: {r}")
                if a.note:
                    st.caption(a.note)
                if a.documents:
                    st.caption("Documents: " + "; ".join(a.documents))
                source = f"Source: [{a.source_name}]({a.source_url})" if a.source_url else ""
                badge = "" if a.verified else " :orange-badge[Confirm with the institution]"
                st.markdown(source + badge)
    st.subheader("Search for what is missing")
    st.write("See 'Missing pieces' for official search services for what a statement cannot show.")


# --------------------------------------------------------------------------- Documents
def tab_documents() -> None:
    ss = st.session_state
    st.header("Documents")
    if ss["items"] is None:
        st.write("The checklist appears after we have read a statement.")
        return
    checklist = build_checklist(current_plan(), all_items(), ss["circ"].main_bank)
    for need in checklist:
        with st.container(border=True):
            label = need.name if need.count is None else f"{need.name}: {need.count} copies"
            st.checkbox(label, key=f"doc::{need.name}")
            if need.explanation:
                st.caption(need.explanation)
            st.caption("Needed for: " + ", ".join(need.needed_for))


# ---------------------------------------------------------------------- Missing pieces
def tab_missing() -> None:
    st.header("Missing pieces")
    st.write(
        "A statement shows only what moved through one account. These official services can "
        "find what it cannot show."
    )
    found_types = {i.type for i in all_items()}
    for ch in load_channels():
        with st.container(border=True):
            st.markdown(f"**{ch['name']}**")
            st.write(ch["what"])
            covered = [TYPE_LABELS.get(t, t) for t in ch["finds"] if t not in found_types]
            if covered:
                st.caption("Could reveal: " + ", ".join(covered))
            st.caption("Have ready: " + "; ".join(ch["have_ready"]))
            badge = "" if ch["verified"] else " :orange-badge[Confirm with the institution]"
            st.markdown(f"[Open the official page]({ch['url']}){badge}")


# ---------------------------------------------------------------------------- Metrics
def _run_name(key: str, r: dict) -> str:
    if key == "rules_only":
        return "Rules only"
    return f"Rules + language model ({r.get('provider')}: {r.get('model')})"


def tab_metrics() -> None:
    st.header("How well it works")
    st.write(
        "We test discovery on the synthetic family, where we know the truth: 14 real items. An "
        "item counts as found only if its evidence lines overlap the true item's lines and the "
        "type family matches. These numbers are read from results/metrics.json, written by "
        "eval/score.py."
    )
    if not config.METRICS_PATH.exists():
        st.warning("No metrics yet. Run: uv run python eval/score.py")
        return
    metrics = json.loads(config.METRICS_PATH.read_text(encoding="utf-8"))
    rows = []
    for key, r in metrics["runs"].items():
        if "error" in r:
            rows.append(
                {
                    "Run": _run_name(key, r),
                    "Recall": None,
                    "Precision": None,
                    "Note": r["error"],
                }
            )
            continue
        rows.append(
            {
                "Run": _run_name(key, r),
                "Found": f"{r['true_positives']} of {r['ground_truth_items']}",
                "Recall": r["recall"],
                "Precision": r["precision"],
                "False positives": r["false_positives"],
                "Missed": ", ".join(f"{m['id']} {m['type']}" for m in r["missed"]) or "none",
                "Closed SIP flagged": all(c["flagged_possibly_closed"] for c in r["closed_items"]),
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    for key, r in metrics["runs"].items():
        if "per_type" not in r:
            continue
        with st.expander(
            f"Per item type: {('Rules only' if key == 'rules_only' else 'Rules + language model')}"
        ):
            st.dataframe(pd.DataFrame(r["per_type"]).T, width="stretch")
    st.caption(
        "Honest limits: the synthetic statement was written by the same team as the rules. The "
        "language-model prompt was adjusted while looking at the two hard items, so the "
        "rules + model figure is optimistic. Generated at " + metrics["generated_at"] + "."
    )


# ----------------------------------------------------------------------------- Letters
def tab_letters() -> None:
    ss = st.session_state
    st.header("Letters")
    items = [i for i in all_items() if i.status != "possibly_closed"]
    if not items:
        st.write("Letters appear after we have read a statement.")
        return
    item = st.selectbox("Letter for", items, format_func=lambda i: f"{i.label} — {i.institution}")
    kind = draft.letter_kind(item)
    st.caption(
        {
            "lender": "Intimation to a lender. It asks about insurance cover and does not stop "
            "payments.",
            "cancellation": "Cancellation of a subscription.",
            "intimation": "Intimation of death and request for the claim process.",
        }[kind]
    )
    with st.expander("Your details for the letter (kept only in this session)"):
        sender = draft.Sender(
            name=st.text_input("Your name", key="sender_name"),
            address=st.text_area("Your address", key="sender_address"),
            contact=st.text_input("Phone or email for replies", key="sender_contact"),
        )
    opening_key = f"opening::{item.id}"
    ss.setdefault(opening_key, draft.default_opening(item, ss["circ"]))
    if ss["provider_used"] != "none" and st.button("Polish the wording (facts stay the same)"):
        client = get_client(ss["provider_used"])
        if client is not None:
            with st.spinner("Asking the local model..."):
                ss[opening_key] = draft.polish_opening(client, ss[opening_key])
    text = draft.render(item, ss["circ"], sender, opening=ss[opening_key])
    text = st.text_area("Preview (you can edit it)", text, height=460, key=f"letter::{item.id}")
    fname = f"letter_{item.institution.replace(' ', '_').lower()}"
    col1, col2 = st.columns(2)
    col1.download_button(
        "Download .docx",
        draft.to_docx(text),
        f"{fname}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    col2.download_button("Download .txt", text, f"{fname}.txt", mime="text/plain")
    st.caption(
        "Fill in the reference number before sending. The statement lines are shown only to "
        "help the institution find the account."
    )


# ----------------------------------------------------------------------------- Tracker
def tab_tracker() -> None:
    ss = st.session_state
    st.header("Tracker")
    items = all_items()
    if items:
        store.sync_items(items)
    rows = store.all_rows()
    if not rows:
        st.write("Nothing to track yet.")
    for row in rows:
        cols = st.columns([3, 2, 3])
        cols[0].write(f"{row['label']} — {row['institution']}")
        status = cols[1].selectbox(
            "Status",
            store.STATUSES,
            index=store.STATUSES.index(row["status"]),
            key=f"track::{row['item_key']}",
            label_visibility="collapsed",
        )
        note = cols[2].text_input(
            "Note",
            row["note"],
            key=f"note::{row['item_key']}",
            label_visibility="collapsed",
            placeholder="Note (optional)",
        )
        if status != row["status"] or note != row["note"]:
            store.set_status(row["item_key"], status, note)
    st.subheader("Delete all our data")
    st.write(
        "Uploaded files are read in memory and never saved. This deletes the tracker file, the "
        "language-model cache and everything in this session."
    )
    if st.button("Delete all our data", type="primary"):
        removed = store.delete_all_data()
        for key in list(ss.keys()):
            del ss[key]
        _state()
        st.success(f"Deleted. {len(removed)} file(s) removed and the session was cleared.")


def main() -> None:
    _state()
    st.title("Anvesha")
    st.caption("Finding and closing a financial life, from the evidence the family already has.")
    tabs = st.tabs(
        [
            "Start",
            "What we found",
            "Plan",
            "Documents",
            "Letters",
            "Missing pieces",
            "Tracker",
            "How well it works",
        ]
    )
    with tabs[0]:
        tab_start()
    with tabs[1]:
        tab_found()
    with tabs[2]:
        tab_plan()
    with tabs[3]:
        tab_documents()
    with tabs[4]:
        tab_letters()
    with tabs[5]:
        tab_missing()
    with tabs[6]:
        tab_tracker()
    with tabs[7]:
        tab_metrics()


main()
