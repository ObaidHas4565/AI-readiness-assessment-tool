"""
Plausibility checks for the open text fields

Sector and country are open fields: the tool has to work for a bakery in
Nairobi and an asset manager in Toronto without either of them appearing on
a list drawn up in advance. But open cannot mean anything at all -- "bahab"
is not a country, and storing it would quietly poison every breakdown that
groups by country afterwards.

So neither field has a permitted list. What they have is a plausibility
check, and the two fields need different kinds:

  Countries are genuinely enumerable. There are about two hundred of them
  and the set does not change month to month, so a reference list is not a
  restriction -- it is the actual answer to "is this a country". Spelling
  variants, abbreviations and short forms are all accepted and resolved to
  one canonical name, which also stops "UAE" and "United Arab Emirates"
  splitting into two groups in the results.

  Industries are not enumerable. Nobody can write the list, and trying
  produces exactly the problem this replaces. Instead an answer is checked
  against a vocabulary of industry words: if any part of it reads as an
  industry -- "logistics", "asset management", "marine engineering" -- it
  is accepted as typed, in the respondent's own words. Only answers that
  contain no recognisable industry term at all are sent back.

Both checks are deliberately generous. A false rejection is worse than a
loose acceptance here: it blocks a real respondent from finishing, whereas
a slightly odd sector label costs nothing but a slightly odd row.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# Countries
# ---------------------------------------------------------------------------

COUNTRIES: Tuple[str, ...] = (
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Argentina",
    "Armenia", "Australia", "Austria", "Azerbaijan", "Bahamas", "Bahrain",
    "Bangladesh", "Barbados", "Belarus", "Belgium", "Belize", "Benin",
    "Bhutan", "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil",
    "Brunei", "Bulgaria", "Burkina Faso", "Burundi", "Cambodia", "Cameroon",
    "Canada", "Cape Verde", "Central African Republic", "Chad", "Chile",
    "China", "Colombia", "Comoros", "Costa Rica", "Croatia", "Cuba",
    "Cyprus", "Czech Republic", "Democratic Republic of the Congo",
    "Denmark", "Djibouti", "Dominica", "Dominican Republic", "Ecuador",
    "Egypt", "El Salvador", "Equatorial Guinea", "Eritrea", "Estonia",
    "Eswatini", "Ethiopia", "Fiji", "Finland", "France", "Gabon", "Gambia",
    "Georgia", "Germany", "Ghana", "Greece", "Grenada", "Guatemala",
    "Guinea", "Guinea-Bissau", "Guyana", "Haiti", "Honduras", "Hong Kong",
    "Hungary", "Iceland", "India", "Indonesia", "Iran", "Iraq", "Ireland",
    "Israel", "Italy", "Ivory Coast", "Jamaica", "Japan", "Jordan",
    "Kazakhstan", "Kenya", "Kiribati", "Kosovo", "Kuwait", "Kyrgyzstan",
    "Laos", "Latvia", "Lebanon", "Lesotho", "Liberia", "Libya",
    "Liechtenstein", "Lithuania", "Luxembourg", "Macau", "Madagascar",
    "Malawi", "Malaysia", "Maldives", "Mali", "Malta", "Mauritania",
    "Mauritius", "Mexico", "Moldova", "Monaco", "Mongolia", "Montenegro",
    "Morocco", "Mozambique", "Myanmar", "Namibia", "Nepal", "Netherlands",
    "New Zealand", "Nicaragua", "Niger", "Nigeria", "North Korea",
    "North Macedonia", "Norway", "Oman", "Pakistan", "Palestine", "Panama",
    "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Poland",
    "Portugal", "Puerto Rico", "Qatar", "Republic of the Congo", "Romania",
    "Russia", "Rwanda", "Samoa", "San Marino", "Saudi Arabia", "Senegal",
    "Serbia", "Seychelles", "Sierra Leone", "Singapore", "Slovakia",
    "Slovenia", "Solomon Islands", "Somalia", "South Africa", "South Korea",
    "South Sudan", "Spain", "Sri Lanka", "Sudan", "Suriname", "Sweden",
    "Switzerland", "Syria", "Taiwan", "Tajikistan", "Tanzania", "Thailand",
    "Timor-Leste", "Togo", "Tonga", "Trinidad and Tobago", "Tunisia",
    "Turkey", "Turkmenistan", "Uganda", "Ukraine", "United Arab Emirates",
    "United Kingdom", "United States", "Uruguay", "Uzbekistan", "Vanuatu",
    "Vatican City", "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe",
)

# Short forms, abbreviations and the spellings people actually type. Resolving
# these matters twice over: it accepts the answer, and it stops "UAE" and
# "United Arab Emirates" being counted as two different countries.
COUNTRY_ALIASES: Dict[str, str] = {
    "uae": "United Arab Emirates", "u a e": "United Arab Emirates",
    "emirates": "United Arab Emirates", "dubai": "United Arab Emirates",
    "abu dhabi": "United Arab Emirates", "sharjah": "United Arab Emirates",
    "uk": "United Kingdom", "u k": "United Kingdom",
    "great britain": "United Kingdom", "britain": "United Kingdom",
    "england": "United Kingdom", "scotland": "United Kingdom",
    "wales": "United Kingdom", "northern ireland": "United Kingdom",
    "usa": "United States", "u s a": "United States", "us": "United States",
    "u s": "United States", "america": "United States",
    "united states of america": "United States",
    "ksa": "Saudi Arabia", "saudi": "Saudi Arabia",
    "korea": "South Korea", "republic of korea": "South Korea",
    "drc": "Democratic Republic of the Congo",
    "congo": "Republic of the Congo",
    "czechia": "Czech Republic", "holland": "Netherlands",
    "swaziland": "Eswatini", "burma": "Myanmar",
    "cote d ivoire": "Ivory Coast", "cote divoire": "Ivory Coast",
    "uae dubai": "United Arab Emirates",
    "russian federation": "Russia", "prc": "China",
    "mainland china": "China", "hk": "Hong Kong",
    "ph": "Philippines", "nz": "New Zealand", "sa": "South Africa",
}


# ---------------------------------------------------------------------------
# Industry vocabulary
# ---------------------------------------------------------------------------
# Not a list of allowed sectors. A list of words that mean "this is an
# industry", used to tell a real answer from a mistyped one. Stems rather than
# whole words, so "manufacturing", "manufacturer" and "manufacture" all pass
# on one entry.

INDUSTRY_TERMS: Tuple[str, ...] = (
    "account", "advertis", "aerospace", "agri", "agricultur", "airline",
    "apparel", "architect", "art", "asset", "audit", "automot", "automobile",
    "aviation", "bank", "beauty", "beverage", "biotech", "broadcast",
    "brokerage", "build", "casino", "catering", "chemical", "childcare",
    "cinema", "clean", "clinic", "cloud", "commerce", "commodit",
    "communicat", "construct", "consult", "consumer", "content", "cosmetic",
    "courier", "craft", "creative", "crypto", "cyber", "dairy", "dental",
    "design", "develop", "digital", "distribut", "ecommerce", "econom",
    "educat", "electric", "electronic", "energy", "engineer", "entertain",
    "environment", "equipment", "event", "export", "fabric", "facilit",
    "farm", "fashion", "financ", "fintech", "fish", "fitness", "food",
    "forestry", "freight", "furniture", "gaming", "garment", "gas",
    "government", "grocer", "hardware", "health", "hospital", "hospitality",
    "hotel", "housing", "human resource", "import", "industr", "informat",
    "infrastructure", "insur", "interior", "internet", "invest", "jewel",
    "journalis", "laborator", "landscap", "laundr", "law", "legal",
    "leisure", "lending", "logistic", "machin", "maintenance", "manage",
    "manufactur", "marine", "maritime", "market", "media", "medical",
    "metal", "mining", "mobile", "motor", "music", "network", "news",
    "nonprofit", "non profit", "ngo", "nursing", "nutrition", "oil",
    "packag", "paint", "paper", "petroleum", "pharma", "photograph",
    "plastic", "plumb", "print", "product", "profession", "propert",
    "public", "publish", "railway", "real estate", "realestate", "recruit",
    "recycl", "renewable", "rental", "repair", "research", "restaurant",
    "retail", "robot", "safety", "sales", "sanitation", "school", "科技",
    "secur", "semiconductor", "service", "shipping", "social", "software",
    "solar", "space", "sport", "staffing", "steel", "storage", "supply",
    "sustainab", "tax", "teach", "tech", "telecom", "textile", "theatre",
    "tourism", "trade", "trading", "train", "transport", "travel", "truck",
    "utilit", "vehicle", "veterinar", "warehous", "waste", "water",
    "wellness", "wholesale", "wood",
)

# Words that carry no industry meaning on their own, so an answer made only of
# these is not specific enough to keep.
FILLER_WORDS: frozenset = frozenset({
    "and", "or", "the", "a", "an", "of", "in", "for", "to", "with", "on",
    "company", "business", "sector", "industry", "firm", "organisation",
    "organization", "group", "ltd", "llc", "inc", "plc", "limited", "co",
    "corp", "corporation", "enterprise", "enterprises", "solutions", "our",
    "we", "my", "other", "others", "general", "various", "misc",
    "miscellaneous", "etc", "na", "n", "none", "nil", "no", "yes", "test",
})


# ---------------------------------------------------------------------------

def _flatten(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", str(text).lower()).split())


def _similar(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def resolve_country(value: object) -> Optional[str]:
    """
    Return the canonical country name, or None if it isn't one.

    Accepts exact names, abbreviations, major cities that stand in for their
    country in casual answers, and misspellings close enough to be obvious.
    """
    flat = _flatten(value)
    if not flat:
        return None

    if flat in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[flat]

    for country in COUNTRIES:
        if flat == _flatten(country):
            return country

    # Misspellings. The bar is high enough that "bahab" matches nothing but
    # low enough to forgive a dropped letter in "Phillipines".
    best_name, best_score = None, 0.0
    for country in COUNTRIES:
        score = _similar(flat, _flatten(country))
        if score > best_score:
            best_name, best_score = country, score
    if best_score >= 0.86:
        return best_name

    for alias, country in COUNTRY_ALIASES.items():
        if _similar(flat, alias) >= 0.90:
            return country

    return None


def looks_like_industry(value: object) -> bool:
    """
    True when the answer contains something recognisable as an industry.

    Deliberately loose: any industry word anywhere in the answer is enough,
    so "marine engineering consultancy" and "halal food logistics" both pass
    without either ever appearing on a list. What fails is an answer with no
    industry word in it at all, which is what a mistyped one looks like.
    """
    flat = _flatten(value)
    if not flat:
        return False

    words = [word for word in flat.split() if word not in FILLER_WORDS]
    if not words:
        return False

    for term in INDUSTRY_TERMS:
        if term in flat:
            return True

    # Nothing matched outright. Allow a close miss on a single word, which
    # covers a typo in an otherwise ordinary sector name.
    for word in words:
        if len(word) < 4:
            continue
        for term in INDUSTRY_TERMS:
            if len(term) >= 4 and _similar(word, term) >= 0.85:
                return True

    return False


def check_open_value(field_name: str, value: object) -> Tuple[Optional[str], Optional[str]]:
    """
    Check one open field.

    Returns (cleaned_value, error). Exactly one of the two is set: either the
    answer is usable and comes back tidied, or it isn't and comes back with a
    message written for the person who typed it.
    """
    text = str(value or "").strip()
    if not text:
        return None, None  # "required" is reported separately

    if field_name == "region":
        resolved = resolve_country(text)
        if resolved:
            return resolved, None
        return None, (
            f"{text!r} doesn't look like a country. Please enter the country "
            f"the company mainly operates in."
        )

    if field_name == "industry_sector":
        if looks_like_industry(text):
            # Kept as typed -- the respondent describes their own industry
            # better than any category would.
            if len(text) > 3 and (text.isupper() or text.islower()):
                return text.title(), None
            return text, None
        return None, (
            f"{text!r} doesn't look like an industry. Please describe what the "
            f"company actually does — for example 'logistics', 'dental clinic' "
            f"or 'food manufacturing'."
        )

    return text, None
