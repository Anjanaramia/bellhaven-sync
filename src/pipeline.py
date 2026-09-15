"""
Orchestrates one pipeline run: scrape -> fetch CRM -> match -> validate
-> write new pending proposals into the state store. Does NOT write to
the CRM — that only happens from the review app, on explicit approval.

Run directly:  python -m src.pipeline
Run daily via: .github/workflows/daily-hygiene.yml
"""
import logging
from pydantic import ValidationError
from .scraper import scrape_bellhaven_locations
from .crm_client import CRMClient
from .matcher import match_and_classify
from .state_store import StateStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pipeline")


def run():
    log.info("Scraping Bellhaven site...")
    locations = scrape_bellhaven_locations()
    log.info("Scraped %d locations", len(locations))

    log.info("Fetching CRM accounts...")
    crm = CRMClient()
    accounts = crm.list_accounts()
    log.info("Fetched %d CRM accounts", len(accounts))

    log.info("Matching + classifying...")
    proposals = match_and_classify(locations, accounts)
    log.info("Generated %d candidate proposals", len(proposals))

    store = StateStore()
    added, skipped, invalid = 0, 0, 0
    for p in proposals:
        try:
            # ProposedChange objects are already validated at construction
            # (pydantic validates on __init__); re-validate defensively here
            # in case a caller builds one from raw dict input.
            p.model_validate(p.model_dump())
        except ValidationError as e:
            log.warning("Dropping invalid proposal for account %s: %s", p.account_id, e)
            invalid += 1
            continue

        if store.upsert_pending(p):
            added += 1
        else:
            skipped += 1

    log.info("Run complete: %d new pending, %d already-decided (skipped), %d invalid", added, skipped, invalid)


if __name__ == "__main__":
    run()
