from functools import lru_cache
import re
from typing import Dict, Optional
from zoneinfo import ZoneInfo, available_timezones

# Comprehensive mapping of timezone abbreviations, military/regional names, and common phrases
TIMEZONE_ALIASES: Dict[str, str] = {
    "UTC": "UTC",
    "Z": "UTC",
    "ZULU": "UTC",
    "GMT": "UTC",
    "UCT": "UTC",
    "UNIVERSAL": "UTC",
    # South Asia & Indian Ocean
    "IST": "Asia/Kolkata",
    "INDIA": "Asia/Kolkata",
    "INDIAN STANDARD TIME": "Asia/Kolkata",
    "CALCUTTA": "Asia/Kolkata",
    "KOLKATA": "Asia/Kolkata",
    "MUMBAI": "Asia/Kolkata",
    "DELHI": "Asia/Kolkata",
    "NEW DELHI": "Asia/Kolkata",
    "BANGALORE": "Asia/Kolkata",
    "BENGALURU": "Asia/Kolkata",
    "CHENNAI": "Asia/Kolkata",
    "HYDERABAD": "Asia/Kolkata",
    "PKT": "Asia/Karachi",
    "PAKISTAN": "Asia/Karachi",
    "BDT": "Asia/Dhaka",
    "BANGLADESH": "Asia/Dhaka",
    "NPT": "Asia/Kathmandu",
    "NEPAL": "Asia/Kathmandu",
    "SLT": "Asia/Colombo",
    "SRI LANKA": "Asia/Colombo",
    # Middle East
    "GST": "Asia/Dubai",
    "UAE": "Asia/Dubai",
    "DUBAI": "Asia/Dubai",
    "ABU DHABI": "Asia/Dubai",
    "AST": "Asia/Riyadh",
    "KSA": "Asia/Riyadh",
    "SAUDI": "Asia/Riyadh",
    "SAUDI ARABIA": "Asia/Riyadh",
    "RIYADH": "Asia/Riyadh",
    "DOHA": "Asia/Qatar",
    "QATAR": "Asia/Qatar",
    "MUSCAT": "Asia/Muscat",
    "OMAN": "Asia/Muscat",
    "KUWAIT": "Asia/Kuwait",
    "BAHRAIN": "Asia/Bahrain",
    "IRST": "Asia/Tehran",
    "IRAN": "Asia/Tehran",
    "TRT": "Europe/Istanbul",
    "TURKEY": "Europe/Istanbul",
    # North & South America
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "ET": "America/New_York",
    "EASTERN": "America/New_York",
    "EASTERN TIME": "America/New_York",
    "NEW YORK": "America/New_York",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "CT": "America/Chicago",
    "CENTRAL": "America/Chicago",
    "CENTRAL TIME": "America/Chicago",
    "CHICAGO": "America/Chicago",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "MT": "America/Denver",
    "MOUNTAIN": "America/Denver",
    "MOUNTAIN TIME": "America/Denver",
    "DENVER": "America/Denver",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "PT": "America/Los_Angeles",
    "PACIFIC": "America/Los_Angeles",
    "PACIFIC TIME": "America/Los_Angeles",
    "LOS ANGELES": "America/Los_Angeles",
    "SAN FRANCISCO": "America/Los_Angeles",
    "AKST": "America/Anchorage",
    "AKDT": "America/Anchorage",
    "ALASKA": "America/Anchorage",
    "HST": "Pacific/Honolulu",
    "HAWAII": "Pacific/Honolulu",
    "TORONTO": "America/Toronto",
    "VANCOUVER": "America/Vancouver",
    "MEXICO CITY": "America/Mexico_City",
    "BRT": "America/Sao_Paulo",
    "BRST": "America/Sao_Paulo",
    "SAO PAULO": "America/Sao_Paulo",
    "ART": "America/Argentina/Buenos_Aires",
    "BUENOS AIRES": "America/Argentina/Buenos_Aires",
    "CLT": "America/Santiago",
    "CLST": "America/Santiago",
    "COT": "America/Bogota",
    "PET": "America/Lima",
    # Europe & Africa
    "BST": "Europe/London",
    "UK": "Europe/London",
    "LONDON": "Europe/London",
    "WET": "Europe/Lisbon",
    "WEST": "Europe/Lisbon",
    "LISBON": "Europe/Lisbon",
    "CET": "Europe/Paris",
    "CEST": "Europe/Paris",
    "PARIS": "Europe/Paris",
    "BERLIN": "Europe/Berlin",
    "GERMANY": "Europe/Berlin",
    "FRANKFURT": "Europe/Berlin",
    "AMSTERDAM": "Europe/Amsterdam",
    "ZURICH": "Europe/Zurich",
    "MADRID": "Europe/Madrid",
    "ROME": "Europe/Rome",
    "EET": "Europe/Athens",
    "EEST": "Europe/Athens",
    "MSK": "Europe/Moscow",
    "MOSCOW": "Europe/Moscow",
    "SAST": "Africa/Johannesburg",
    "JOHANNESBURG": "Africa/Johannesburg",
    "EAT": "Africa/Nairobi",
    "NAIROBI": "Africa/Nairobi",
    "WAT": "Africa/Lagos",
    "LAGOS": "Africa/Lagos",
    "CAIRO": "Africa/Cairo",
    # East / SE Asia & Oceania
    "MMT": "Asia/Yangon",
    "ICT": "Asia/Bangkok",
    "BANGKOK": "Asia/Bangkok",
    "WIB": "Asia/Jakarta",
    "JAKARTA": "Asia/Jakarta",
    "WITA": "Asia/Makassar",
    "WIT": "Asia/Jayapura",
    "SGT": "Asia/Singapore",
    "SINGAPORE": "Asia/Singapore",
    "MYT": "Asia/Kuala_Lumpur",
    "MALAYSIA": "Asia/Kuala_Lumpur",
    "HKT": "Asia/Hong_Kong",
    "HONG KONG": "Asia/Hong_Kong",
    "PHT": "Asia/Manila",
    "MANILA": "Asia/Manila",
    "CST CHINA": "Asia/Shanghai",
    "CHINA": "Asia/Shanghai",
    "SHANGHAI": "Asia/Shanghai",
    "BEIJING": "Asia/Shanghai",
    "TAIPEI": "Asia/Taipei",
    "JST": "Asia/Tokyo",
    "JAPAN": "Asia/Tokyo",
    "TOKYO": "Asia/Tokyo",
    "KST": "Asia/Seoul",
    "KOREA": "Asia/Seoul",
    "SEOUL": "Asia/Seoul",
    "AWST": "Australia/Perth",
    "PERTH": "Australia/Perth",
    "ACST": "Australia/Adelaide",
    "ACDT": "Australia/Adelaide",
    "ADELAIDE": "Australia/Adelaide",
    "AEST": "Australia/Sydney",
    "AEDT": "Australia/Sydney",
    "SYDNEY": "Australia/Sydney",
    "MELBOURNE": "Australia/Melbourne",
    "BRISBANE": "Australia/Brisbane",
    "NZST": "Pacific/Auckland",
    "NZDT": "Pacific/Auckland",
    "AUCKLAND": "Pacific/Auckland",
}

OFFSET_MINUTES_TO_IANA: Dict[int, str] = {
    0: "UTC",
    60: "Europe/London",
    120: "Europe/Paris",
    180: "Asia/Riyadh",
    210: "Asia/Tehran",
    240: "Asia/Dubai",
    270: "Asia/Kabul",
    300: "Asia/Karachi",
    330: "Asia/Kolkata",
    345: "Asia/Kathmandu",
    360: "Asia/Dhaka",
    390: "Asia/Yangon",
    420: "Asia/Bangkok",
    480: "Asia/Singapore",
    540: "Asia/Tokyo",
    570: "Australia/Adelaide",
    600: "Australia/Sydney",
    720: "Pacific/Auckland",
    765: "Pacific/Chatham",
    -180: "America/Sao_Paulo",
    -210: "America/St_Johns",
    -240: "America/Halifax",
    -300: "America/New_York",
    -360: "America/Chicago",
    -420: "America/Denver",
    -480: "America/Los_Angeles",
    -540: "America/Anchorage",
    -600: "Pacific/Honolulu",
}


@lru_cache(maxsize=1)
def _build_tz_indexes():
    """
    Build cached case-insensitive indexes over all network IANA time zones
    from zoneinfo.available_timezones().
    """
    all_zones = sorted(available_timezones())
    lower_map: Dict[str, str] = {}
    city_map: Dict[str, str] = {}

    for zone in all_zones:
        lower_map[zone.lower()] = zone
        # Map space-separated variant too (e.g. "america/new york" -> "America/New_York")
        lower_map[zone.lower().replace("_", " ")] = zone

        if "/" in zone and not zone.startswith(("Etc/", "SystemV/")):
            city = zone.split("/")[-1].replace("_", " ").strip().lower()
            if city and city not in city_map:
                city_map[city] = zone

    return tuple(all_zones), lower_map, city_map


def list_all_timezones() -> list[str]:
    zones, _, _ = _build_tz_indexes()
    return list(zones)


def _resolve_offset_minutes(sign: str, hours: int, minutes: int) -> Optional[str]:
    total_mins = (hours * 60 + minutes) * (-1 if sign == "-" else 1)
    if total_mins < -720 or total_mins > 840:
        return None
    if total_mins in OFFSET_MINUTES_TO_IANA:
        cand = OFFSET_MINUTES_TO_IANA[total_mins]
        try:
            ZoneInfo(cand)
            return cand
        except Exception:
            pass
    if minutes == 0:
        # POSIX Etc/GMT sign convention is inverted (Etc/GMT-4 == UTC+4)
        etc_sign = "-" if sign == "+" else "+"
        etc_name = f"Etc/GMT{etc_sign}{hours}" if hours != 0 else "UTC"
        try:
            ZoneInfo(etc_name)
            return etc_name
        except Exception:
            pass
    return None


def normalize_timezone(raw_tz: Optional[str]) -> Optional[str]:
    """
    Normalize any user-supplied network/IANA timezone, abbreviation, city, or UTC/GMT offset
    (e.g. 'Asia/kolkata', 'america/new_york', 'IST', 'UTC+5:30', '+05:30') to a valid
    canonical ZoneInfo timezone key, or None if invalid.
    """
    if not raw_tz:
        return None
    cleaned = re.sub(r"\s+", " ", str(raw_tz).strip())
    if not cleaned:
        return None

    _, lower_map, city_map = _build_tz_indexes()

    # 1. Exact case-insensitive IANA match (supports "Asia/kolkata" -> "Asia/Kolkata")
    if cleaned.lower() in lower_map:
        cand = lower_map[cleaned.lower()]
        try:
            ZoneInfo(cand)
            return cand
        except Exception:
            pass

    # 2. Direct alias match
    upper = cleaned.upper()
    if upper in TIMEZONE_ALIASES:
        cand = TIMEZONE_ALIASES[upper]
        try:
            ZoneInfo(cand)
            return cand
        except Exception:
            pass

    # 3. City name lookup from full IANA tzdb
    city_key = cleaned.lower().replace("_", " ")
    if city_key in city_map:
        cand = city_map[city_key]
        try:
            ZoneInfo(cand)
            return cand
        except Exception:
            pass

    # 4. Numeric UTC/GMT offset (e.g. "UTC+5:30", "GMT-04:00", "+05:30")
    m_off = re.match(
        r"^(?:(?:UTC|GMT)\s*)?([+-])\s*(\d{1,2})(?::?(\d{2}))?$",
        upper,
    )
    if m_off:
        sign = m_off.group(1)
        hrs = int(m_off.group(2))
        mins = int(m_off.group(3) or 0)
        if 0 <= hrs <= 14 and 0 <= mins < 60:
            resolved = _resolve_offset_minutes(sign, hrs, mins)
            if resolved:
                return resolved

    # 5. Final direct ZoneInfo validation attempt
    try:
        ZoneInfo(cleaned)
        return cleaned
    except Exception:
        return None


def extract_timezone_from_text(text: str, *, expecting_timezone: bool = False) -> Optional[str]:
    """
    Extract a canonical network IANA timezone from freeform WhatsApp/chat text.
    Supports case-insensitive Area/Location(/Sublocation) zones, UTC/GMT offsets,
    standard abbreviations, and city/country names.
    """
    if not text:
        return None
    cleaned_text = re.sub(r"\s+", " ", text.strip())
    _, lower_map, city_map = _build_tz_indexes()

    # 1. Any <Region>/<City> or <Region>/<State>/<City> token (case-insensitive!)
    for m_iana in re.finditer(r"\b([a-zA-Z][a-zA-Z_]+/[a-zA-Z][a-zA-Z0-9_\-]+(?:/[a-zA-Z][a-zA-Z0-9_\-]+)?)\b", cleaned_text):
        token = m_iana.group(1)
        norm = normalize_timezone(token)
        if norm:
            return norm

    # 2. Numeric UTC/GMT offset (e.g. "UTC+5:30", "GMT +04:00", "UTC-5")
    m_utc = re.search(
        r"\b(?:UTC|GMT)\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?\b",
        cleaned_text,
        re.IGNORECASE,
    )
    if m_utc:
        resolved = _resolve_offset_minutes(
            m_utc.group(1), int(m_utc.group(2)), int(m_utc.group(3) or 0)
        )
        if resolved:
            return resolved

    # Bare numeric offset like "+05:30" or "-04:00" when expecting timezone
    if expecting_timezone:
        m_bare = re.search(r"(?:^|\s)([+-])(\d{1,2}):(\d{2})(?:\s|$)", cleaned_text)
        if m_bare:
            resolved = _resolve_offset_minutes(
                m_bare.group(1), int(m_bare.group(2)), int(m_bare.group(3))
            )
            if resolved:
                return resolved

    # 3. Standard abbreviations / multi-word timezone aliases
    # Long multi-word phrases first ("indian standard time", "eastern time", etc.)
    lower = cleaned_text.lower()
    for alias in sorted((k for k in TIMEZONE_ALIASES if len(k) > 4), key=len, reverse=True):
        alias_l = alias.lower()
        # Require either contextual words, standalone message when expecting timezone, or city/country exact word match
        if re.search(rf"\b{re.escape(alias_l)}\b", lower):
            # Avoid matching common English word "central"/"eastern"/"mountain"/"pacific" unless paired with "time"/"zone" or expecting_timezone
            ambiguous = alias_l in ("eastern", "central", "mountain", "pacific", "universal")
            if ambiguous and not expecting_timezone and not re.search(rf"\b{re.escape(alias_l)}\s+(?:time|zone|tz|time\s*zone)\b", lower):
                continue
            return TIMEZONE_ALIASES[alias]

    # Short 2-5 letter abbreviations: match if uppercase in original text OR if expecting_timezone / accompanied by time-zone context
    short_aliases = [k for k in TIMEZONE_ALIASES if len(k) <= 4]
    has_tz_context = expecting_timezone or bool(re.search(r"\b(tz|time\s*zone|timezone|time)\b", lower))
    for alias in short_aliases:
        if alias in ("Z", "ET", "CT", "MT", "PT") and not has_tz_context:
            # Avoid false positives on casual words like "et", "pt", "mt", "z"
            if not re.search(rf"\b{alias}\b", cleaned_text):
                continue
        pattern = rf"\b{re.escape(alias)}\b" if not has_tz_context else rf"\b{re.escape(alias.lower())}\b"
        target_str = cleaned_text if not has_tz_context else lower
        if re.search(pattern, target_str):
            return TIMEZONE_ALIASES[alias]

    # 4. City suffix from full IANA tzdb (e.g. "barcelona", "stockholm", "cairo") when expecting timezone or phrased as "<city> time/timezone"
    if expecting_timezone:
        # Check longest city names first
        for city_key, canonical_zone in sorted(city_map.items(), key=lambda kv: len(kv[0]), reverse=True):
            if len(city_key) >= 4 and re.search(rf"\b{re.escape(city_key)}\b", lower):
                return canonical_zone
    else:
        m_city_ctx = re.search(r"\b([a-zA-Z][a-zA-Z ]{2,30}?)\s+(?:time\s*zone|timezone|time)\b", lower)
        if m_city_ctx:
            cand_city = m_city_ctx.group(1).strip()
            norm = normalize_timezone(cand_city)
            if norm:
                return norm

    return None
