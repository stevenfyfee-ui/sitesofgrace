"""ISO 3166-1 alpha-2 country codes, and the mapping from the free-text
`SacredSitePage.country` strings to them.

Used by `manage.py propose_country_codes` (which only proposes; nothing is
written until a reviewer approves a row) and by destination hubs, which
match sites on the approved `country_code`. The original `country` text is
never changed.

Decisions (docs/v2/phase0-findings.md): "USA" -> US; "United Kingdom" -> GB,
displayed as "United Kingdom".
"""
import re

# code -> display name. Short, everyday English names.
COUNTRY_NAMES = dict(
    entry.split(":", 1) for entry in (
        "AD:Andorra|AE:United Arab Emirates|AF:Afghanistan|AG:Antigua and Barbuda|AL:Albania|AM:Armenia|"
        "AO:Angola|AR:Argentina|AT:Austria|AU:Australia|AZ:Azerbaijan|BA:Bosnia and Herzegovina|"
        "BB:Barbados|BD:Bangladesh|BE:Belgium|BF:Burkina Faso|BG:Bulgaria|BH:Bahrain|BI:Burundi|BJ:Benin|"
        "BN:Brunei|BO:Bolivia|BR:Brazil|BS:Bahamas|BT:Bhutan|BW:Botswana|BY:Belarus|BZ:Belize|CA:Canada|"
        "CD:Democratic Republic of the Congo|CF:Central African Republic|CG:Republic of the Congo|"
        "CH:Switzerland|CI:Côte d'Ivoire|CL:Chile|CM:Cameroon|CN:China|CO:Colombia|CR:Costa Rica|CU:Cuba|"
        "CV:Cabo Verde|CY:Cyprus|CZ:Czech Republic|DE:Germany|DJ:Djibouti|DK:Denmark|DM:Dominica|"
        "DO:Dominican Republic|DZ:Algeria|EC:Ecuador|EE:Estonia|EG:Egypt|ER:Eritrea|ES:Spain|ET:Ethiopia|"
        "FI:Finland|FJ:Fiji|FM:Micronesia|FR:France|GA:Gabon|GB:United Kingdom|GD:Grenada|GE:Georgia|"
        "GH:Ghana|GM:Gambia|GN:Guinea|GQ:Equatorial Guinea|GR:Greece|GT:Guatemala|GW:Guinea-Bissau|"
        "GY:Guyana|HN:Honduras|HR:Croatia|HT:Haiti|HU:Hungary|ID:Indonesia|IE:Ireland|IL:Israel|IN:India|"
        "IQ:Iraq|IR:Iran|IS:Iceland|IT:Italy|JM:Jamaica|JO:Jordan|JP:Japan|KE:Kenya|KG:Kyrgyzstan|"
        "KH:Cambodia|KI:Kiribati|KM:Comoros|KN:Saint Kitts and Nevis|KP:North Korea|KR:South Korea|"
        "KW:Kuwait|KZ:Kazakhstan|LA:Laos|LB:Lebanon|LC:Saint Lucia|LI:Liechtenstein|LK:Sri Lanka|"
        "LR:Liberia|LS:Lesotho|LT:Lithuania|LU:Luxembourg|LV:Latvia|LY:Libya|MA:Morocco|MC:Monaco|"
        "MD:Moldova|ME:Montenegro|MG:Madagascar|MH:Marshall Islands|MK:North Macedonia|ML:Mali|"
        "MM:Myanmar|MN:Mongolia|MR:Mauritania|MT:Malta|MU:Mauritius|MV:Maldives|MW:Malawi|MX:Mexico|"
        "MY:Malaysia|MZ:Mozambique|NA:Namibia|NE:Niger|NG:Nigeria|NI:Nicaragua|NL:Netherlands|NO:Norway|"
        "NP:Nepal|NR:Nauru|NZ:New Zealand|OM:Oman|PA:Panama|PE:Peru|PG:Papua New Guinea|PH:Philippines|"
        "PK:Pakistan|PL:Poland|PR:Puerto Rico|PS:Palestine|PT:Portugal|PW:Palau|PY:Paraguay|QA:Qatar|"
        "RO:Romania|RS:Serbia|RU:Russia|RW:Rwanda|SA:Saudi Arabia|SB:Solomon Islands|SC:Seychelles|"
        "SD:Sudan|SE:Sweden|SG:Singapore|SI:Slovenia|SK:Slovakia|SL:Sierra Leone|SM:San Marino|"
        "SN:Senegal|SO:Somalia|SR:Suriname|SS:South Sudan|ST:São Tomé and Príncipe|SV:El Salvador|"
        "SY:Syria|SZ:Eswatini|TD:Chad|TG:Togo|TH:Thailand|TJ:Tajikistan|TL:Timor-Leste|TM:Turkmenistan|"
        "TN:Tunisia|TO:Tonga|TR:Turkey|TT:Trinidad and Tobago|TV:Tuvalu|TW:Taiwan|TZ:Tanzania|"
        "UA:Ukraine|UG:Uganda|US:United States|UY:Uruguay|UZ:Uzbekistan|VA:Vatican City|"
        "VC:Saint Vincent and the Grenadines|VE:Venezuela|VN:Vietnam|VU:Vanuatu|WS:Samoa|YE:Yemen|"
        "ZA:South Africa|ZM:Zambia|ZW:Zimbabwe"
    ).split("|")
)
COUNTRY_CHOICES = sorted(COUNTRY_NAMES.items(), key=lambda kv: kv[1])

# Other spellings seen in imports, -> (code, confidence, note).
ALIASES = {
    "usa": ("US", "high", "decision: USA -> US"),
    "united states of america": ("US", "high", ""),
    "u.s.a.": ("US", "high", ""),
    "uk": ("GB", "high", "decision: United Kingdom -> GB"),
    "great britain": ("GB", "high", ""),
    "england": ("GB", "medium", "constituent country of the United Kingdom"),
    "scotland": ("GB", "medium", "constituent country of the United Kingdom"),
    "wales": ("GB", "medium", "constituent country of the United Kingdom"),
    "northern ireland": ("GB", "medium", "part of the United Kingdom"),
    "holy see": ("VA", "high", ""),
    "vatican": ("VA", "high", ""),
    "palestinian territories": ("PS", "high", ""),
    "state of palestine": ("PS", "high", ""),
    "czechia": ("CZ", "high", ""),
    "bosnia & herzegovina": ("BA", "high", ""),
    "ivory coast": ("CI", "high", ""),
    "cote d'ivoire": ("CI", "high", ""),
    "türkiye": ("TR", "high", ""),
    "turkiye": ("TR", "high", ""),
    "republic of korea": ("KR", "high", ""),
    "korea": ("KR", "low", "North or South? check the sites"),
    "the netherlands": ("NL", "high", ""),
    "holland": ("NL", "high", ""),
    "macedonia": ("MK", "high", ""),
    "burma": ("MM", "high", ""),
    "swaziland": ("SZ", "high", ""),
    "congo": ("", "", "two countries share this name; check the sites"),
}

_BY_NAME = {name.lower(): code for code, name in COUNTRY_NAMES.items()}
_QUALIFIER_RE = re.compile(r"\s*\((.*)\)\s*$")
_MULTI_RE = re.compile(r"\s*(?:&|/|,|\band\b)\s*")


def country_name(code):
    return COUNTRY_NAMES.get((code or "").upper(), "")


def propose(country):
    """(code, confidence, note) for one free-text country string.

    confidence: "high" (exact name or alias), "medium" (after dropping a
    trailing qualifier like "Italy (tomb)", or a constituent country), or
    "" with no code where unsure -- several countries, or unknown."""
    text = (country or "").strip()
    if not text:
        return "", "", "blank"
    key = text.lower()
    if key in _BY_NAME:
        return _BY_NAME[key], "high", ""
    if key in ALIASES:
        return ALIASES[key]
    match = _QUALIFIER_RE.search(text)
    if match:
        base = text[: match.start()].strip()
        code, confidence, note = propose(base)
        if code:
            note = f'qualifier "({match.group(1)})" dropped' + (f"; {note}" if note else "")
            return code, "medium" if confidence == "high" else confidence, note
        return "", "", f"unknown country {base!r}"
    if len([p for p in _MULTI_RE.split(text) if p]) > 1 and key not in _BY_NAME:
        return "", "", "more than one country"
    return "", "", "unknown country"
