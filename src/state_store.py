"""
Local SQLite state store. This is what satisfies the brief's rerun
requirement: "Running the pipeline a second time must not re-propose
items that were already decided." Every proposal is keyed on a stable
dedupe_key (account_id + classification), not the random proposal_id,
so a second pipeline run recognizes "we already decided this."
"""
import sqlite3
import json
from datetime import datetime, timezone
from . import config


def _dedupe_key(proposal) -> str:
    """
    Stable key for detecting 'already decided' across reruns.

    CRITICAL BUG FOUND against live data: proposals with no account_id
    (classification "no_account_yet") all collapsed to the same literal
    key "NEW::no_account_yet", regardless of which facility they
    represented. Each upsert overwrote the previous one, silently
    dropping 6 of 7 new-facility proposals in one real run — the exact
    classification the exercise is built to test. Falls back to the
    proposed name (the only stable identifier available before an
    account exists) instead of a constant placeholder.
    """
    if proposal.account_id:
        return f"{proposal.account_id}::{proposal.classification}"
    proposed_name = (proposal.fields or {}).get("name", "").strip().lower()
    return f"NEW:{proposed_name}::{proposal.classification}"


class StateStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or config.STATE_DB_PATH
        self._init_schema()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_schema(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS proposals (
                    dedupe_key TEXT PRIMARY KEY,
                    proposal_id TEXT,
                    classification TEXT,
                    account_id TEXT,
                    evidence TEXT,
                    fields_json TEXT,
                    note TEXT,
                    status TEXT DEFAULT 'pending',   -- pending | approved | rejected
                    created_at TEXT,
                    decided_at TEXT
                )
            """)

    def already_decided(self, proposal) -> bool:
        with self._conn() as c:
            row = c.execute(
                "SELECT status FROM proposals WHERE dedupe_key = ? AND status != 'pending'",
                (_dedupe_key(proposal),),
            ).fetchone()
            return row is not None

    def upsert_pending(self, proposal):
        """Insert a new pending proposal if this dedupe_key hasn't been decided yet."""
        if self.already_decided(proposal):
            return False
        with self._conn() as c:
            c.execute("""
                INSERT INTO proposals (dedupe_key, proposal_id, classification, account_id,
                    evidence, fields_json, note, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                ON CONFLICT(dedupe_key) DO UPDATE SET
                    proposal_id=excluded.proposal_id, evidence=excluded.evidence,
                    fields_json=excluded.fields_json, note=excluded.note
                WHERE proposals.status = 'pending'
            """, (
                _dedupe_key(proposal), proposal.proposal_id, proposal.classification,
                proposal.account_id, proposal.evidence, json.dumps(proposal.fields),
                proposal.note, datetime.now(timezone.utc).isoformat(),
            ))
        return True

    def list_pending(self) -> list[dict]:
        with self._conn() as c:
            c.row_factory = sqlite3.Row
            rows = c.execute("SELECT * FROM proposals WHERE status = 'pending'").fetchall()
            return [dict(r) for r in rows]

    def decide(self, dedupe_key: str, status: str):
        assert status in {"approved", "rejected"}
        with self._conn() as c:
            c.execute(
                "UPDATE proposals SET status = ?, decided_at = ? WHERE dedupe_key = ?",
                (status, datetime.now(timezone.utc).isoformat(), dedupe_key),
            )
