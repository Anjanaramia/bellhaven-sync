"""
Regression test for a real bug found against live data: multiple
no_account_yet proposals (account_id=None) all collapsed to the same
dedupe_key, so each upsert silently overwrote the previous one — 6 of 7
new-facility proposals disappeared from a real run with zero errors.
"""
import os
from src.state_store import StateStore
from src.validators import ProposedChange


def _new_proposal(name):
    return ProposedChange(
        proposal_id=f"p-{name}", account_id=None, classification="no_account_yet",
        evidence=f"'{name}' found on website, no CRM match.",
        fields={"name": name, "parent_id": "p1"},
    )


def test_multiple_new_facilities_do_not_collide(tmp_path):
    db_path = str(tmp_path / "test_state.db")
    store = StateStore(db_path=db_path)

    names = ["Bellhaven of Kettering", "Bellhaven of Chagrin Falls", "Bellhaven Willow Creek",
             "Bellhaven at Union Square", "Bellhaven of Batavia", "Bellhaven of Carlisle",
             "Bellhaven of Chesterton"]
    for name in names:
        store.upsert_pending(_new_proposal(name))

    pending = store.list_pending()
    pending_names = {p["fields_json"] for p in pending}
    assert len(pending) == 7, f"expected all 7 new facilities to survive, got {len(pending)}"
    assert len(pending_names) == 7, "each new facility must have a distinct stored row"
