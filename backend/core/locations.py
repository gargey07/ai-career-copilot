"""
Shared location taxonomy
─────────────────────────
Single source of truth for two consumers that used to carry separate,
drifting copies of the same country/city data:
  - jobs/fetchers.py: resolve_fetch_location() steers Adzuna's country
    endpoint + JSearch's query text.
  - api/routes/suggestions.py: suggest_locations() backs the onboarding
    "Preferred locations" autosuggest field.
"""
from __future__ import annotations
import re
from typing import Optional

# Adzuna is per-country-ENDPOINT — only these country codes exist there.
ADZUNA_COUNTRIES = {
    "at", "au", "be", "br", "ca", "ch", "de", "es", "fr", "gb", "in", "it",
    "mx", "nl", "nz", "pl", "sg", "us", "za",
}

# code -> canonical display name, used for suggestions and "Remote — X"
# labels. Explicit rather than derived from _COUNTRY_CODES' synonyms below
# (several synonyms share a code — e.g. "uk"/"scotland"/"england" all -> gb
# — so deriving a display name from that map picks whichever happened to
# be inserted last, not necessarily the name anyone would want to see).
COUNTRY_NAMES: dict[str, str] = {
    "in": "India", "gb": "United Kingdom", "us": "United States", "ca": "Canada",
    "au": "Australia", "de": "Germany", "fr": "France", "nl": "Netherlands",
    "sg": "Singapore", "nz": "New Zealand", "at": "Austria", "be": "Belgium",
    "br": "Brazil", "ch": "Switzerland", "es": "Spain", "it": "Italy",
    "mx": "Mexico", "pl": "Poland", "za": "South Africa", "ae": "UAE",
    "ie": "Ireland", "jp": "Japan", "qa": "Qatar", "sa": "Saudi Arabia",
}

# Free-text synonym -> country code (many-to-one; used for RESOLUTION).
_COUNTRY_CODES: dict[str, str] = {
    "india": "in",
    "united kingdom": "gb", "uk": "gb", "england": "gb", "great britain": "gb", "scotland": "gb",
    "united states": "us", "usa": "us", "us": "us", "america": "us", "united states of america": "us",
    "canada": "ca", "australia": "au", "germany": "de", "france": "fr",
    "netherlands": "nl", "singapore": "sg", "new zealand": "nz",
    "austria": "at", "belgium": "be", "brazil": "br", "switzerland": "ch",
    "spain": "es", "italy": "it", "mexico": "mx", "poland": "pl", "south africa": "za",
    # Not on Adzuna, but still resolvable so JSearch can serve them:
    "uae": "ae", "united arab emirates": "ae", "ireland": "ie", "japan": "jp",
    "qatar": "qa", "saudi arabia": "sa",
}

CITY_COUNTRY: dict[str, str] = {
    # India
    "mumbai": "in", "delhi": "in", "new delhi": "in", "bangalore": "in", "bengaluru": "in",
    "hyderabad": "in", "chennai": "in", "pune": "in", "kolkata": "in", "ahmedabad": "in",
    "gurgaon": "in", "gurugram": "in", "noida": "in", "jaipur": "in", "surat": "in",
    # Gulf
    "dubai": "ae", "abu dhabi": "ae", "sharjah": "ae", "doha": "qa", "riyadh": "sa", "jeddah": "sa",
    # UK / Europe
    "london": "gb", "manchester": "gb", "birmingham": "gb", "edinburgh": "gb",
    "berlin": "de", "munich": "de", "frankfurt": "de", "paris": "fr", "amsterdam": "nl",
    "dublin": "ie", "zurich": "ch", "madrid": "es", "barcelona": "es", "milan": "it", "warsaw": "pl",
    # North America
    "new york": "us", "san francisco": "us", "seattle": "us", "austin": "us", "boston": "us",
    "chicago": "us", "los angeles": "us", "toronto": "ca", "vancouver": "ca",
    # APAC / other
    "singapore": "sg", "sydney": "au", "melbourne": "au", "auckland": "nz", "tokyo": "jp",
    "sao paulo": "br", "mexico city": "mx", "johannesburg": "za", "cape town": "za",
}

REMOTE_WORDS = {"remote", "anywhere", "work from home", "wfh"}

_REMOTE_PREFIX_RE = re.compile(r"^remote\s*[—\-]\s*(.+)$")


def resolve_fetch_location(raw: str) -> Optional[dict]:
    """
    Free-text preferred_location -> {"raw", "country_code", "city"} fetch
    target, or None for remote/empty entries (remote sources always run
    regardless of location). Unknown places still resolve — with
    country_code=None — so JSearch can use the raw text even when Adzuna
    (country-endpoint-based) has to sit that fetch out.

    Handles the "Remote — Worldwide" / "Remote — {Country}" suggestion
    labels (see suggest_locations below) the same as their plain
    equivalents: "Remote — Worldwide" -> no constraint (None), "Remote —
    India" -> constrained to India, same as typing "India" alone.
    """
    text = (raw or "").strip()
    key = re.sub(r"\s+", " ", text.lower()).strip(" .")
    if not key or key in REMOTE_WORDS:
        return None

    remote_match = _REMOTE_PREFIX_RE.match(key)
    if remote_match:
        rest = remote_match.group(1).strip()
        if rest in ("worldwide", "anywhere", ""):
            return None
        key = rest  # "remote — india" -> resolve "india" below

    if key in _COUNTRY_CODES:
        return {"raw": text, "country_code": _COUNTRY_CODES[key], "city": None}
    if key in CITY_COUNTRY:
        return {"raw": text, "country_code": CITY_COUNTRY[key], "city": text}
    if "," in key:  # "City, Country"
        city_part, _, country_part = key.partition(",")
        city_part, country_part = city_part.strip(), country_part.strip()
        code = _COUNTRY_CODES.get(country_part) or CITY_COUNTRY.get(city_part)
        return {"raw": text, "country_code": code, "city": city_part.title()}
    return {"raw": text, "country_code": None, "city": text}


# ── Autosuggest ─────────────────────────────────────────────────────────────
def _build_suggestion_list() -> list[str]:
    """Built once at import: Remote — Worldwide, Remote — {country} for
    every known country, every country name, then every curated city —
    each group alphabetical so results read predictably."""
    countries_sorted = sorted(COUNTRY_NAMES.values())
    items = ["Remote — Worldwide"]
    items += [f"Remote — {name}" for name in countries_sorted]
    items += countries_sorted
    items += sorted({c.title() for c in CITY_COUNTRY})
    return items


LOCATION_SUGGESTIONS: list[str] = _build_suggestion_list()


def suggest_locations(query: str, limit: int = 20) -> list[str]:
    """Type-ahead for the onboarding 'Preferred locations' field — prefix
    matches rank above substring matches, same convention as
    core/skill_maps.suggest()."""
    q = query.strip().lower()
    if not q:
        return LOCATION_SUGGESTIONS[:limit]
    prefix_matches = [item for item in LOCATION_SUGGESTIONS if item.lower().startswith(q)]
    substring_matches = [item for item in LOCATION_SUGGESTIONS if q in item.lower() and item not in prefix_matches]
    return (prefix_matches + substring_matches)[:limit]
