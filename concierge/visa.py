"""Entry requirement lookup."""

from . import store
from .store import ToolError


def check_visa_requirements(destination, nationality=None, stay_days=None) -> dict:
    country = store.resolve_country(destination)
    code = str(nationality or store.TRAVELER["passport_nationality"]).strip().upper()
    rule = store.VISA_RULES[country].get(code)
    if rule is None:
        raise ToolError(f"no rule on file for passport nationality {code}")
    result = dict(rule, destination=country, passport_nationality=code)
    if stay_days is not None:
        if not isinstance(stay_days, int) or stay_days < 1:
            raise ToolError("stay_days must be a positive whole number")
        limit = rule["max_stay_days"]
        if not rule["visa_required"] and limit is not None and stay_days > limit:
            result["visa_required"] = True
            result["notes"] = f"A stay of {stay_days} days exceeds the {limit}-day visa-free limit."
    return result
