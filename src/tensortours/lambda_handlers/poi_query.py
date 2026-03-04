"""Lambda handler for GET /poi — search for nearby ready Points of Interest."""

import json
import logging
from typing import List

from ..models.poi import PoiQueryRequest, PoiQueryResponse, PoiRecord
from ..services.supabase_client import get_connection

logger = logging.getLogger(__name__)

_QUERY_SQL = """
SELECT
    id::text, title, summary,
    ST_Y(location::geometry) AS lat,
    ST_X(location::geometry) AS lng,
    overall_score, status,
    scores_vector, audio_urls, photo_urls, scripts, location_meta
FROM poi
WHERE status = 'ready'
  AND ST_DWithin(
        location,
        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
        %s
      )
ORDER BY location <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
LIMIT %s
"""


def _parse_params(event: dict) -> PoiQueryRequest:
    params = event.get("queryStringParameters") or {}
    body = {
        "lat": float(params["lat"]),
        "lng": float(params["lng"]),
        "radius_meters": float(params.get("radius_meters", 5000.0)),
        "limit": int(params.get("limit", 50)),
        "requestContext": event.get("requestContext", {}),
    }
    return PoiQueryRequest.model_validate(body)


def _row_to_record(row) -> PoiRecord:
    return PoiRecord(
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
    )


def handler(event, context):
    """Return ready POIs within radius_meters of the given lat/lng."""
    try:
        request = _parse_params(event)
    except (KeyError, ValueError) as e:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"Invalid query parameters: {e}"}),
        }

    user_id = request.user.user_id if request.user else None

    try:
        conn = get_connection(user_id=user_id)
        with conn.cursor() as cur:
            cur.execute(
                _QUERY_SQL,
                (
                    request.lng, request.lat,   # ST_MakePoint center
                    request.radius_meters,
                    request.lng, request.lat,   # ST_MakePoint for ORDER BY
                    request.limit,
                ),
            )
            rows = cur.fetchall()
        conn.close()

        pois: List[PoiRecord] = [_row_to_record(r) for r in rows]
        response = PoiQueryResponse(pois=pois, total=len(pois))
        return {"statusCode": 200, "body": response.model_dump_json()}

    except Exception as e:
        logger.exception(f"Error querying POIs: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to query POIs"}),
        }
