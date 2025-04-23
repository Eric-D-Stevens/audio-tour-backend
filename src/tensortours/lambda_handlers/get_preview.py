"""Preview tour handler for TensorTours backend.

This handler validates that a requested place_id exists in our preview dataset
before retrieving the tour data, ensuring only approved preview content is accessible.
"""

import json
import logging
import boto3
import os
from functools import lru_cache
from typing import Dict, List, Optional, Set, Tuple

from ..models.api import GetPreviewRequest, GetPreviewResponse
from ..models.tour import TourType, TTour
from ..services.tour_table import TourTableClient, TourTableItem
from ..services.user_event_table import UserEventTableClient
from ..utils.general_utils import get_tour_table_client, get_user_event_table_client

logger = logging.getLogger(__name__)

# Constants
PREVIEW_PATH_PREFIX = "preview"
CONTENT_BUCKET = os.environ.get("CONTENT_BUCKET", "tensortours-content-us-west-2")
PREVIEW_CITIES = ["san-francisco", "new-york", "london", "paris", "tokyo", "rome", "giza"]
PREVIEW_TOUR_TYPES = [tour_type.value for tour_type in TourType]

# Initialize S3 client
s3_client = boto3.client("s3")


@lru_cache(maxsize=32)
def get_preview_place_ids(city: str, tour_type: str) -> Set[str]:
    """
    Get a set of place_ids that are available in the preview dataset for a specific city and tour type.
    
    Uses LRU cache to minimize S3 requests.
    
    Args:
        city: The city name
        tour_type: The tour type
        
    Returns:
        Set of place_ids
    """
    try:
        # Construct the S3 key for the places.json file
        s3_key = f"{PREVIEW_PATH_PREFIX}/{city}/{tour_type}/places.json"
        
        # Get the file from S3
        response = s3_client.get_object(Bucket=CONTENT_BUCKET, Key=s3_key)
        json_content = response["Body"].read().decode("utf-8")
        data = json.loads(json_content)
        
        # Extract place_ids from the places array
        place_ids = {place["place_id"] for place in data.get("places", [])}
        logger.info(f"Loaded {len(place_ids)} preview place_ids for {city}/{tour_type}")
        return place_ids
    except Exception as e:
        logger.error(f"Error loading preview place_ids for {city}/{tour_type}: {str(e)}")
        return set()


@lru_cache(maxsize=32)
def get_all_preview_place_ids() -> Dict[str, Set[str]]:
    """
    Get all place_ids organized by tour type from all available preview cities.
    
    Returns:
        Dictionary mapping tour_type to sets of place_ids
    """
    result = {tour_type: set() for tour_type in PREVIEW_TOUR_TYPES}
    
    for city in PREVIEW_CITIES:
        for tour_type in PREVIEW_TOUR_TYPES:
            place_ids = get_preview_place_ids(city, tour_type)
            result[tour_type].update(place_ids)
            
    return result


def is_preview_place_id(place_id: str, tour_type: str) -> bool:
    """
    Check if a place_id is part of the preview dataset for a specific tour type.
    
    Args:
        place_id: The place ID to check
        tour_type: The tour type
        
    Returns:
        True if it's a preview place_id, False otherwise
    """
    all_preview_ids = get_all_preview_place_ids()
    return place_id in all_preview_ids.get(tour_type, set())


def handler(event, context):
    """Get a preview tour by place_id and tour_type, validating it's in the preview dataset."""
    # Merge the body with the event to include both request data and context
    body = event.get("body", {})
    if isinstance(body, str):
        # API Gateway might send the body as a JSON string
        body = json.loads(body)

    # Create a merged dict with both body fields and the original event
    # This allows the validator to see both the request fields and the context
    merged_event = {**body, "requestContext": event.get("requestContext", {})}

    # Validate the merged event
    request = GetPreviewRequest.model_validate(merged_event)
    tour_table_client: TourTableClient = get_tour_table_client()
    user_event_table_client: UserEventTableClient = get_user_event_table_client()

    # Log the user's request to get a preview tour
    user_event_table_client.log_get_tour_event(request)
    
    # Check if the place_id is part of our preview dataset
    if not is_preview_place_id(request.place_id, request.tour_type.value):
        return {
            "statusCode": 404,
            "body": json.dumps({
                "error": "Preview not available",
                "message": f"The requested place_id is not available in the preview dataset for {request.tour_type.value} tours."
            }),
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"  # For CORS support
            }
        }

    # Get the tour from the tour table
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
        
    # Check if the tour item is incomplete (script or audio missing)
    if tour_item.script is None or tour_item.audio is None:
        missing_parts = []
        if tour_item.script is None:
            missing_parts.append("script")
        if tour_item.audio is None:
            missing_parts.append("audio")
            
        return {
            "statusCode": 404,
            "body": json.dumps({
                "error": "Incomplete tour", 
                "message": f"Tour found but missing: {', '.join(missing_parts)}. The tour may still be generating."
            }),
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            }
        }

    # Create TTour object with null checks to prevent validation errors
    tour_data = {
        "place_id": tour_item.place_id,
        "tour_type": tour_item.tour_type,
        "place_info": tour_item.place_info,
        "photos": tour_item.photos
    }
    
    # Only add script and audio if they exist to prevent validation errors
    if tour_item.script is not None:
        tour_data["script"] = tour_item.script
    if tour_item.audio is not None:
        tour_data["audio"] = tour_item.audio
    
    tour = TTour(**tour_data)
    tour_response = GetPreviewResponse(
        tour=tour,
        is_authenticated=request.user is not None
    )
    
    return {
        "statusCode": 200, 
        "body": tour_response.model_dump_json(),
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"  # For CORS support
        }
    }
