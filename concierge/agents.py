"""Agent tree: a root concierge that hands over to specialist sub-agents."""

import json
from datetime import date
from pathlib import Path

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.genai import types

import config
from . import store, tools

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _prompt(name: str):
    template = (PROMPT_DIR / f"{name}.md").read_text()
    shared = (PROMPT_DIR / "visa_guidance.md").read_text()

    def provider(_ctx) -> str:
        text = template.replace("{{VISA_GUIDANCE}}", shared)
        text = text.replace("{{TODAY}}", date.today().strftime("%A %Y-%m-%d"))
        return text.replace("{{TRAVELER}}", json.dumps(store.TRAVELER, indent=1))

    return provider


def build_root(env: dict[str, str]) -> Agent:
    model = LiteLlm(model="openai/" + env["LLM_MODEL"], api_base=env["LLM_BASE_URL"], api_key=env["LLM_API_KEY"])
    gen = types.GenerateContentConfig(temperature=config.TEMPERATURE, max_output_tokens=config.MAX_OUTPUT_TOKENS)

    inspiration = Agent(
        model=model, name="inspiration_agent", generate_content_config=gen,
        description="Destination ideas, things to do, attractions and entry or visa requirements.",
        instruction=_prompt("inspiration"),
        tools=[tools.get_attractions, tools.check_visa_requirements],
    )
    planning = Agent(
        model=model, name="planning_agent", generate_content_config=gen,
        description="Finds and compares flights and hotels, prices and availability for a trip.",
        instruction=_prompt("planning"),
        tools=[tools.search_flights, tools.search_hotels, tools.check_visa_requirements],
    )
    booking = Agent(
        model=model, name="booking_agent", generate_content_config=gen,
        description="Books a chosen flight or hotel: holds it, takes payment and handles cancellations and refunds.",
        instruction=_prompt("booking"),
        tools=[tools.get_itinerary, tools.hold_booking, tools.confirm_booking, tools.cancel_booking],
    )
    in_trip = Agent(
        model=model, name="in_trip_agent", generate_content_config=gen,
        description="The traveler's existing or ongoing trip: what is booked, when it starts and what to do during it. It does not cancel or refund.",
        instruction=_prompt("in_trip"),
        tools=[tools.get_itinerary, tools.get_attractions],
    )
    return Agent(
        model=model, name="root_agent", generate_content_config=gen,
        description="Travel concierge that routes each request to the right specialist.",
        instruction=_prompt("root"),
        sub_agents=[inspiration, planning, booking, in_trip],
    )
