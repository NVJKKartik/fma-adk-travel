"""Runtime settings for the travel concierge."""

import os
import sys

# Model sampling
TEMPERATURE = 0.2
MAX_OUTPUT_TOKENS = 4000

# Upper bound on model calls for one reply (routing hops, tool rounds and the final answer).
MAX_LLM_CALLS = 12

# Earlier chat messages passed to the agent along with the latest one.
# Must be large enough that a chosen offer_id, a corrected quantity or a chosen
# flight from earlier turns still reaches the booking specialist.
HISTORY_MESSAGES = 40

# Booking holds are released after this many minutes.
HOLD_MINUTES = 30

PORT = int(os.environ.get("PORT", "8080"))


def require_env() -> dict[str, str]:
    missing = [k for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL") if not os.environ.get(k)]
    if missing:
        sys.exit(f"Missing required environment variables: {', '.join(missing)}")
    return {k: os.environ[k] for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")}
