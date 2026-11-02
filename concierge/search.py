"""Flight, hotel and attraction search over the seeded data."""

import hashlib
import math
from datetime import datetime, timedelta

from . import store
from .store import ToolError

CABIN_FACTOR = {"economy": 1.0, "premium_economy": 1.6, "business": 3.2}
DEPARTURE_SLOTS = [("07:10", "AF"), ("13:45", "EK"), ("21:30", "SQ")]
FLIGHT_TAX_RATE = 0.18

CANCELLATION_TEXT = {
    "flexible": "Free cancellation until 48 hours before check-in; no refund after that.",
    "moderate": "Full refund until 7 days before check-in, 50% refund until 48 hours before, nothing after that.",
    "strict": "Non-refundable.",
}


def _hash(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def _distance_km(a: str, b: str) -> float:
    pa, pb = store.AIRPORTS[a], store.AIRPORTS[b]
    la1, lo1, la2, lo2 = map(math.radians, (pa["lat"], pa["lon"], pb["lat"], pb["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _flights_on(origin: str, dest: str, day, cabin: str) -> list[dict]:
    km = _distance_km(origin, dest)
    hours = km / 820 + 0.6
    weekend = 1.12 if day.weekday() in (4, 6) else 1.0
    out = []
    for i, (hhmm, carrier) in enumerate(DEPARTURE_SLOTS):
        number = f"{carrier}{100 + _hash(origin, dest, i) % 800}"
        base = (45 + km * 0.07 + i * 12) * weekend * CABIN_FACTOR[cabin]
        base = round(base, 2)
        taxes = round(base * FLIGHT_TAX_RATE, 2)
        depart = datetime.strptime(f"{day.isoformat()} {hhmm}", "%Y-%m-%d %H:%M")
        arrive = depart + timedelta(minutes=int(hours * 60))
        seats = 2 + _hash(number, day.isoformat()) % 30
        out.append({
            "offer_id": f"FL:{number}:{day.isoformat()}:{cabin}",
            "flight_number": number,
            "origin": origin,
            "destination": dest,
            "departs": depart.strftime("%Y-%m-%d %H:%M"),
            "arrives": arrive.strftime("%Y-%m-%d %H:%M"),
            "duration_hours": round(hours, 1),
            "cabin": cabin,
            "base_price_per_passenger": base,
            "taxes_per_passenger": taxes,
            "price_per_passenger": round(base + taxes, 2),
            "currency": "USD",
            "seats_left": seats,
        })
    return out


def flight_from_offer(offer_id: str) -> dict:
    try:
        _, number, day_text, cabin = offer_id.split(":")
    except ValueError:
        raise ToolError("unrecognised flight offer_id") from None
    day = store.future_date(day_text, "flight date")
    if cabin not in CABIN_FACTOR:
        raise ToolError("unrecognised flight offer_id")
    for origin in store.AIRPORTS:
        for dest in store.AIRPORTS:
            if origin == dest:
                continue
            for f in _flights_on(origin, dest, day, cabin):
                if f["flight_number"] == number and f["offer_id"] == offer_id:
                    return f
    raise ToolError("that flight offer does not exist")


def search_flights(origin, destination, depart_date, passengers=1, cabin="economy", return_date=None, max_price=None) -> dict:
    o, d = store.resolve_airport(origin), store.resolve_airport(destination)
    if o == d:
        raise ToolError("origin and destination are the same")
    day = store.future_date(depart_date, "depart_date")
    cabin = str(cabin).lower()
    if cabin not in CABIN_FACTOR:
        raise ToolError("cabin must be one of: " + ", ".join(CABIN_FACTOR))
    if not isinstance(passengers, int) or not 1 <= passengers <= 9:
        raise ToolError("passengers must be a whole number from 1 to 9")
    result = {"outbound": _filter(_flights_on(o, d, day, cabin), passengers, max_price)}
    if return_date:
        back = store.future_date(return_date, "return_date")
        if back < day:
            raise ToolError("return_date is before depart_date")
        result["return"] = _filter(_flights_on(d, o, back, cabin), passengers, max_price)
    return result


def _filter(flights, passengers, max_price):
    rows = [f for f in flights if f["seats_left"] >= passengers]
    if max_price is not None:
        rows = [f for f in rows if f["price_per_passenger"] <= float(max_price)]
    return rows


def stay_nights(check_in, check_out) -> int:
    return (check_out - check_in).days + 1


def hotel_from_offer(offer_id: str) -> tuple[dict, object, object]:
    try:
        _, hotel_id, cin, cout = offer_id.split(":")
    except ValueError:
        raise ToolError("unrecognised hotel offer_id") from None
    hotel = next((h for h in store.HOTELS if h["hotel_id"] == hotel_id), None)
    if hotel is None:
        raise ToolError("that hotel offer does not exist")
    return hotel, store.future_date(cin, "check-in date"), store.future_date(cout, "check-out date")


def search_hotels(city, check_in, check_out, guests=1, max_price_per_night=None, min_stars=None) -> dict:
    name = store.resolve_city(city)
    cin, cout = store.future_date(check_in, "check_in"), store.future_date(check_out, "check_out")
    if cout <= cin:
        raise ToolError("check_out must be after check_in")
    if not isinstance(guests, int) or not 1 <= guests <= 8:
        raise ToolError("guests must be a whole number from 1 to 8")
    nights = stay_nights(cin, cout)
    rooms = math.ceil(guests / 2)
    rows = []
    for h in store.HOTELS:
        if h["city"] != name or h["rooms_left"] < rooms:
            continue
        if max_price_per_night is not None and h["nightly_rate"] > float(max_price_per_night):
            continue
        if min_stars is not None and h["stars"] < int(min_stars):
            continue
        base = h["nightly_rate"] * nights
        rows.append({
            "offer_id": f"HT:{h['hotel_id']}:{cin.isoformat()}:{cout.isoformat()}",
            "name": h["name"],
            "stars": h["stars"],
            "nightly_rate": h["nightly_rate"],
            "nights": nights,
            "rooms_needed": rooms,
            "tax_pct": h["tax_pct"],
            "total_price_per_room": round(base * (1 + h["tax_pct"] / 100), 2),
            "currency": h["currency"],
            "cancellation_policy": CANCELLATION_TEXT[h["cancellation"]],
            "amenities": h["amenities"],
            "rooms_left": h["rooms_left"],
        })
    return {"city": name, "check_in": cin.isoformat(), "check_out": cout.isoformat(), "hotels": rows}


def get_attractions(city, category=None, max_price=None) -> dict:
    name = store.resolve_city(city)
    rows = store.ATTRACTIONS.get(name, [])
    if category:
        rows = [a for a in rows if a["category"] == str(category).lower()]
    if max_price is not None:
        rows = [a for a in rows if a["price"] <= float(max_price)]
    return {"city": name, "attractions": rows}
