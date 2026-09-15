"""
Change-of-ownership (CHOW) rule — isolated per the brief's explicit SOP:

  "If the account has revenue history AND outstanding AR greater than
   zero, our billing team needs the old account preserved... leave the
   existing account exactly as it is, create a new account for the
   facility under the correct parent, and set chow_current_account on
   the OLD account to the new account's id. If the account has no
   revenue history, or no outstanding AR, re-parent the existing
   account directly."

Kept as a single pure function with no I/O, deliberately, so it can be
unit-tested directly and demoed live without touching the matcher or
the CRM client.
"""
from dataclasses import dataclass
from typing import Literal

Action = Literal["reparent_direct", "preserve_and_chow"]


@dataclass
class ChowDecision:
    action: Action
    reason: str


def decide_chow_action(lifetime_revenue: float | None, outstanding_ar: float | None) -> ChowDecision:
    """
    Pure decision function — no network calls, no CRM writes.
    Called before any re-parent proposal is generated.
    """
    has_revenue_history = bool(lifetime_revenue) and lifetime_revenue > 0
    has_outstanding_ar = bool(outstanding_ar) and outstanding_ar > 0

    if has_revenue_history and has_outstanding_ar:
        return ChowDecision(
            action="preserve_and_chow",
            reason=(
                f"lifetime_revenue={lifetime_revenue} and outstanding_ar={outstanding_ar} "
                f"(both > 0) — old account must be preserved per SOP; billing continuity requires it."
            ),
        )
    return ChowDecision(
        action="reparent_direct",
        reason=(
            f"lifetime_revenue={lifetime_revenue}, outstanding_ar={outstanding_ar} — "
            f"no active billing dependency, safe to re-parent directly."
        ),
    )


def apply_chow_decision(account: dict, correct_parent_id: str, decision: ChowDecision) -> dict:
    """
    Translates a ChowDecision into the actual proposal payload(s).
    Returns a dict describing what to write — the caller (matcher/pipeline)
    is responsible for actually calling the CRM client.
    """
    if decision.action == "reparent_direct":
        return {
            "type": "update",
            "account_id": account["account_id"],
            "payload": {"parent_id": correct_parent_id},
            "note": decision.reason,
        }

    # preserve_and_chow: old account untouched except a note + linkage field;
    # a NEW account is created under the correct parent.
    return {
        "type": "chow_split",
        "old_account_update": {
            "account_id": account["account_id"],
            "payload": {"note": decision.reason},  # chow_current_account set after new id is known
        },
        "new_account_create": {
            "payload": {
                "name": account["name"],
                "billing_street": account.get("billing_street"),
                "billing_city": account.get("billing_city"),
                "billing_state": account.get("billing_state"),
                "billing_zip": account.get("billing_zip"),
                "care_type": account.get("care_type"),
                "parent_id": correct_parent_id,
            }
        },
        "note": decision.reason,
    }
