"""Tool definitions exposed to the model. Names, docstrings and signatures are the tool schemas."""

import functools
from typing import Optional

from . import bookings, search, visa
from .store import ToolError


def _guard(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ToolError as exc:
            return {"error": str(exc)}

    return wrapper


@_guard
def search_flights(
    origin: str,
    destination: str,
    depart_date: str,
    passengers: int = 1,
    cabin: str = "economy",
    return_date: Optional[str] = None,
    max_price: Optional[float] = None,
) -> dict:
    """Search flights between two airports. Returns outbound (and return, when return_date is given) options with offer_id, times, price per passenger in USD and seats left.

    Args:
        origin: Three-letter IATA airport code only, never a city name: convert city names to the code first, for example Mumbai -> BOM, Lisbon -> LIS, London -> LHR.
        destination: Three-letter IATA airport code only, never a city name: convert city names to the code first.
        depart_date: Departure date, YYYY-MM-DD.
        passengers: Number of passengers, 1 to 9.
        cabin: economy, premium_economy or business.
        return_date: Return date YYYY-MM-DD for a round trip.
        max_price: Maximum price per passenger in USD.
    """
    return search.search_flights(origin, destination, depart_date, passengers, cabin, return_date, max_price)


@_guard
def search_hotels(
    city: str,
    check_in: str,
    check_out: str,
    guests: int = 1,
    max_price_per_night: Optional[float] = None,
    min_stars: Optional[int] = None,
) -> dict:
    """Search hotels in a city for a stay. Returns offers with offer_id, nightly rate, number of nights, total price per room including tax, currency and cancellation policy. Prices are in each hotel's local currency.

    Args:
        city: City name, for example Lisbon.
        check_in: Check-in date, YYYY-MM-DD.
        check_out: Check-out date, YYYY-MM-DD.
        guests: Number of guests, 1 to 8.
        max_price_per_night: Maximum total price for the whole stay, in the hotel's currency.
        min_stars: Minimum star rating, 1 to 5.
    """
    return search.search_hotels(city, check_in, check_out, guests, max_price_per_night, min_stars)


@_guard
def get_attractions(city: str, category: Optional[str] = None, max_price: Optional[float] = None) -> dict:
    """List attractions and activities in a city with category, typical price and suggested hours needed.

    Args:
        city: City name.
        category: One of history, museum, food, outdoors, landmark, entertainment, sightseeing.
        max_price: Only return attractions priced at or below this amount in the local currency.
    """
    return search.get_attractions(city, category, max_price)


@_guard
def check_visa_requirements(destination: str, nationality: Optional[str] = None, stay_days: Optional[int] = None) -> dict:
    """Check whether a passport holder needs a visa for a destination country, with visa type, maximum stay, processing time in days and notes.

    Args:
        destination: Country name, never a city: convert city names to their country first, for example London -> United Kingdom, Lisbon -> Portugal.
        nationality: Two-letter passport nationality code, for example IN, US or GB. Defaults to the traveler's own passport.
        stay_days: Planned length of stay in days.
    """
    return visa.check_visa_requirements(destination, nationality, stay_days)


@_guard
def get_itinerary(booking_id: Optional[str] = None, status: Optional[str] = None) -> dict:
    """List the traveler's bookings (flights and hotels) with dates, status, price paid, confirmation code and cancellation policy. Call it before changing or cancelling anything.

    Args:
        booking_id: Return only this booking, for example BK1001.
        status: Filter by held, confirmed or cancelled.
    """
    return bookings.get_itinerary(booking_id, status)


@_guard
def hold_booking(offer_id: str, quantity: int = 1) -> dict:
    """Reserve a flight or hotel offer without paying. Creates a booking with status held and a hold expiry. Returns booking_id, total price and currency.

    Args:
        offer_id: The offer_id returned by search_flights or search_hotels.
        quantity: Passengers for a flight, rooms for a hotel.
    """
    return bookings.hold_booking(offer_id, quantity)


@_guard
def confirm_booking(booking_id: str, payment_method_id: str) -> dict:
    """Charge the payment method and confirm a held booking. Returns the confirmation code and the payment taken.

    Args:
        booking_id: A booking in held status, for example BK2003.
        payment_method_id: A saved payment method id, such as card_4242 or upi_maya.
    """
    return bookings.confirm_booking(booking_id, payment_method_id)


@_guard
def cancel_booking(booking_id: str, reason: Optional[str] = None) -> dict:
    """Cancel a held or confirmed booking and apply its refund policy. Returns the refund percent and amount.

    Args:
        booking_id: The booking to cancel, for example BK1001.
        reason: Why the traveler is cancelling.
    """
    return bookings.cancel_booking(booking_id, reason)
