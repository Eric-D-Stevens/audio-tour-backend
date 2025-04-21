import json
import logging
from typing import Dict, List

from ..models.api import GetPlacesRequest, GetPlacesResponse
from ..models.tour import TTPlaceInfo, TourTypeToGooglePlaceTypes
from ..services.user_event_table import UserEventTableClient
from ..utils.general_utils import get_google_places_client, get_user_event_table_client

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
