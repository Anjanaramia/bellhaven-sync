Bellhaven sync — CRM data hygiene pipeline
Keeps Clipboard's CRM accurate against Bellhaven Senior Living's real
locations: scrapes their site, matches against CRM accounts, proposes
corrections, and writes nothing until a human approves it.
Use case
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
Architecture
See ARCHITECTURE.md for the diagram and per-component
detail. Quick version:
```
GitHub Actions (daily) → Scraper → Matcher+CHOW → Pydantic validator
                                        ↕ state store (SQLite)
                                   Review app (human) → CRM API
```
Nothing writes to the CRM except the review app, and only on approval.
Quick start
```bash
python3 -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env   # already has the confirmed CRM + site URLs filled in

# 1. Run the pipeline — scrapes + matches + queues proposals (writes nothing)
python -m src.pipeline

# 2. Review and approve — this is the only step that writes to the CRM
python -m src.review_app
# open http://127.0.0.1:5000

# 3. Independently verify every change against the live API afterward
python verify_all.py

# 4. Run the test suite
pytest tests/ -v
```
`.env` loads automatically via `python-dotenv` — no manual export step
needed on any OS.
Confirmed end-to-end against live data, not just unit tests: field
names and pagination against a real API response, the scraper against
the real Bellhaven site (including its own independent 3-page
pagination and a homepage-only link outside the paginated directory),
and the full matcher against the real 121-account CRM dataset. Every
bug listed below was found and fixed this way, then verified against
the live CRM with `verify_all.py` before submission.
Requirement traceability
See TRACEABILITY.md for a full requirement → file →
function mapping.
How I used AI tools
I used Claude to design, build, and — critically — stress-test this
pipeline against real data.
I drafted an initial architecture drawing on the Revenue Recovery
Engine, a self-directed CRM project I'd built for realtors, and asked
Claude to review it against the assessment's actual requirements. It
caught two gaps I'd missed: I hadn't accounted for the CHOW rule or
idempotent reruns. With those fixed, I had Claude build the pipeline
component by component — scraper, matcher with CHOW logic isolated as
its own testable function, Pydantic validation, a SQLite state store,
and a local review app.
I didn't take the output on faith. Once I had live API and site
access, I fed Claude the real account schema and real scraped HTML,
which didn't match the first build's assumptions. Testing the rebuilt
code against real data surfaced three genuine bugs: a fuzzy-matching
threshold that scored two unrelated facilities — "Bellhaven of
Carlisle" and "Bellhaven of New Carlisle" — as a 91% match purely from
a shared prefix, which would have renamed the wrong CRM account; a
dedupe-key collision that silently dropped 6 of 7 new-facility
proposals with zero errors thrown; and a hardcoded API token in a
helper script, caught before it reached a public repo.
Before finishing, I asked Claude for a way to independently verify
every change against the live CRM rather than trusting the review
app's confirmations. That verification surfaced two more issues:
rejecting one bad match had left a real facility with no CRM account
at all, and a manual rename hadn't actually taken effect the first
time. Separately, I manually caught three CRM accounts the matcher had
flagged as closures that were actually active facilities under old,
pre-rebrand names — confirmed by cross-checking addresses and finding
staff contacts on Bellhaven's own email domain — and corrected those
by hand.
My role throughout was to direct the build, supply the real data that
exposed the AI's wrong assumptions, and independently verify the
result before calling anything done.
What I'd build next
A few things I'd add given more than two hours:
A conflict check for contradictory proposals on the same account. The
matcher's passes run independently, so one real account (a duplicate
Owosso record) generated both a duplicate proposal and a
vanished_from_website proposal at once — correct and wrong, side by
side. I'd have the pipeline detect when two proposals target the same
account and either merge them or force a single resolution before
either reaches the review app.
A stealth-rebrand signal in the matcher itself. I caught three
accounts that looked like closures but were actually active facilities
under old, non-Bellhaven-branded names — found only by manually
cross-checking addresses and staff email domains. That check is
mechanical enough to automate: cross-reference every
vanished_from_website candidate's billing address against every
no_account_yet candidate's address before finalizing either
classification, and surface a "possible rebrand" flag when they match.
A fallback proposal when a fuzzy match is rejected. When I rejected
the false "Bellhaven of Zanesville → Cedar Trail of Zanesville" match,
the pipeline had no alternative proposal ready — the real new facility
was left with no CRM account until I created it manually. I'd have the
matcher always generate a low-confidence no_account_yet proposal
alongside any ambiguous needs_fix match, so a human rejecting one path
isn't left with nothing.
Email notification to record owners, as in my original design, gated
behind the single reviewer's approval rather than replacing it —
useful once this moves past a single-analyst workflow.
A before/after report — account counts and revenue-at-stake by
classification, generated from the state store after each run, so the
sales team can see impact at a glance without reading the raw proposal
log.
Making a live change (cheat sheet for the demo)
Ask	Touch this file / function
Change matching threshold	`src/config.py` → `FUZZY_MATCH_CONFIDENT` / `FUZZY_MATCH_CANDIDATE`
Change the CHOW rule	`src/chow.py` → `decide_chow_action()` (has its own test file)
Add a new classification outcome	`src/matcher.py` → `match_and_classify()`, add case to `ClassificationType` in `src/validators.py`
Add a required field to proposals	`src/validators.py` → `ProposedChange`
Add a scraped field	`src/scraper.py` → `SELECTORS` + `ScrapedLocation`
Change review-app fields shown	`src/review_app.py` → `TEMPLATE`
Change schedule cadence	`.github/workflows/daily-hygiene.yml` → `cron`
Change idempotency key	`src/state_store.py` → `_dedupe_key()`
