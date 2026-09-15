"""
Matches scraped Bellhaven locations against CRM accounts and classifies
each into one of six outcomes. This is the core "judgment" layer —
kept as small, named, testable functions so a live-demo change
("what if we also check phone number", "raise the confidence threshold")
touches one function, not a rewrite.
"""
import uuid
from difflib import SequenceMatcher
from . import config
from .chow import decide_chow_action, apply_chow_decision
from .validators import ProposedChange


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _normalize_city(city: str) -> str:
    return (city or "").strip().lower()


def find_best_account_match(scraped, crm_accounts: list[dict]) -> tuple[dict | None, float]:
    """
    Returns (best_matching_account_or_None, similarity_score).

    CRITICAL: city-gated. Confirmed from live data that name alone is not
    a safe match key — the site's "Amberly Manor" (Hudson, OH, Bellhaven)
    and the CRM's "Amberly Manor" (Colorado Springs, CO, Juniper Point
    Healthcare — a different company) score 1.0 on name alone. Without a
    city check, the matcher would confidently link two unrelated
    facilities and corrupt an account that belongs to a different company
    entirely. Only accounts whose billing_city matches the scraped city
    are considered candidates at all; a same-named account in a different
    city is treated as no match, not a weak match.
    """
    scraped_city = _normalize_city(scraped.city)
    candidates = [a for a in crm_accounts if _normalize_city(a.get("billing_city")) == scraped_city]
    if not candidates:
        return None, 0.0

    best, best_score = None, 0.0
    for acc in candidates:
        score = name_similarity(scraped.name, acc.get("name", ""))
        if score > best_score:
            best, best_score = acc, score
    return best, best_score


def find_bellhaven_parent(crm_accounts: list[dict]) -> dict | None:
    """
    CONFIRMED from the live CRM browser: the parent account's name field
    is literally "Bellhaven Senior Living (Parent Account)" — the
    "(Parent Account)" suffix is baked into the name, not a UI label.
    Match on a substring + no parent_id of its own (i.e. it's top-level),
    rather than an exact string, so this survives minor naming variants.
    """
    for acc in crm_accounts:
        name = acc.get("name", "").strip().lower()
        if "bellhaven senior living" in name and not acc.get("parent_id"):
            return acc
    return None


def _mk_proposal(classification, account_id, evidence, fields=None, note="") -> ProposedChange:
    return ProposedChange(
        proposal_id=str(uuid.uuid4()),
        account_id=account_id,
        classification=classification,
        evidence=evidence,
        fields=fields or {},
        note=note,
    )


def match_and_classify(scraped_locations, crm_accounts: list[dict]) -> list[ProposedChange]:
    """
    Core matching pass. Produces one ProposedChange per action needed —
    accounts that are already correct produce nothing.
    """
    proposals: list[ProposedChange] = []
    bellhaven_parent = find_bellhaven_parent(crm_accounts)
    matched_account_ids = set()

    # --- Pass 1: for each scraped (real, current) location, find its CRM account ---
    for loc in scraped_locations:
        # Exclude accounts already claimed by an earlier scraped location in
        # this run — otherwise two same-named CRM accounts (a real duplicate
        # pair) can both match the same account, falsely orphaning the other
        # into "vanished_from_website" instead of recognizing it as present.
        available = [a for a in crm_accounts if a["account_id"] not in matched_account_ids]
        acc, score = find_best_account_match(loc, available)

        if acc and score >= config.FUZZY_MATCH_CANDIDATE:
            matched_account_ids.add(acc["account_id"])

            fields = {}
            evidence_parts = [f"Matched '{loc.name}' to '{acc.get('name')}' in {acc.get('billing_city')} (name score={score:.2f})."]

            # Name correction — independent of parent correctness. A confident
            # match can still have a stale name (e.g. "Bellhaven Health Care
            # Center" vs "Bellhaven Healthcare Centre") that a parent-only
            # check would silently skip.
            if acc.get("name", "").strip() != loc.name.strip():
                fields["name"] = loc.name
                evidence_parts.append(f"Name differs from CRM ('{acc.get('name')}') — proposing correction.")

            chow_action = None
            if bellhaven_parent and acc.get("parent_id") != bellhaven_parent["account_id"]:
                decision = decide_chow_action(acc.get("lifetime_revenue"), acc.get("outstanding_ar"))
                chow_action = apply_chow_decision(acc, bellhaven_parent["account_id"], decision)
                evidence_parts.append(f"Parent mismatch — {decision.reason}")

            if chow_action and chow_action["type"] == "chow_split":
                proposals.append(_mk_proposal(
                    "needs_fix", acc["account_id"],
                    evidence=" ".join(evidence_parts),
                    fields={**fields, "_chow_split": chow_action},
                    note="Preserves old account (billing history); creates new account under correct parent; links via chow_current_account on approval.",
                ))
            elif chow_action:  # simple reparent, plus any name fix, in one proposal
                proposals.append(_mk_proposal(
                    "needs_fix", acc["account_id"],
                    evidence=" ".join(evidence_parts),
                    fields={**fields, **chow_action["payload"]},
                ))
            elif fields:  # name fix only, parent already correct
                proposals.append(_mk_proposal(
                    "needs_fix", acc["account_id"],
                    evidence=" ".join(evidence_parts),
                    fields=fields,
                ))
            # else: confident match, name correct, parent correct — nothing to propose.

        else:
            proposals.append(_mk_proposal(
                "no_account_yet", None,
                evidence=f"'{loc.name}' found on website, no CRM match >= {config.FUZZY_MATCH_CANDIDATE}.",
                fields={
                    "name": loc.name, "billing_street": loc.address, "billing_city": loc.city,
                    "billing_state": loc.state, "billing_zip": loc.zip, "care_type": loc.care_type,
                    "parent_id": bellhaven_parent["account_id"] if bellhaven_parent else None,
                },
            ))

    # --- Pass 2: CRM accounts under Bellhaven with no matching scraped location ---
    if bellhaven_parent:
        for acc in crm_accounts:
            if acc.get("parent_id") != bellhaven_parent["account_id"] or acc["account_id"] in matched_account_ids:
                continue
            proposals.append(_mk_proposal(
                "vanished_from_website", acc["account_id"],
                evidence=f"'{acc.get('name')}' is under Bellhaven in CRM but not found on the current site listing.",
                fields={"status": "Needs Review"},
                note="No longer listed on operator site — confirm closed vs. site lag before deactivating.",
            ))

    # --- Pass 3: duplicate detection within CRM accounts under Bellhaven ---
    if bellhaven_parent:
        bh_accounts = [a for a in crm_accounts if a.get("parent_id") == bellhaven_parent["account_id"]]
        seen = []
        for acc in bh_accounts:
            dup_of = None
            for other in seen:
                if name_similarity(acc.get("name", ""), other.get("name", "")) >= config.FUZZY_MATCH_CONFIDENT:
                    dup_of = other
                    break
            if dup_of:
                proposals.append(_mk_proposal(
                    "duplicate", acc["account_id"],
                    evidence=f"'{acc.get('name')}' duplicates '{dup_of.get('name')}' (id={dup_of['account_id']}).",
                    fields={"duplicate_of_account": dup_of["account_id"], "status": "Inactive"},
                ))
            else:
                seen.append(acc)

    return proposals
