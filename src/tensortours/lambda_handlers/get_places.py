import json
import logging
from typing import Dict, List

from ..models.api import GetPlacesRequest, GetPlacesResponse
from ..models.tour import TourType, TourTypeToGooglePlaceTypes, TTPlaceInfo
from ..services.tour_table import GenerationStatus
from ..services.user_event_table import UserEventTableClient
from ..utils.general_utils import (
    get_generation_queue,
    get_google_places_client,
    get_tour_table_client,
    get_user_event_table_client,
)

logger = logging.getLogger(__name__)


def transform_google_places_to_tt_place_info(places_data: Dict) -> List[TTPlaceInfo]:
    """Transform Google Places API response to TTPlaceInfo objects.

    Args:
        places_data: Response data from Google Places API

    Returns:
        List of TTPlaceInfo objects
    """
    places = []

    for place in places_data.get("places", []):
        # Extract place information
        place_id = place.get("id", "")
        name = place.get("displayName", {}).get("text", "")

        # Extract location coordinates
        location = place.get("location", {})
        latitude = location.get("latitude", 0.0)
        longitude = location.get("longitude", 0.0)

        # Extract address
        address = place.get("formattedAddress", "")

        # Extract rating information
        place.get("rating", 0.0)
        place.get("userRatingCount", 0)

        # Extract place types
        types = place.get("types", [])
        primary_type = place.get("primaryType", "")

        # Extract editorial summary if available
        editorial_summary = ""
        if "editorialSummary" in place and place["editorialSummary"]:
            editorial_summary = place["editorialSummary"].get("text", "")

        # Create TTPlaceInfo object
        place_info = TTPlaceInfo(
            place_id=place_id,
            place_name=name,
            place_editorial_summary=editorial_summary,
            place_address=address,
            place_primary_type=primary_type,
            place_types=types,
            place_location={"latitude": latitude, "longitude": longitude},
        )

        places.append(place_info)

    return places


def forward_to_generation_queue(place_info: TTPlaceInfo, tour_type: TourType, user_id: str = None):
    """Forward a place to the generation queue if it doesn't exist in the tour table.

    Args:
        place_info: The place info object to forward
        tour_type: The tour type to generate
        user_id: Optional user ID to associate with the generation request
    """
    try:
        # Get the cached SQS queue resource
        queue = get_generation_queue()

        # Create a payload with place_id, tour_type, user_id, and place_info fields
        payload = {
            "place_id": place_info.place_id,
            "tour_type": tour_type.value,
            "user_id": user_id,
            # Store the serialized TTPlaceInfo data directly as a string in the place_info field
            "place_info": place_info.model_dump_json(),
        }

        # Convert the payload to a JSON string for the message body
        message_body = json.dumps(payload)
        queue.send_message(MessageBody=message_body)
        logger.info(f"Forwarded place {place_info.place_id} for {tour_type.value} tour generation")
    except ValueError as e:
        # This happens when the environment variable is not set
        logger.warning(f"Skipping generation queue: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to forward place {place_info.place_id} to generation queue: {str(e)}")


def handler(event, context):
    """Get places near a location based on latitude, longitude, and tour type."""
    # Merge the body with the event to include both request data and context
    body = event.get("body", {})
    if isinstance(body, str):
        # API Gateway might send the body as a JSON string
        body = json.loads(body)

    # Create a merged dict with both body fields and the original event
    # This allows the validator to see both the request fields and the context
    merged_event = {**body, "requestContext": event.get("requestContext", {})}

    # Validate the merged event
    request = GetPlacesRequest.model_validate(merged_event)
    user_event_table_client: UserEventTableClient = get_user_event_table_client()

    # Log the user's request to get places
    user_event_table_client.log_get_places_event(request)

    # Get Google Places client
    google_places_client = get_google_places_client()

    # Determine place types to include based on tour type using the enum mapping
    include_types = TourTypeToGooglePlaceTypes.get_place_types(request.tour_type)
    exclude_types = []

    try:
        # Search for places using Google Places API
        places_data = google_places_client.search_nearby(
            latitude=request.latitude,
            longitude=request.longitude,
            radius=request.radius,
            include_types=include_types,
            exclude_types=exclude_types,
            max_results=request.max_results,
        )

        # Transform Google Places data to TTPlaceInfo objects
        places = transform_google_places_to_tt_place_info(places_data)

        # Get the tour table client to check if places exist
        tour_table_client = get_tour_table_client()

        # Get user ID for the generation request if the user is authenticated
        user_id = None
        if request.user is not None:
            user_id = request.user.user_id

        # Check each place and forward to generation queue if it doesn't exist
        for place in places:
            # Check if the place exists in the tour table for this tour type
            tour_item = tour_table_client.get_item(place.place_id, request.tour_type)

            # If the place doesn't exist or is not completed, forward to generation queue
            if tour_item is None or tour_item.status != GenerationStatus.COMPLETED:
                forward_to_generation_queue(place, request.tour_type, user_id)

        # Create response
        response = GetPlacesResponse(
            places=places,
            total_count=len(places),
            is_authenticated=request.user is not None,
        )

        return {"statusCode": 200, "body": response.model_dump_json()}

    except Exception as e:
        logger.exception(f"Error getting places: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Failed to get places: {str(e)}"}),
        }
