import json
import logging
from typing import Optional

from ..models.api import GetPregeneratedTourRequest, GetPregeneratedTourResponse
from ..models.tour import TTour
from ..services.tour_table import TourTableClient, TourTableItem
from ..services.user_event_table import UserEventTableClient
from ..utils.general_utils import get_tour_table_client, get_user_event_table_client

logger = logging.getLogger(__name__)


def handler(event, context):
    """Get a tour item by place_id and tour_type."""
    # Merge the body with the event to include both request data and context
    body = event.get("body", {})
    if isinstance(body, str):
        # API Gateway might send the body as a JSON string
        body = json.loads(body)

    # Create a merged dict with both body fields and the original event
    # This allows the validator to see both the request fields and the context
    merged_event = {**body, "requestContext": event.get("requestContext", {})}

    # Validate the merged event
    request = GetPregeneratedTourRequest.model_validate(merged_event)
    tour_table_client: TourTableClient = get_tour_table_client()
    user_event_table_client: UserEventTableClient = get_user_event_table_client()

    # Log the user's request to get a tour
    user_event_table_client.log_get_tour_event(request)

    tour_item: Optional[TourTableItem] = tour_table_client.get_item(
        request.place_id, request.tour_type
    )
    if tour_item is None:
        return {
            "statusCode": 404, 
            "body": json.dumps({"error": "Tour not found"}),
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"  # For CORS support
            }
        }

    tour = TTour(
        place_id=tour_item.place_id,
        tour_type=tour_item.tour_type,
        place_info=tour_item.place_info,
        photos=tour_item.photos,
        script=tour_item.script,
        audio=tour_item.audio,
    )
    tour_response = GetPregeneratedTourResponse(tour=tour)
    return {"statusCode": 200, "body": tour_response.model_dump_json()}
