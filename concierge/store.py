"""Seed data loaded from the data/ directory at startup."""

import json
from datetime import date, datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load(name: str):
    return json.loads((DATA_DIR / name).read_text())


AIRPORTS: dict[str, dict] = _load("airports.json")
HOTELS: list[dict] = _load("hotels.json")
ATTRACTIONS: dict[str, list[dict]] = _load("attractions.json")
VISA_RULES: dict[str, dict] = _load("visa_rules.json")
TRAVELER: dict = _load("traveler.json")


class ToolError(Exception):
    """A problem with the arguments or the state, reported back to the model."""


def parse_date(text: str, label: str = "date") -> date:
    try:
        return datetime.strptime(str(text).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ToolError(f"{label} must be a calendar date formatted YYYY-MM-DD") from None


def future_date(text: str, label: str = "date") -> date:
    day = parse_date(text, label)
    if day < date.today():
        raise ToolError(f"{label} {day.isoformat()} is in the past")
    return day


def resolve_airport(text: str) -> str:
    key = str(text).strip()
    if key.upper() in AIRPORTS:
        return key.upper()
    for code, info in AIRPORTS.items():
        if info["city"].lower() == key.lower():
            return code
    raise ToolError(f"unknown airport or city '{text}'; served airports: " + ", ".join(AIRPORTS))


def resolve_city(text: str) -> str:
    key = str(text).strip().lower()
    for info in AIRPORTS.values():
        if info["city"].lower() == key:
            return info["city"]
    for code, info in AIRPORTS.items():
        if code.lower() == key:
            return info["city"]
    raise ToolError(f"no data for '{text}'; cities covered: " + ", ".join(i["city"] for i in AIRPORTS.values()))


def resolve_country(text: str) -> str:
    key = str(text).strip().lower()
    for country in VISA_RULES:
        if country.lower() == key:
            return country
    for info in AIRPORTS.values():
        if info["city"].lower() == key or info["country"].lower() == key:
            return info["country"]
    aliases = {"uk": "United Kingdom", "england": "United Kingdom", "uae": "United Arab Emirates", "usa": "United States", "us": "United States"}
    if key in aliases:
        return aliases[key]
    raise ToolError(f"no visa data for '{text}'")
