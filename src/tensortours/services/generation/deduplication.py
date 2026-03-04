"""Stage 1: POI deduplication — hard source_id match, geo proximity, LLM tie-break."""

import json
import logging
import os
from functools import lru_cache
from typing import Optional

import psycopg2.extensions
from google import genai  # type: ignore[import]
from google.genai import types as genai_types  # type: ignore[import]
from pydantic import BaseModel

from ...models.generation import PoiInputData
from ...utils.aws import get_api_key_from_secret

logger = logging.getLogger(__name__)

GEMINI_API_KEY_SECRET_NAME = os.environ.get("GEMINI_API_KEY_SECRET_NAME", "gemini-api-key")

# -------------------------------------------------------------------
# SQL helpers
# -------------------------------------------------------------------

_HARD_LOOKUP_SQL = """
SELECT id::text, status
FROM poi
WHERE source_ids @> %s::jsonb
LIMIT 1
"""

_GEO_LOOKUP_SQL = """
SELECT id::text, title, summary, status
FROM poi
WHERE ST_DWithin(
    location,
    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
    50
)
LIMIT 5
"""

# -------------------------------------------------------------------
# Models
# -------------------------------------------------------------------


class _DedupDecision(BaseModel):
    is_same_place: bool


class DeduplicationResult(BaseModel):
    existing_poi_id: Optional[str] = None
    existing_poi_status: Optional[str] = None
    canonical_id: Optional[str] = None
    was_hard_match: bool = False
    was_geo_match: bool = False


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


@lru_cache(maxsize=1)
def _get_gemini_key() -> str:
    key = get_api_key_from_secret(GEMINI_API_KEY_SECRET_NAME, "GEMINI_API_KEY")
    if not key:
        raise ValueError(f"GEMINI_API_KEY not found in secret '{GEMINI_API_KEY_SECRET_NAME}'")
    return key


def _llm_same_place(
    title_new: str,
    title_existing: str,
    summary_existing: Optional[str],
) -> bool:
    """Ask Gemini (no tools, no search) whether two place names are the same location.

    Uses structured output (response_schema) to guarantee a boolean response.
    """
    try:
        client = genai.Client(api_key=_get_gemini_key())

        existing_desc = f'"{title_existing}"'
        if summary_existing:
            existing_desc += f" — {summary_existing}"

        prompt = (
            f'Are these two entries the same physical location?\n'
            f'Place A: "{title_new}"\n'
            f"Place B: {existing_desc}"
        )

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_DedupDecision,
            ),
        )
        decision = _DedupDecision.model_validate_json(response.text)
        return decision.is_same_place
    except Exception:
        logger.exception("LLM dedup call failed; treating as no-match")
        return False


# -------------------------------------------------------------------
# Public entry point
# -------------------------------------------------------------------


def deduplicate(
    conn: psycopg2.extensions.connection,
    poi_data: PoiInputData,
) -> DeduplicationResult:
    """Run all three dedup passes and return a DeduplicationResult.

    Pass 1 — hard lookup: exact source_ids GIN match.
    Pass 2 — geo query: ST_DWithin 50 m radius.
    Pass 3 — LLM tie-break: Gemini structured YES/NO for ambiguous geo hits.
    """
    # ------------------------------------------------------------------
    # Pass 1: hard source_id match
    # ------------------------------------------------------------------
    if poi_data.source_ids:
        with conn.cursor() as cur:
            cur.execute(_HARD_LOOKUP_SQL, (json.dumps(poi_data.source_ids),))
            row = cur.fetchone()
        if row:
            logger.info("Dedup hard match: poi_id=%s status=%s", row[0], row[1])
            return DeduplicationResult(
                existing_poi_id=row[0],
                existing_poi_status=row[1],
                canonical_id=row[0],
                was_hard_match=True,
            )

    # ------------------------------------------------------------------
    # Pass 2: geo proximity
    # ------------------------------------------------------------------
    with conn.cursor() as cur:
        cur.execute(_GEO_LOOKUP_SQL, (poi_data.lng, poi_data.lat))
        nearby = cur.fetchall()

    if not nearby:
        return DeduplicationResult()

    # ------------------------------------------------------------------
    # Pass 3: LLM tie-break for each nearby candidate
    # ------------------------------------------------------------------
    for row in nearby:
        poi_id, existing_title, existing_summary, poi_status = row[0], row[1], row[2], row[3]
        if _llm_same_place(poi_data.title, existing_title, existing_summary):
            logger.info("Dedup geo+LLM match: poi_id=%s", poi_id)
            return DeduplicationResult(
                existing_poi_id=poi_id,
                existing_poi_status=poi_status,
                canonical_id=poi_id,
                was_geo_match=True,
            )

    return DeduplicationResult()
