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
        logger.info(f"Attempting to fetch preview places from S3: {s3_key}")
        
        # Get the file from S3
        response = s3_client.get_object(Bucket=CONTENT_BUCKET, Key=s3_key)
        json_content = response["Body"].read().decode("utf-8")
        data = json.loads(json_content)
        
        # Extract place_ids from the places array
        places_array = data.get("places", [])
        place_ids = {place["place_id"] for place in places_array}
        logger.info(f"Loaded {len(place_ids)} preview place_ids for {city}/{tour_type}")
        
        # Log a sample of place IDs for debugging
        if place_ids:
            sample = list(place_ids)[:3]
            logger.info(f"Sample place_ids from {city}/{tour_type}: {sample}")
        else:
            logger.warning(f"No place_ids found in {s3_key} - places array length: {len(places_array)}")
            
        return place_ids
    except s3_client.exceptions.NoSuchKey:
        logger.error(f"S3 file not found: s3://{CONTENT_BUCKET}/{s3_key}")
        return set()
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
    logger.info(f"Checking if place_id '{place_id}' exists in preview dataset for tour type '{tour_type}'")
    all_preview_ids = get_all_preview_place_ids()
    tour_type_ids = all_preview_ids.get(tour_type, set())
    logger.info(f"Found {len(tour_type_ids)} total preview place_ids for tour type '{tour_type}'")
    
    result = place_id in tour_type_ids
    if result:
        logger.info(f"place_id '{place_id}' IS in the preview dataset for tour type '{tour_type}'")
    else:
        logger.warning(f"place_id '{place_id}' is NOT in the preview dataset for tour type '{tour_type}'")
    
    return result


def handler(event, context):
    """Get a preview tour by place_id and tour_type, validating it's in the preview dataset."""
    logger.info(f"Received get_preview request: {event}")
    
    # Merge the body with the event to include both request data and context
    body = event.get("body", {})
    if isinstance(body, str):
        # API Gateway might send the body as a JSON string
        logger.info("Converting JSON string body to dict")
        body = json.loads(body)

    # Create a merged dict with both body fields and the original event
    # This allows the validator to see both the request fields and the context
    merged_event = {**body, "requestContext": event.get("requestContext", {})}
    logger.info(f"Merged event for validation: {merged_event}")

    # Validate the merged event
    try:
        request = GetPreviewRequest.model_validate(merged_event)
        logger.info(f"Validated request: place_id={request.place_id}, tour_type={request.tour_type.value}")
    except Exception as e:
        logger.error(f"Request validation failed: {str(e)}")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid request", "message": str(e)}),
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}
        }
        
    tour_table_client: TourTableClient = get_tour_table_client()
    user_event_table_client: UserEventTableClient = get_user_event_table_client()

    # Log the user's request to get a preview tour
    try:
        user_event_table_client.log_get_tour_event(request)
        logger.info("User event logged successfully")
    except Exception as e:
        logger.error(f"Failed to log user event: {str(e)}")
    
    # Check if the place_id is part of our preview dataset
    place_id = request.place_id
    tour_type_value = request.tour_type.value
    
    if not is_preview_place_id(place_id, tour_type_value):
        logger.warning(f"404 ERROR: place_id '{place_id}' not in preview dataset for '{tour_type_value}'")
        
        # List some valid IDs that could be used instead
        all_preview_ids = get_all_preview_place_ids()
        valid_ids = list(all_preview_ids.get(tour_type_value, set()))[:5]
        if valid_ids:
            logger.info(f"Some valid place_ids for '{tour_type_value}': {valid_ids}")
        
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
    logger.info(f"Fetching tour from DynamoDB: place_id={place_id}, tour_type={tour_type_value}")
    tour_item: Optional[TourTableItem] = tour_table_client.get_item(
        request.place_id, request.tour_type
    )
    
    if tour_item is None:
        logger.warning(f"404 ERROR: Tour not found in DynamoDB for place_id '{place_id}', tour_type '{tour_type_value}'")
        
        # This is a potential inconsistency if the place is in preview data but not in DynamoDB
        if is_preview_place_id(place_id, tour_type_value):
            logger.error(f"INCONSISTENCY DETECTED: place_id '{place_id}' is in preview dataset but missing from DynamoDB")
        
        return {
            "statusCode": 404, 
            "body": json.dumps({"error": "Tour not found"}),
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"  # For CORS support
            }
        }
        
    # Check if the tour item is incomplete (script or audio missing)
    logger.info(f"Checking if tour for place_id '{place_id}' is complete")
    
    if tour_item.script is None or tour_item.audio is None:
        missing_parts = []
        if tour_item.script is None:
            missing_parts.append("script")
            logger.info(f"Tour for place_id '{place_id}' is missing script")
            
        if tour_item.audio is None:
            missing_parts.append("audio")
            logger.info(f"Tour for place_id '{place_id}' is missing audio")
        
        missing_parts_str = ', '.join(missing_parts)
        logger.warning(f"404 ERROR: Incomplete tour for place_id '{place_id}'. Missing: {missing_parts_str}")
        
        # Log when the tour was created to help debug potential stuck tours
        if hasattr(tour_item, 'created_at'):
            logger.info(f"Tour was created at: {tour_item.created_at}")
            
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
    logger.info(f"Tour for place_id '{place_id}' is complete, preparing response")
    
    tour_data = {
        "place_id": tour_item.place_id,
        "tour_type": tour_item.tour_type,
        "place_info": tour_item.place_info,
        "photos": tour_item.photos
    }
    
    # Log some basic info about the tour content
    photo_count = len(tour_item.photos) if tour_item.photos else 0
    logger.info(f"Tour has {photo_count} photos")
    
    # Only add script and audio if they exist to prevent validation errors
    if tour_item.script is not None:
        tour_data["script"] = tour_item.script
        script_length = len(tour_item.script) if tour_item.script else 0
        logger.info(f"Tour script length: {script_length} characters")
        
    if tour_item.audio is not None:
        tour_data["audio"] = tour_item.audio
        logger.info(f"Tour has audio URL: {tour_item.audio}")
    
    try:
        tour = TTour(**tour_data)
        tour_response = GetPreviewResponse(
            tour=tour,
            is_authenticated=request.user is not None
        )
        
        logger.info(f"Successfully created tour response for place_id '{place_id}'")
        
        return {
            "statusCode": 200, 
            "body": tour_response.model_dump_json(),
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"  # For CORS support
            }
        }
    except Exception as e:
        logger.error(f"Failed to create tour response: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error", "message": "Failed to generate tour response"}),
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            }
        }
