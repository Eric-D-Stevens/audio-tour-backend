"""Lambda handler for GET /poi/{id} — fetch a single POI by ID."""

import json
import logging

from ..models.poi import PoiRecord
from ..services.supabase_client import get_connection

logger = logging.getLogger(__name__)

_GET_SQL = """
SELECT
    id::text, title, summary,
    ST_Y(location::geometry) AS lat,
    ST_X(location::geometry) AS lng,
    overall_score, status,
    scores_vector, audio_urls, photo_urls, scripts, location_meta,
    generation_error
FROM poi
WHERE id = %s::uuid
"""


def handler(event, context):
    """Return a single POI at any lifecycle status (pending/processing/ready/failed).

    Used by clients polling for on-demand generation completion.
    """
    poi_id = (event.get("pathParameters") or {}).get("id")
    if not poi_id:
        return {"statusCode": 400, "body": json.dumps({"error": "Missing path parameter: id"})}

    request_context = event.get("requestContext", {})
    user_id = None
    if request_context.get("authorizer", {}).get("claims", {}).get("sub"):
        user_id = request_context["authorizer"]["claims"]["sub"]

    try:
        conn = get_connection(user_id=user_id)
        with conn.cursor() as cur:
            cur.execute(_GET_SQL, (poi_id,))
            row = cur.fetchone()
        conn.close()

        if row is None:
            return {"statusCode": 404, "body": json.dumps({"error": "POI not found"})}

        record = PoiRecord(
            id=row[0],
            title=row[1],
            summary=row[2],
            lat=row[3],
            lng=row[4],
            overall_score=row[5],
            status=row[6],
            scores_vector=row[7] or {},
            audio_urls=row[8] or {},
            photo_urls=row[9] or {},
            scripts=row[10] or {},
            location_meta=row[11],
            generation_error=row[12],
        )
        return {"statusCode": 200, "body": record.model_dump_json()}

    except Exception as e:
        logger.exception(f"Error fetching POI {poi_id}: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to fetch POI"}),
        }
