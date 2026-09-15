# Bellhaven sync — CRM data hygiene pipeline

Keeps Clipboard's CRM accurate against Bellhaven Senior Living's real
locations: scrapes their site, matches against CRM accounts, proposes
corrections, and writes nothing until a human approves it.

## Use case

Roughly 60% of Clipboard's LTC facility accounts sit under a parent
company, and parent/facility links quietly break as facilities get
bought, renamed, closed, or consolidated. Because corporate-owned
facilities are sold and contracted differently than independents,
an inaccurate ownership picture directly affects how the sales team
works an account. This pipeline finds and proposes fixes for those
breaks — new locations missing from the CRM, stale parent links,
closed locations still marked active, and duplicate accounts — while
respecting one hard constraint: accounts with active billing history
must never be silently re-parented (see CHOW rule below).

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the diagram and per-component
detail. Quick version:

```
GitHub Actions (daily) → Scraper → Matcher+CHOW → Pydantic validator
                                        ↕ state store (SQLite)
                                   Review app (human) → CRM API
```

Nothing writes to the CRM except the review app, and only on approval.

## Quick start

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in BELLHAVEN_SITE_URL after you locate it
export $(cat .env | xargs)

# 1. Run the pipeline — scrapes + matches + queues proposals (writes nothing)
python -m src.pipeline

# 2. Review and approve — this is the only step that writes to the CRM
python -m src.review_app
# open http://127.0.0.1:5000

# 3. Run tests for the CHOW rule
pytest tests/ -v
```

**Field names and pagination are now confirmed against a real API
response** (`account_id`, `billing_street/city/state/zip`, `care_type`
as a single string, `data`/`page`/`page_size`/`total` pagination) —
`src/crm_client.py`, `src/matcher.py`, and `src/chow.py` were updated
to match. **Still unverified:** the exact `BELLHAVEN_SITE_URL` and its
real HTML markup — `src/scraper.py`'s selectors are built from one
devtools screenshot of a single facility page, not the full site.

## Requirement traceability

See [TRACEABILITY.md](TRACEABILITY.md) for a full requirement → file →
function mapping.

## How I used AI tools

[Fill in honestly before submitting — which tool(s), what you asked
for, what you changed or rejected from its output, and where you
personally verified correctness (e.g. the CHOW test suite). This is
graded; don't downplay it, and don't leave it generic.]

## What I'd build next

- Email notification to record owners before a proposal auto-expires
  unreviewed (production concern, out of scope for the 2-hour build).
- Before/after report with revenue-at-stake, generated from the state
  store.
- Fuzzy-match tuning using a labeled sample once real match/mismatch
  examples accumulate, instead of a fixed threshold.
- File-based export path only if a downstream team needs offline CRM
  snapshots — not needed while direct API access exists.

## Making a live change (cheat sheet for the demo)

| Ask | Touch this file / function |
|---|---|
| Change matching threshold | `src/config.py` → `FUZZY_MATCH_CONFIDENT` / `FUZZY_MATCH_CANDIDATE` |
| Change the CHOW rule | `src/chow.py` → `decide_chow_action()` (has its own test file) |
| Add a new classification outcome | `src/matcher.py` → `match_and_classify()`, add case to `ClassificationType` in `src/validators.py` |
| Add a required field to proposals | `src/validators.py` → `ProposedChange` |
| Add a scraped field | `src/scraper.py` → `SELECTORS` + `ScrapedLocation` |
| Change review-app fields shown | `src/review_app.py` → `TEMPLATE` |
| Change schedule cadence | `.github/workflows/daily-hygiene.yml` → `cron` |
| Change idempotency key | `src/state_store.py` → `_dedupe_key()` |
