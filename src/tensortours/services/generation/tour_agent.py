"""Stage 2: Tour generation pipeline using Google ADK SequentialAgent.

Pipeline:
  wikipedia_agent   — fetches Wikipedia content for the POI
  research_router   — decides if Wikipedia is sufficient; if not, transfers to web_search_agent
    └─ web_search_agent  — searches the web (google_search tool, must be its only tool)
  generation_agent  — produces structured TourOutput from all research
"""

import asyncio
import logging
import os
import uuid
from functools import lru_cache
from typing import Any, Dict, List, Optional

import requests
from google.adk.agents import Agent, SequentialAgent  # type: ignore[import]
from google.adk.runners import Runner  # type: ignore[import]
from google.adk.sessions import InMemorySessionService  # type: ignore[import]
from google.adk.tools import google_search  # type: ignore[import]
from google.genai import types as genai_types  # type: ignore[import]
from pydantic import BaseModel

from ...models.generation import GenerationConfig, PoiInputData
from ...utils.aws import get_api_key_from_secret

logger = logging.getLogger(__name__)

GEMINI_API_KEY_SECRET_NAME = os.environ.get("GEMINI_API_KEY_SECRET_NAME", "gemini-api-key")

# -------------------------------------------------------------------
# Structured output schema
# -------------------------------------------------------------------


class TourOutput(BaseModel):
    """Structured output from the generation agent."""

    recommend_exclude: bool = False
    exclusion_reason: str = ""
    script: str = ""
    summary: str = ""
    cultural_significance: int = 0
    accessibility: int = 0
    visitor_interest: int = 0
    uniqueness: int = 0


# -------------------------------------------------------------------
# Public result model
# -------------------------------------------------------------------


class TourGenerationResult(BaseModel):
    script: str
    summary: str
    overall_score: float
    scores_vector: Dict[str, Any]
    sources: List[str] = []
    recommend_exclude: bool = False
    exclusion_reason: str = ""


# -------------------------------------------------------------------
# Secret helper
# -------------------------------------------------------------------


@lru_cache(maxsize=1)
def _get_gemini_key() -> str:
    key = get_api_key_from_secret(GEMINI_API_KEY_SECRET_NAME, "GEMINI_API_KEY")
    if not key:
        raise ValueError(f"GEMINI_API_KEY not found in secret '{GEMINI_API_KEY_SECRET_NAME}'")
    return key


# -------------------------------------------------------------------
# Wikipedia tool
# -------------------------------------------------------------------

_WIKIPEDIA_SEARCH_URL = "https://en.wikipedia.org/w/api.php"


def fetch_wikipedia(search_term: str) -> dict:
    """Search Wikipedia and return the best-matching article extract.

    Args:
        search_term: The name or description of the location to look up.

    Returns:
        A dict with keys "title", "extract", "url", or "error" on failure.
    """
    try:
        search_resp = requests.get(
            _WIKIPEDIA_SEARCH_URL,
            params={
                "action": "query",
                "list": "search",
                "srsearch": search_term,
                "format": "json",
                "srlimit": 1,
            },
            timeout=10,
        )
        search_resp.raise_for_status()
        results = search_resp.json().get("query", {}).get("search", [])
        if not results:
            return {"error": f"No Wikipedia results for '{search_term}'"}

        pageid = results[0]["pageid"]

        extract_resp = requests.get(
            _WIKIPEDIA_SEARCH_URL,
            params={
                "action": "query",
                "prop": "extracts",
                "exintro": True,
                "pageids": pageid,
                "format": "json",
            },
            timeout=10,
        )
        extract_resp.raise_for_status()
        pages = extract_resp.json().get("query", {}).get("pages", {})
        page = pages.get(str(pageid), {})
        title = page.get("title", "")
        extract = page.get("extract", "")
        url = f"https://en.wikipedia.org/?curid={pageid}"

        if not extract:
            return {"error": f"Wikipedia page for '{search_term}' has no extract"}

        return {"title": title, "extract": extract, "url": url}

    except Exception as exc:
        logger.warning("fetch_wikipedia failed for '%s': %s", search_term, exc)
        return {"error": str(exc)}


# -------------------------------------------------------------------
# ADK Agents (module-level — survive warm Lambda invocations)
# -------------------------------------------------------------------

_wikipedia_agent = Agent(
    name="wikipedia_agent",
    model="gemini-2.0-flash",
    instruction=(
        "Look up '{poi_title}' on Wikipedia using the fetch_wikipedia tool. "
        "Return the full article extract. If nothing useful is found, say so clearly."
    ),
    tools=[fetch_wikipedia],
    output_key="wiki_research",
)

_web_search_agent = Agent(
    name="web_search_agent",
    model="gemini-2.0-flash",
    instruction=(
        "Search the web for '{poi_title}' located near coordinates ({poi_lat}, {poi_lng}). "
        "Find history, cultural significance, visitor highlights, accessibility details, "
        "and any unique or interesting facts. "
        "Supplement what Wikipedia already found:\n{wiki_research}"
    ),
    tools=[google_search],
    output_key="web_research",
)

_research_router = Agent(
    name="research_router",
    model="gemini-2.0-flash",
    instruction=(
        "Review the Wikipedia research for '{poi_title}':\n{wiki_research}\n\n"
        "If this provides sufficient detail for a rich audio tour (history, cultural "
        "significance, visitor highlights), respond with exactly 'Wikipedia sufficient' "
        "and stop.\n"
        "If the article is missing, very thin, or the POI needs more current information, "
        "transfer to web_search_agent."
    ),
    sub_agents=[_web_search_agent],
    output_key="web_research",
)

_generation_agent = Agent(
    name="generation_agent",
    model="gemini-2.0-flash",
    instruction=(
        "Write a {tour_style} audio tour for '{poi_title}' in language '{language}'.\n\n"
        "Wikipedia research:\n{wiki_research}\n\n"
        "Additional web research:\n{web_research}\n\n"
        "Script: 400–600 words. Summary: 1–2 sentences. Score each dimension 0–10.\n\n"
        "If this location has no notable characteristics worthy of an audio tour — completely "
        "generic, no history, no cultural significance, not interesting to visitors — set "
        "`recommend_exclude=True` and provide a brief `exclusion_reason`. Leave all other "
        "fields empty. Otherwise generate the full tour."
    ),
    output_schema=TourOutput,
    include_contents="none",
)

_tour_pipeline = SequentialAgent(
    name="tour_pipeline",
    sub_agents=[_wikipedia_agent, _research_router, _generation_agent],
)

# -------------------------------------------------------------------
# Runner (module-level — reused across warm Lambda invocations)
# -------------------------------------------------------------------

_session_service = InMemorySessionService()
_runner: Optional[Runner] = None


def _get_runner() -> Runner:
    """Lazily initialise the Runner (requires GEMINI_API_KEY at call time)."""
    global _runner
    if _runner is None:
        os.environ.setdefault("GOOGLE_API_KEY", _get_gemini_key())
        _runner = Runner(
            agent=_tour_pipeline,
            app_name="poi_tour_generator",
            session_service=_session_service,
        )
    return _runner


# -------------------------------------------------------------------
# Async execution
# -------------------------------------------------------------------


async def _run_async(poi_data: PoiInputData, config: GenerationConfig) -> str:
    runner = _get_runner()
    session_id = str(uuid.uuid4())

    await _session_service.create_session(
        app_name="poi_tour_generator",
        user_id="system",
        session_id=session_id,
        state={
            "poi_title": poi_data.title,
            "poi_lat": str(poi_data.lat),
            "poi_lng": str(poi_data.lng),
            "google_place_id": poi_data.source_ids.get("google", ""),
            "poi_summary": poi_data.summary or "",
            "tour_style": config.tour_style,
            "language": config.language,
        },
    )

    final_text = ""
    async for event in runner.run_async(
        user_id="system",
        session_id=session_id,
        new_message=genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=f"Generate a tour for: {poi_data.title}")],
        ),
    ):
        if event.is_final_response() and event.content:
            for part in event.content.parts or []:
                if part.text:
                    final_text += part.text

    return final_text


# -------------------------------------------------------------------
# Public entry point
# -------------------------------------------------------------------


def generate_tour(
    poi_data: PoiInputData,
    config: GenerationConfig,
) -> TourGenerationResult:
    """Run the ADK tour generation pipeline and return a TourGenerationResult.

    Raises ValueError if the pipeline produces no output.
    The caller should check TourGenerationResult fields; for excluded POIs the
    script/summary will be empty and overall_score will be 0.
    """
    final_text = asyncio.run(_run_async(poi_data, config))

    if not final_text:
        raise ValueError("ADK pipeline produced no output for POI: %s" % poi_data.title)

    output = TourOutput.model_validate_json(final_text)

    overall = (
        output.cultural_significance
        + output.accessibility
        + output.visitor_interest
        + output.uniqueness
    ) / 4.0

    return TourGenerationResult(
        script=output.script,
        summary=output.summary,
        overall_score=round(overall, 2),
        scores_vector={
            "cultural_significance": output.cultural_significance,
            "accessibility": output.accessibility,
            "visitor_interest": output.visitor_interest,
            "uniqueness": output.uniqueness,
        },
        recommend_exclude=output.recommend_exclude,
        exclusion_reason=output.exclusion_reason,
    )
