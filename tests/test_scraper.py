"""
Tests for address/detail parsing against markup shaped like the real
Bellhaven site. Uses actual BeautifulSoup tags (not pre-flattened
strings) so line-break structure is preserved, the way it is on the
live page.
"""
from bs4 import BeautifulSoup
from src.scraper import _parse_address_dd, _dl_to_dict


def _dd_with_lines(*lines):
    html = "<dd>" + "<br/>".join(lines) + "</dd>"
    return BeautifulSoup(html, "html.parser").find("dd")


def test_parses_real_observed_address():
    dd = _dd_with_lines("210 Orchard Lane", "Maplewood, OH 44280")
    street, city, state, zip_ = _parse_address_dd(dd)
    assert street == "210 Orchard Lane"
    assert city == "Maplewood"
    assert state == "OH"
    assert zip_ == "44280"


def test_parses_multiword_street_and_multiword_city():
    # This is the case a flattened-string regex cannot disambiguate —
    # both "Harbor Point Dr" and "Port Clinton" are multi-word text
    # with no delimiter between them once flattened.
    dd = _dd_with_lines("1420 Harbor Point Dr", "Port Clinton, OH 43452")
    street, city, state, zip_ = _parse_address_dd(dd)
    assert street == "1420 Harbor Point Dr"
    assert city == "Port Clinton"
    assert state == "OH"
    assert zip_ == "43452"


def test_handles_po_box_street():
    dd = _dd_with_lines("PO Box 517", "Ashtabula, OH 44004")
    street, city, state, zip_ = _parse_address_dd(dd)
    assert street == "PO Box 517"
    assert city == "Ashtabula"


def test_dl_to_dict_extracts_dt_dd_pairs():
    html = """
    <dl class="detail">
      <dt>Address</dt><dd>210 Orchard Lane<br/>Maplewood, OH 44280</dd>
      <dt>Care Offerings</dt><dd>Assisted Living</dd>
      <dt>Phone</dt><dd>(614) 250-9447</dd>
    </dl>
    """
    dl = BeautifulSoup(html, "html.parser").find("dl")
    fields = _dl_to_dict(dl)
    assert set(fields.keys()) == {"address", "care offerings", "phone"}
    assert fields["phone"].get_text(strip=True) == "(614) 250-9447"


def test_care_type_normalizes_site_vocabulary_to_crm_enum():
    from src.scraper import normalize_care_type
    assert normalize_care_type("Assisted Living") == "Assisted Living"
    assert normalize_care_type("Short-Term Rehabilitation & Nursing") == "Skilled Nursing"
    assert normalize_care_type("Memory Support") == "Memory Care"


def test_care_type_flags_unknown_labels_instead_of_guessing():
    from src.scraper import normalize_care_type
    result = normalize_care_type("Independent Living")
    assert result.startswith("UNMAPPED:")


def test_index_pagination_follows_all_pages(monkeypatch):
    """
    Regression test for a real bug found from live devtools: the
    community index paginates independently of the CRM API ("Page 1 of
    3 · 34 communities listed"). Without following it, only page 1's
    communities would be scraped.
    """
    import src.scraper as scraper_mod

    pages = {
        "https://example.test/communities": (
            "<p>Page 1 of 3 · 34 communities listed</p>"
            "<a href='/communities/a'>A</a><a href='/communities/b'>B</a>"
        ),
        "https://example.test/communities?page=2": (
            "<p>Page 2 of 3 · 34 communities listed</p>"
            "<a href='/communities/c'>C</a>"
        ),
        "https://example.test/communities?page=3": (
            "<p>Page 3 of 3 · 34 communities listed</p>"
            "<a href='/communities/d'>D</a>"
        ),
    }

    class FakeResp:
        def __init__(self, text):
            self.text = text
        def raise_for_status(self):
            pass

    def fake_get(url, timeout=15):
        return FakeResp(pages[url])

    monkeypatch.setattr(scraper_mod.requests, "get", fake_get)
    urls = scraper_mod._find_community_detail_urls("https://example.test/communities")
    assert urls == [
        "https://example.test/communities/a",
        "https://example.test/communities/b",
        "https://example.test/communities/c",
        "https://example.test/communities/d",
    ]


def test_homepage_only_link_is_included_even_when_absent_from_index(monkeypatch):
    """
    Regression test for a real gap found from live inspection: at least
    one real facility ("Bellhaven Meadows of Findlay") is linked only
    from the homepage's promo callout, not from the paginated community
    index at all. scrape_bellhaven_locations must pick it up from the
    homepage even though _find_community_detail_urls never sees it.
    """
    import src.scraper as scraper_mod

    pages = {
        "https://example.test": (
            "<a href='/communities'>Our Communities</a>"
            "<p>New this year: <a href='/communities/new-one'>Bellhaven Meadows of Findlay</a></p>"
        ),
        "https://example.test/communities": (
            "<p>Page 1 of 1 · 1 communities listed</p>"
            "<a href='/communities/a'>A</a>"
        ),
        "https://example.test/communities/a": (
            "<h1>A</h1><dl class='detail'>"
            "<dt>Address</dt><dd>1 Main St<br/>Townsville, OH 44444</dd>"
            "<dt>Care Offerings</dt><dd>Assisted Living</dd></dl>"
        ),
        "https://example.test/communities/new-one": (
            "<h1>Bellhaven Meadows of Findlay</h1><dl class='detail'>"
            "<dt>Address</dt><dd>2 Elm St<br/>Findlay, OH 45840</dd>"
            "<dt>Care Offerings</dt><dd>Assisted Living</dd></dl>"
        ),
    }

    class FakeResp:
        def __init__(self, text):
            self.text = text
        def raise_for_status(self):
            pass

    def fake_get(url, timeout=15):
        return FakeResp(pages[url])

    monkeypatch.setattr(scraper_mod.requests, "get", fake_get)
    locations = scraper_mod.scrape_bellhaven_locations("https://example.test")
    names = {loc.name for loc in locations}
    assert "Bellhaven Meadows of Findlay" in names
    assert "A" in names
