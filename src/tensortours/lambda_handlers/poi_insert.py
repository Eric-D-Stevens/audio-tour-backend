"""Lambda handler for POST /poi — insert a new Point of Interest."""

import json
import logging

from ..models.poi import PoiInsertRequest, PoiInsertResponse
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


def handler(event, context):
    """Insert a new POI row with status='pending'."""
    body = event.get("body", {})
    if isinstance(body, str):
        body = json.loads(body)

    merged_event = {**body, "requestContext": event.get("requestContext", {})}
    request = PoiInsertRequest.model_validate(merged_event)

    user_id = request.user.user_id if request.user else None

    try:
        conn = get_connection(user_id=user_id)
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    _INSERT_SQL,
                    (
                        request.title,
                        request.summary,
                        request.lng,  # ST_MakePoint(x, y) = (lng, lat)
                        request.lat,
                        json.dumps(request.source_ids),
                        json.dumps(request.location_meta) if request.location_meta is not None else None,
                        request.overall_score,
                        json.dumps(request.scores_vector),
                        json.dumps(request.photo_urls),
                        json.dumps(request.scripts),
                        json.dumps(request.audio_urls),
                    ),
                )
                row = cur.fetchone()
        conn.close()

        response = PoiInsertResponse(id=str(row[0]))
        return {"statusCode": 201, "body": response.model_dump_json()}

    except Exception as e:
        logger.exception(f"Error inserting POI: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to insert POI"}),
        }
