"""
Tests for the CHOW rule in isolation. Run: pytest tests/test_chow.py -v

These cover all four quadrants of (revenue history) x (outstanding AR),
since the brief's rule is an AND condition and the two easiest ways to
get it wrong are inverting the AND to an OR, or treating a None/0 value
as truthy.
"""
from src.chow import decide_chow_action


def test_revenue_and_ar_both_positive_preserves_old_account():
    d = decide_chow_action(lifetime_revenue=50000, outstanding_ar=1200)
    assert d.action == "preserve_and_chow"


def test_revenue_but_zero_ar_reparents_directly():
    d = decide_chow_action(lifetime_revenue=50000, outstanding_ar=0)
    assert d.action == "reparent_direct"


def test_no_revenue_but_ar_positive_reparents_directly():
    # AR > 0 with no revenue history shouldn't happen in real data, but
    # the rule is explicitly an AND — confirm we don't treat it as OR.
    d = decide_chow_action(lifetime_revenue=0, outstanding_ar=500)
    assert d.action == "reparent_direct"


def test_no_revenue_no_ar_reparents_directly():
    d = decide_chow_action(lifetime_revenue=0, outstanding_ar=0)
    assert d.action == "reparent_direct"


def test_none_values_treated_as_falsy_not_error():
    d = decide_chow_action(lifetime_revenue=None, outstanding_ar=None)
    assert d.action == "reparent_direct"


def test_negative_ar_treated_as_no_outstanding():
    d = decide_chow_action(lifetime_revenue=1000, outstanding_ar=-50)
    assert d.action == "reparent_direct"
