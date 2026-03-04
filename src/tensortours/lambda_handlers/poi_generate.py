"""Lambda handler for POST /poi/generate — full POI tour generation pipeline."""

import json
import logging

from ..models.generation import PoiGenerateRequest, PoiGenerateResponse
from ..services.generation.deduplication import deduplicate
from ..services.generation.metadata_finalizer import finalize
from ..services.generation.tour_agent import generate_tour
from ..services.supabase_client import get_connection

logger = logging.getLogger(__name__)

_INSERT_SQL = """
INSERT INTO poi (
    title, summary, location,
    source_ids, location_meta,
    overall_score, scores_vector,
    photo_urls, scripts, audio_urls,
    status
)
VALUES (
    %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326),
    %s::jsonb, %s::jsonb,
    %s, %s::jsonb,
    %s::jsonb, %s::jsonb, %s::jsonb,
    'pending'
)
RETURNING id
"""

_INSERT_EXCLUDED_SQL = """
INSERT INTO poi (
    title, location,
    source_ids, location_meta,
    status
)
VALUES (
    %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326),
    %s::jsonb, %s::jsonb,
    'excluded'
)
RETURNING id
"""

_UPDATE_SQL = """
UPDATE poi
SET
    title          = %s,
    summary        = %s,
    overall_score  = %s,
    scores_vector  = %s::jsonb,
    scripts        = scripts || %s::jsonb,
    status         = 'pending'
WHERE id = %s
RETURNING id
"""


def handler(event, context):
    """Orchestrate the four-stage POI generation pipeline."""
    body = event.get("body", {})
    if isinstance(body, str):
        body = json.loads(body)

    merged_event = {**body, "requestContext": event.get("requestContext", {})}

    try:
        request = PoiGenerateRequest.model_validate(merged_event)
    except Exception as exc:
        logger.warning("Invalid request: %s", exc)
        return {"statusCode": 400, "body": json.dumps({"error": str(exc)})}

    user_id = request.user.user_id if request.user else None

    try:
        conn = get_connection(user_id=user_id)

        # ------------------------------------------------------------------
        # Stage 1: Deduplication
        # ------------------------------------------------------------------
        dedup = deduplicate(conn, request.poi_data)

        if dedup.existing_poi_id and not request.generation_config.force_regenerate:
            # Fast path: POI already exists, skip generation
            conn.close()
            return {
                "statusCode": 200,
                "body": PoiGenerateResponse(
                    poi_id=dedup.existing_poi_id,
                    status=dedup.existing_poi_status or "pending",
                    was_duplicate=True,
                    canonical_id=dedup.canonical_id,
                ).model_dump_json(),
            }

        # ------------------------------------------------------------------
        # Stage 2: Tour generation (Gemini agent)
        # ------------------------------------------------------------------
        generation_result = generate_tour(request.poi_data, request.generation_config)

        # ------------------------------------------------------------------
        # Excluded path: generation agent determined this POI is not tour-worthy
        # ------------------------------------------------------------------
        if generation_result.recommend_exclude:
            logger.info(
                "POI excluded by generation agent: %s — %s",
                request.poi_data.title,
                generation_result.exclusion_reason,
            )
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        _INSERT_EXCLUDED_SQL,
                        (
                            request.poi_data.title,
                            request.poi_data.lng,
                            request.poi_data.lat,
                            json.dumps(request.poi_data.source_ids),
                            json.dumps(request.poi_data.location_meta)
                            if request.poi_data.location_meta is not None
                            else None,
                        ),
                    )
                    row = cur.fetchone()
                    poi_id = str(row[0])
            conn.close()
            return {
                "statusCode": 201,
                "body": PoiGenerateResponse(
                    poi_id=poi_id,
                    status="excluded",
                    was_duplicate=False,
                    canonical_id=None,
                ).model_dump_json(),
            }

        # ------------------------------------------------------------------
        # Stage 3: Metadata finalization
        # ------------------------------------------------------------------
        insert_payload = finalize(request.poi_data, generation_result, request.generation_config)

        # ------------------------------------------------------------------
        # Stage 4: DB upload — UPDATE existing or INSERT new
        # ------------------------------------------------------------------
        with conn:
            with conn.cursor() as cur:
                if dedup.existing_poi_id:
                    cur.execute(
                        _UPDATE_SQL,
                        (
                            insert_payload.title,
                            insert_payload.summary,
                            insert_payload.overall_score,
                            json.dumps(insert_payload.scores_vector),
                            json.dumps(insert_payload.scripts),
                            dedup.existing_poi_id,
                        ),
                    )
                    row = cur.fetchone()
                    poi_id = str(row[0]) if row else dedup.existing_poi_id
                else:
                    cur.execute(
                        _INSERT_SQL,
                        (
                            insert_payload.title,
                            insert_payload.summary,
                            insert_payload.lng,  # ST_MakePoint(x, y) = (lng, lat)
                            insert_payload.lat,
                            json.dumps(insert_payload.source_ids),
                            json.dumps(insert_payload.location_meta)
                            if insert_payload.location_meta is not None
                            else None,
                            insert_payload.overall_score,
                            json.dumps(insert_payload.scores_vector),
                            json.dumps(insert_payload.photo_urls),
                            json.dumps(insert_payload.scripts),
                            json.dumps(insert_payload.audio_urls),
                        ),
                    )
                    row = cur.fetchone()
                    poi_id = str(row[0])

        conn.close()

        return {
            "statusCode": 201,
            "body": PoiGenerateResponse(
                poi_id=poi_id,
                status="pending",
                was_duplicate=bool(dedup.existing_poi_id),
                canonical_id=dedup.canonical_id,
            ).model_dump_json(),
        }

    except Exception as exc:
        logger.exception("POI generation pipeline failed: %s", exc)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "POI generation failed"}),
        }
