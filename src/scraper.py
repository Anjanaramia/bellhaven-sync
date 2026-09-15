"""
Scrapes Bellhaven's public site for its list of locations.

CONFIRMED structure (from live devtools inspection, 2026-09-14):
  - Nav has "Our Communities" — an index page listing links to each
    facility's own detail page.
  - Each detail page: <h1> is the facility name; <dl class="detail">
    holds label/value pairs (dt/dd) for Address, Care Offerings,
    Administrator, Phone. Address is two lines: street, then
    "City, ST ZIP".
  - care_type on the CRM side is a single string (e.g. "Assisted
    Living"), matching what the site shows as one badge — not a list.

If the real markup uses different tag/class names than assumed below,
the fix is localized to this file's SELECTORS dict and the two parsing
functions — nothing downstream needs to change.
"""
import re
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from urllib.parse import urljoin
from . import config

SELECTORS = {
    "communities_nav_link_text": "Our Communities",
    "detail_list": "dl.detail",
}

# Matches /communities/some-slug or /community/123 — but NOT the bare
# index URL (/communities) itself. Using a regex instead of a CSS
# attribute selector because the naive `a[href*='/communit']` also
# matched the "Our Communities" nav link to the index page, which is
# not a facility detail page and has no <h1>/<dl> to parse.
DETAIL_LINK_RE = re.compile(r"/communit(?:y|ies)/[^/?#]+")
PAGE_COUNT_RE = re.compile(r"Page\s+\d+\s+of\s+(\d+)", re.IGNORECASE)

# CONFIRMED mismatch: the site's care-offering labels don't match the CRM's
# care_type enum values (site "Short-Term Rehabilitation & Nursing" vs CRM
# "Skilled Nursing", site "Memory Support" vs CRM "Memory Care"). This map
# is inferred from ONE page of visible cards — verify it covers every label
# the full 34-community set actually uses before relying on it for creates.
CARE_TYPE_MAP = {
    "assisted living": "Assisted Living",
    "short-term rehabilitation & nursing": "Skilled Nursing",
    "memory support": "Memory Care",
}


def normalize_care_type(site_label: str) -> str:
    key = site_label.strip().lower()
    if key in CARE_TYPE_MAP:
        return CARE_TYPE_MAP[key]
    # Unknown label — don't silently guess; surface it so a human decides
    # rather than writing a value the CRM may reject or misclassify.
    return f"UNMAPPED:{site_label.strip()}"

# Unambiguous, since a comma only ever separates city from "ST ZIP" —
# unlike the street/city boundary, which has no reliable delimiter.
CITY_STATE_ZIP_RE = re.compile(r"^(?P<city>.+),\s*(?P<state>[A-Z]{2})\s+(?P<zip>\d{5})$")


@dataclass
class ScrapedLocation:
    name: str
    address: str
    city: str
    state: str
    zip: str
    care_type: str
    source_url: str = ""


def _dl_to_dict(dl_tag) -> dict:
    """Parses a <dl> of dt/dd pairs into {label_lower: dd_tag} (keeps the
    tag, not flattened text, so callers can inspect line breaks)."""
    result = {}
    for dt in dl_tag.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            result[dt.get_text(strip=True).lower()] = dd
    return result


def _parse_address_dd(dd_tag) -> tuple[str, str, str, str]:
    """
    Address is shown as two visual lines (street, then 'City, ST ZIP').
    Splitting a flattened single string is ambiguous for multi-word
    street/city combos (e.g. 'Harbor Point Dr' vs 'Port Clinton') — so
    this reads the two lines separately via stripped_strings, which
    splits on <br> or block-level breaks in the markup, instead of
    guessing a boundary with regex.
    """
    lines = list(dd_tag.stripped_strings) if dd_tag else []
    if len(lines) < 2:
        return (lines[0] if lines else "", "", "", "")

    street = lines[0]
    city_state_zip = lines[-1]
    m = CITY_STATE_ZIP_RE.match(city_state_zip)
    if m:
        return (street, m.group("city").strip(), m.group("state"), m.group("zip"))
    return (street, "", "", "")


def _find_communities_index_url(base_url: str) -> str:
    resp = requests.get(base_url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for a in soup.find_all("a"):
        if SELECTORS["communities_nav_link_text"].lower() in a.get_text(strip=True).lower():
            return urljoin(base_url, a["href"])
    raise ValueError(
        f"Could not find an 'Our Communities' nav link on {base_url} — "
        f"update SELECTORS['communities_nav_link_text'] or hardcode the index URL."
    )


def _find_community_detail_urls(index_url: str) -> list[str]:
    """
    Follows the index page's OWN pagination ("Page 1 of 3 · 34 communities
    listed") — confirmed from live devtools to be separate from the CRM
    API's pagination. Without this, only the first page's ~12 of 34
    communities would be scraped, silently undercounting the very
    no_account_yet cases the exercise depends on.
    """
    all_urls = []
    seen = set()
    page = 1
    total_pages = None

    while total_pages is None or page <= total_pages:
        url = index_url if page == 1 else f"{index_url}?page={page}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        if total_pages is None:
            page_text = soup.get_text(" ", strip=True)
            m = PAGE_COUNT_RE.search(page_text)
            total_pages = int(m.group(1)) if m else 1

        for a in soup.find_all("a", href=True):
            if not DETAIL_LINK_RE.search(a["href"]):
                continue
            u = urljoin(url, a["href"])
            if u not in seen:
                seen.add(u)
                all_urls.append(u)

        page += 1

    return all_urls


def _scrape_detail_page(url: str) -> ScrapedLocation:
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    name = soup.find("h1").get_text(strip=True)
    dl = soup.select_one(SELECTORS["detail_list"])
    fields = _dl_to_dict(dl) if dl else {}

    street, city, state, zip_ = _parse_address_dd(fields.get("address"))

    return ScrapedLocation(
        name=name, address=street, city=city, state=state, zip=zip_,
        care_type=normalize_care_type(fields["care offerings"].get_text(" ", strip=True)) if fields.get("care offerings") else "",
        source_url=url,
    )


def scrape_bellhaven_locations(site_url: str | None = None) -> list[ScrapedLocation]:
    base_url = site_url or config.BELLHAVEN_SITE_URL
    if not base_url:
        raise ValueError("BELLHAVEN_SITE_URL is not set — see config.py / .env.example")

    index_url = _find_communities_index_url(base_url)
    detail_urls = _find_community_detail_urls(index_url)

    # CONFIRMED from live inspection: at least one facility ("Bellhaven
    # Meadows of Findlay" — the homepage's "New this year" callout) is
    # linked ONLY from the homepage, not from the paginated "Our
    # Communities" index. Relying on the index alone would silently miss
    # it. Also crawl the homepage itself for any matching community links
    # and union them in, de-duplicated by URL.
    resp = requests.get(base_url, timeout=15)
    resp.raise_for_status()
    home_soup = BeautifulSoup(resp.text, "html.parser")
    for a in home_soup.find_all("a", href=True):
        if not DETAIL_LINK_RE.search(a["href"]):
            continue
        u = urljoin(base_url, a["href"])
        if u not in detail_urls:
            detail_urls.append(u)

    return [_scrape_detail_page(u) for u in detail_urls]
