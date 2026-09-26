from datetime import date

import pytest

from anvesha.ingest.ais import load_ais
from anvesha.ingest.statement import load_statement
from anvesha.pipeline import run
from anvesha.plan import intake
from anvesha.plan.documents import build_checklist, death_certificate_copies
from anvesha.plan.engine import build_plan, load_channels, load_procedures


@pytest.fixture(scope="module")
def items(demo_paths):
    stmt = load_statement(demo_paths["statement_csv"])
    ais = load_ais(demo_paths["ais_csv"])
    return run(stmt, ais, "State Bank of India", date(2025, 7, 12), "none")


def _circ(**kw):
    base = dict(main_bank="State Bank of India", date_of_death=date(2025, 7, 12))
    base.update(kw)
    return intake.Circumstances(**base)


def test_every_kb_entry_has_source_and_flag():
    for e in list(load_procedures()) + list(load_channels()):
        assert e["source_url"].startswith("http")
        assert isinstance(e["verified"], bool)


def test_every_action_comes_from_kb(items):
    kb_ids = {e["id"] for e in load_procedures()}
    for a in build_plan(items, _circ()):
        assert a.kb_id in kb_ids and a.source_url


def test_loans_are_never_told_to_stop_paying(items):
    loan_actions = [a for a in build_plan(items, _circ()) if a.kb_id == "loan_talk_first"]
    assert len(loan_actions) == 2
    assert all(a.stage == "this_week" and "Do not stop EMIs" in a.text for a in loan_actions)


def test_still_debiting_items_get_stop_actions(items):
    this_week = {a.kb_id for a in build_plan(items, _circ()) if a.stage == "this_week"}
    assert {"stop_subscription_debits", "stop_sip"} <= this_week


def test_nominee_branch_changes_bank_path(items):
    no_nom = {a.kb_id for a in build_plan(items, _circ(nominees_registered=intake.NO))}
    nom = {a.kb_id for a in build_plan(items, _circ(nominees_registered=intake.YES))}
    assert "bank_claim_no_nominee" in no_nom and "bank_claim_nominee" not in no_nom
    assert "bank_claim_nominee" in nom and "legal_heir_documents" not in nom


def test_joint_account_takes_survivor_path(items):
    acts = build_plan(items, _circ(joint_main_account=intake.YES, nominees_registered=intake.NO))
    main = [a for a in acts if a.institution == "State Bank of India" and "bank_claim" in a.kb_id]
    assert [a.kb_id for a in main] == ["bank_claim_nominee"]


def test_lawyer_step_triggers(items):
    calm = _circ(dispute=intake.NO, minors_among_heirs=intake.NO, will_exists=intake.YES)
    plain = [i for i in items if i.type != "home_loan"]
    assert not any(a.kb_id == "lawyer_needed" for a in build_plan(plain, calm))
    for kw in ({"dispute": intake.YES}, {"minors_among_heirs": intake.YES}):
        assert any(a.kb_id == "lawyer_needed" for a in build_plan(plain, _circ(**kw)))


def test_stage_order_and_closed_item_check(items):
    acts = build_plan(items, _circ())
    stages = [a.stage for a in acts]
    assert stages == sorted(stages, key=["this_week", "first_month", "months_2_6"].index)
    assert any(a.key.startswith("confirm_closed:") for a in acts)


def test_death_certificate_count(items):
    count, names = death_certificate_copies(items, "State Bank of India")
    assert count == len(names) + 2
    checklist = build_checklist(build_plan(items, _circ()), items, "State Bank of India")
    assert checklist[0].count == count
