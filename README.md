# Travel concierge

A multi-agent travel concierge built with [Google ADK](https://github.com/google/adk-python). A root agent hands each request to a specialist: inspiration (destinations, attractions, visas), planning (flights and hotels), booking (hold, pay, cancel) and in-trip (the traveler's existing itinerary). It serves an OpenAI-style chat endpoint.

The agent structure and prompts are adapted from the `travel-concierge` sample in [google/adk-samples](https://github.com/google/adk-samples/tree/b822efc7710498dfa4ff0d405c20ecdc6b92c8e3/python/agents/travel-concierge) (Apache-2.0, see `LICENSE`). Search and map tools were replaced with seeded JSON data so it runs offline.

## Tools

| Tool | What it does |
|---|---|
| `search_flights` | Flights between two airports for a date, optional return, cabin and price cap |
| `search_hotels` | Hotels in a city for a stay, with totals and cancellation terms |
| `get_attractions` | Attractions and activities by city and category |
| `check_visa_requirements` | Entry requirements for a destination |
| `get_itinerary` | The traveler's bookings, status and cancellation policy |
| `hold_booking` | Reserve a flight or hotel offer without paying |
| `confirm_booking` | Pay for a held booking with a saved payment method |
| `cancel_booking` | Cancel a booking and apply its refund policy |

## Run

```sh
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
export LLM_BASE_URL=https://your-gateway/v1 LLM_API_KEY=... LLM_MODEL=your-model
.venv/bin/python agent.py
```

The model is reached through ADK's LiteLLM wrapper (`openai/<LLM_MODEL>` on `LLM_BASE_URL`), so any OpenAI-compatible endpoint works.

- `GET /health` returns `{"status": "ok"}`.
- `POST /v1/chat/completions` (also `/chat/completions`) takes an OpenAI chat request with the full `messages` history and returns a chat completion plus `completed_tools`, the tools run for that reply.

## Environment variables

| Variable | Required | Meaning |
|---|---|---|
| `LLM_BASE_URL` | yes | OpenAI-compatible base URL, ending in `/v1` |
| `LLM_API_KEY` | yes | API key for that endpoint |
| `LLM_MODEL` | yes | Model name |
| `PORT` | no | Listen port, default 8080 |

## Layout

- `agent.py` HTTP server and ADK runner
- `config.py` model and booking settings
- `prompts/` instructions for each agent
- `concierge/agents.py` agent tree; `concierge/tools.py` tool schemas
- `concierge/search.py`, `visa.py`, `bookings.py` tool logic; `data/` seeded flights, hotels, attractions, visa rules and traveler profile
