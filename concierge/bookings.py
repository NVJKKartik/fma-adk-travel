"""Booking lifecycle: hold, confirm, cancel, itinerary. State lives in memory."""

import threading
import uuid
from datetime import date, datetime, timedelta

import config
from . import search, store
from .store import ToolError

_lock = threading.Lock()
_bookings: dict[str, dict] = {}
_counter = 5000

FLIGHT_POLICY = "Full refund until 7 days before departure, 50% refund until 48 hours before, nothing after that."


def _now() -> datetime:
    return datetime.now()


def _policy_for(b: dict) -> str:
    return FLIGHT_POLICY if b["type"] == "flight" else search.CANCELLATION_TEXT[b["policy"]]


def _public(b: dict) -> dict:
    row = {k: v for k, v in b.items() if k not in ("policy",)}
    row["cancellation_policy"] = _policy_for(b)
    return row


def _seed() -> None:
    today = date.today()

    def add(bid, kind, desc, start, base, taxes, cur, policy, status="confirmed", qty=1):
        _bookings[bid] = {
            "booking_id": bid, "type": kind, "description": desc, "status": status, "quantity": qty,
            "starts": start.strftime("%Y-%m-%d %H:%M"), "base_price": base, "taxes": taxes,
            "total_price": round(base + taxes, 2), "currency": cur, "policy": policy,
            "offer_id": None, "confirmation_code": f"FA{bid[-4:]}XK", "payment": {
                "method": "card_4242", "amount": round(base + taxes, 2), "currency": cur},
        }

    d = lambda n, h=0, m=0: datetime.combine(today + timedelta(days=n), datetime.min.time()) + timedelta(hours=h, minutes=m)
    add("BK1001", "flight", "BOM to LHR, flight AF512, economy, 1 passenger", d(20, 7, 10), 540.0, 97.2, "USD", "flight")
    add("BK1002", "hotel", "The Marlowe Hotel, London, 5 nights, 1 room", d(20, 15), 1050.0, 210.0, "GBP", "flexible")
    add("BK1003", "flight", "LHR to BOM, flight EK744, economy, 1 passenger", d(25, 13, 45), 520.0, 93.6, "USD", "flight")
    add("BK2001", "hotel", "Marina Vista, Singapore, 5 nights, 1 room", d(-1, 15), 1900.0, 171.0, "SGD", "moderate")
    add("BK2002", "flight", "SIN to BOM, flight SQ208, economy, 1 passenger", d(4, 21, 30), 330.0, 59.4, "USD", "flight")
    add("BK3001", "hotel", "Hotel Lumiere, Paris, 3 nights, 1 room", d(2, 15), 555.0, 55.5, "EUR", "flexible")
    add("BK3002", "flight", "BOM to CDG, flight EK431, economy, 1 passenger", d(2, 13, 45), 610.0, 109.8, "USD", "flight")


_seed()


def get_itinerary(booking_id=None, status=None) -> dict:
    rows = [b for b in _bookings.values() if (not booking_id or b["booking_id"] == booking_id.strip().upper())
            and (not status or b["status"] == status)]
    if booking_id and not rows:
        raise ToolError(f"no booking {booking_id}")
    rows.sort(key=lambda b: b["starts"])
    return {"traveler": store.TRAVELER["name"], "today": date.today().isoformat(), "bookings": [_public(b) for b in rows]}


def hold_booking(offer_id, quantity=1) -> dict:
    global _counter
    if not isinstance(quantity, int) or not 1 <= quantity <= 9:
        raise ToolError("quantity must be a whole number from 1 to 9")
    kind = str(offer_id).split(":")[0]
    if kind == "FL":
        f = search.flight_from_offer(offer_id)
        base, taxes = f["base_price_per_passenger"] * quantity, f["taxes_per_passenger"] * quantity
        desc = f"{f['origin']} to {f['destination']}, flight {f['flight_number']}, {f['cabin']}, {quantity} passenger(s)"
        start, cur, policy = f["departs"], f["currency"], "flight"
    elif kind == "HT":
        h, cin, cout = search.hotel_from_offer(offer_id)
        if cout <= cin:
            raise ToolError("check-out must be after check-in")
        if quantity > h["rooms_left"]:
            raise ToolError(f"only {h['rooms_left']} room(s) left at {h['name']}")
        nights = search.stay_nights(cin, cout)
        base = h["nightly_rate"] * nights * quantity
        taxes = base * h["tax_pct"] / 100
        desc = f"{h['name']}, {h['city']}, {nights} nights, {quantity} room(s)"
        start, cur, policy = f"{cin.isoformat()} 15:00", h["currency"], h["cancellation"]
    else:
        raise ToolError("offer_id must come from search_flights or search_hotels")
    with _lock:
        _counter += 1
        bid = f"BK{_counter}"
        _bookings[bid] = {
            "booking_id": bid, "type": "flight" if kind == "FL" else "hotel", "description": desc,
            "status": "held", "quantity": quantity, "starts": start, "base_price": round(base, 2),
            "taxes": round(taxes, 2), "total_price": round(base + taxes, 2), "currency": cur, "policy": policy,
            "offer_id": offer_id, "confirmation_code": None, "payment": None,
            "hold_expires": (_now() + timedelta(minutes=config.HOLD_MINUTES)).strftime("%Y-%m-%d %H:%M"),
        }
        return _public(_bookings[bid])


def confirm_booking(booking_id, payment_method_id) -> dict:
    b = _bookings.get(str(booking_id).strip().upper())
    if b is None:
        raise ToolError(f"no booking {booking_id}")
    if b["status"] != "held":
        raise ToolError(f"booking {b['booking_id']} is {b['status']}, only held bookings can be confirmed")
    if _now() > datetime.strptime(b["hold_expires"], "%Y-%m-%d %H:%M"):
        b["status"] = "expired"
        raise ToolError("the hold has expired; search again and make a new hold")
    methods = {m["id"]: m for m in store.TRAVELER["payment_methods"]}
    if payment_method_id not in methods:
        raise ToolError("unknown payment method; saved methods: " + ", ".join(methods))
    with _lock:
        b["status"] = "confirmed"
        b["confirmation_code"] = "FA" + uuid.uuid4().hex[:6].upper()
        b["payment"] = {"method": payment_method_id, "amount": b["total_price"], "currency": "USD"}
        b.pop("hold_expires", None)
    return _public(b)


def _refund_fraction(b: dict, hours_left: float) -> float:
    if b["type"] == "flight":
        return 1.0 if hours_left >= 168 else 0.5 if hours_left >= 48 else 0.0
    policy = b["policy"]
    if policy == "flexible":
        return 1.0 if hours_left >= 48 else 0.0
    if policy == "moderate":
        return 1.0 if hours_left >= 168 else 0.5 if hours_left >= 48 else 0.0
    return 0.0


def cancel_booking(booking_id, reason=None) -> dict:
    b = _bookings.get(str(booking_id).strip().upper())
    if b is None:
        raise ToolError(f"no booking {booking_id}")
    if b["status"] in ("cancelled", "expired"):
        raise ToolError(f"booking {b['booking_id']} is already {b['status']}")
    started = datetime.strptime(b["starts"], "%Y-%m-%d %H:%M") <= _now()
    if started and b["status"] == "confirmed":
        raise ToolError("this booking has already started and can no longer be cancelled")
    with _lock:
        if b["status"] == "held":
            refund, fraction = 0.0, 0.0
        else:
            hours_left = (datetime.strptime(b["starts"], "%Y-%m-%d %H:%M") - _now()).total_seconds() / 3600
            fraction = _refund_fraction(b, hours_left)
            refund = round(fraction * b["base_price"], 2)
        b["status"] = "cancelled"
    return {
        "booking_id": b["booking_id"], "status": "cancelled", "reason": reason,
        "refund_percent": int(fraction * 100), "refund_amount": refund, "currency": b["currency"],
        "refund_eta_days": 7 if refund else None,
        "cancellation_policy": _policy_for(b),
    }
