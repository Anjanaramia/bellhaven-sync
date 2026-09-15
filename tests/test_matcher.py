"""
Regression test for the bug caught from the live CRM screenshot: the
parent account name includes '(Parent Account)' as part of the actual
name field, not a UI decoration. An exact-match lookup would silently
return None and break every downstream check.
"""
from src.matcher import find_bellhaven_parent


def test_finds_parent_with_real_observed_name_format():
    accounts = [
        {"id": "p1", "name": "Bellhaven Senior Living (Parent Account)", "parent_id": None},
        {"id": "a2", "name": "Bellhaven Court of Altoona", "parent_id": "p1"},
        {"id": "a3", "name": "Stonebridge Eldercare (Parent Account)", "parent_id": None},
    ]
    parent = find_bellhaven_parent(accounts)
    assert parent is not None
    assert parent["id"] == "p1"


def test_does_not_match_facility_that_merely_has_bellhaven_in_name():
    # A facility named "Bellhaven ..." with a parent_id set is NOT the
    # top-level parent — must not be confused with it.
    accounts = [
        {"id": "a2", "name": "Bellhaven Court of Altoona", "parent_id": "p1"},
    ]
    assert find_bellhaven_parent(accounts) is None


def test_returns_none_when_absent():
    accounts = [{"id": "a1", "name": "Amberly Care Center", "parent_id": "x"}]
    assert find_bellhaven_parent(accounts) is None


def test_scraped_duplicate_pair_does_not_orphan_the_second_account():
    """
    Regression test for a real bug found against live data: when two CRM
    accounts share a name (a real duplicate pair, e.g. two "Bellhaven of
    Owosso" accounts), matching must not let the first claim both scraped
    mentions and leave the second falsely flagged vanished_from_website.
    """
    from src.matcher import match_and_classify
    from dataclasses import dataclass

    @dataclass
    class Loc:
        name: str
        address: str = ""
        city: str = ""
        state: str = ""
        zip: str = ""
        care_type: str = ""

    parent = {"account_id": "p1", "name": "Bellhaven Senior Living (Parent Account)", "parent_id": ""}
    acc1 = {"account_id": "a1", "name": "Bellhaven of Owosso", "parent_id": "p1", "billing_city": "Owosso",
            "lifetime_revenue": 0, "outstanding_ar": 0}
    acc2 = {"account_id": "a2", "name": "Bellhaven of Owosso", "parent_id": "p1", "billing_city": "Owosso",
            "lifetime_revenue": 0, "outstanding_ar": 0}
    accounts = [parent, acc1, acc2]
    scraped = [Loc(name="Bellhaven of Owosso", city="Owosso"), Loc(name="Bellhaven of Owosso", city="Owosso")]

    proposals = match_and_classify(scraped, accounts)
    classifications = {p.classification for p in proposals}
    assert "vanished_from_website" not in classifications


def test_same_name_different_company_and_city_is_not_matched():
    """
    Regression test for the most serious bug found: two facilities with
    the identical name ("Amberly Manor") in different cities, belonging
    to entirely different parent companies, score 1.0 on name similarity
    alone. Without a city check, the matcher would confidently link them
    and risk writing changes onto an account that belongs to a different
    company. The site's copy must be treated as no_account_yet, not
    matched to the unrelated CRM account.
    """
    from src.matcher import match_and_classify
    from dataclasses import dataclass

    @dataclass
    class Loc:
        name: str
        address: str = ""
        city: str = ""
        state: str = ""
        zip: str = ""
        care_type: str = ""

    parent = {"account_id": "p1", "name": "Bellhaven Senior Living (Parent Account)", "parent_id": ""}
    unrelated_account = {
        "account_id": "juniper-1", "name": "Amberly Manor", "parent_id": "juniper-parent",
        "billing_city": "Colorado Springs", "lifetime_revenue": 0, "outstanding_ar": 0,
    }
    accounts = [parent, unrelated_account]
    scraped = [Loc(name="Amberly Manor", city="Hudson", state="OH")]

    proposals = match_and_classify(scraped, accounts)
    assert len(proposals) == 1
    assert proposals[0].classification == "no_account_yet"
    assert proposals[0].account_id is None
    # Must never touch the unrelated Juniper Point account.
    touched_ids = {p.account_id for p in proposals if p.account_id}
    assert "juniper-1" not in touched_ids


def test_confident_match_still_flags_stale_name_when_parent_is_correct():
    """
    Regression test: an account already correctly parented under Bellhaven
    can still have a stale name (site "Bellhaven at Sycamore Ridge" vs CRM
    "Bellhaven of Sycamore Ridge", real score 0.926). A parent-only check
    would silently skip this since parent_id already matches.
    """
    from src.matcher import match_and_classify
    from dataclasses import dataclass

    @dataclass
    class Loc:
        name: str
        address: str = ""
        city: str = ""
        state: str = ""
        zip: str = ""
        care_type: str = ""

    parent = {"account_id": "p1", "name": "Bellhaven Senior Living (Parent Account)", "parent_id": ""}
    acc = {"account_id": "a1", "name": "Bellhaven of Sycamore Ridge", "parent_id": "p1",
           "billing_city": "Miamisburg", "lifetime_revenue": 0, "outstanding_ar": 0}
    accounts = [parent, acc]
    scraped = [Loc(name="Bellhaven at Sycamore Ridge", city="Miamisburg")]

    proposals = match_and_classify(scraped, accounts)
    assert len(proposals) == 1
    assert proposals[0].classification == "needs_fix"
    assert proposals[0].fields.get("name") == "Bellhaven at Sycamore Ridge"


def test_common_prefix_does_not_falsely_match_unrelated_new_facility():
    """
    Regression test for a real bug found against the live 121-account
    dataset: 'Bellhaven of Carlisle' (a genuinely new facility, city
    Carlisle) scored 0.91 on name alone against the unrelated existing
    'Bellhaven of New Carlisle' (city New Carlisle) — above the
    confident-match threshold — because every facility shares the
    'Bellhaven of ' prefix. Without the city gate, this would either
    silently drop the new facility or propose renaming the wrong account.
    """
    from src.matcher import match_and_classify
    from dataclasses import dataclass

    @dataclass
    class Loc:
        name: str
        city: str
        address: str = ""
        state: str = ""
        zip: str = ""
        care_type: str = ""

    parent = {"account_id": "p1", "name": "Bellhaven Senior Living (Parent Account)", "parent_id": ""}
    existing = {"account_id": "a1", "name": "Bellhaven of New Carlisle", "parent_id": "p1",
                "billing_city": "New Carlisle", "lifetime_revenue": 0, "outstanding_ar": 0}
    accounts = [parent, existing]
    scraped = [
        Loc(name="Bellhaven of New Carlisle", city="New Carlisle"),
        Loc(name="Bellhaven of Carlisle", city="Carlisle"),
    ]

    proposals = match_and_classify(scraped, accounts)
    new_one = [p for p in proposals if p.classification == "no_account_yet"]
    assert len(new_one) == 1, "the new Carlisle facility must surface as no_account_yet, not be dropped or misfiled"
    assert new_one[0].fields.get("name") == "Bellhaven of Carlisle"
