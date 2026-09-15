# Requirement traceability

Every requirement stated in the assessment brief, mapped to the file
and function that satisfies it.

| Requirement (from brief) | File | Function / component |
|---|---|---|
| Scrape name, address, city, state, zip, care offerings | `src/scraper.py` | `scrape_bellhaven_locations()` |
| Confident match / needs-fix / no-account / vanished classifications | `src/matcher.py` | `match_and_classify()` |
| Duplicate handling via `duplicate_of_account` + `Inactive` | `src/matcher.py` | `match_and_classify()` — Pass 3 |
| CHOW rule (`lifetime_revenue` + `outstanding_ar`) | `src/chow.py` | `decide_chow_action()`, `apply_chow_decision()` |
| CHOW rule correctness | `tests/test_chow.py` | 6 unit tests, all quadrants |
| Review app shows evidence, approve/reject | `src/review_app.py` | `TEMPLATE`, `index()`, `decide()` |
| Nothing writes without approval | `src/review_app.py` | `_apply_to_crm()` — only write path in codebase |
| Proposal shape validated before write | `src/validators.py` | `ProposedChange` |
| Daily schedule config | `.github/workflows/daily-hygiene.yml` | `on.schedule.cron` |
| Reruns don't re-propose decided items | `src/state_store.py` | `StateStore.already_decided()`, `upsert_pending()` |
| CRM actually corrected, not just tooled | *(process, not code)* | Run `python -m src.pipeline`, then approve real proposals in the review app before the deadline |
| Live 45-min demo + small live change | `README.md` | "Making a live change" table |
| Honest time-spent disclosure | *(submission form)* | Log hours as you work, not reconstructed after |
| Writeup: matching approach, AI usage, next steps | `README.md` | "How I used AI tools" / "What I'd build next" |

## Isolated, individually testable/demoable functions

- `chow.decide_chow_action(lifetime_revenue, outstanding_ar)` — pure, no I/O
- `chow.apply_chow_decision(account, correct_parent_id, decision)` — pure, no I/O
- `matcher.name_similarity(a, b)` — pure
- `matcher.find_best_account_match(scraped, crm_accounts)` — pure
- `matcher.find_bellhaven_parent(crm_accounts)` — pure
- `state_store.StateStore.already_decided(proposal)` — single-responsibility, testable against an in-memory/temp SQLite file
- `crm_client.CRMClient.*` — mockable; nothing else in the codebase imports `requests` directly except the scraper
