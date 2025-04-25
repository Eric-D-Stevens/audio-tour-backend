"""
Preview Data Generator for TensorTours

This script generates preview data for predefined cities in the same format as the get_places handler,
allowing for consistent preview data across environments. It offers options to:
1. Generate place data for each city and tour type combination
2. Publish place data to the generation queue (like get_places does)
3. Save the data to the content bucket under a /preview path for easy retrieval
"""

import argparse
import boto3
import concurrent.futures
import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add the project root to the path so we can import modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, project_root)

# City coordinates for preview mode
CITY_COORDINATES = {
    "san-francisco": {"lat": 37.7749, "lng": -122.4194},
    "new-york": {"lat": 40.7128, "lng": -74.0060},
    "london": {"lat": 51.5074, "lng": -0.1278},
    "paris": {"lat": 48.8566, "lng": 2.3522},
    "tokyo": {"lat": 35.6762, "lng": 139.6503},
    "rome": {"lat": 41.9028, "lng": 12.4964},
    "giza": {"lat": 29.9773, "lng": 31.1325},
}

from tensortours.models.api import GetPlacesRequest, GetPlacesResponse
from tensortours.models.tour import TourType, TourTypeToGooglePlaceTypes, TTPlaceInfo
from tensortours.services.tour_table import GenerationStatus
from tensortours.services.google_places import GooglePlacesClient
from tensortours.utils.general_utils import (
    get_generation_queue,
    get_google_places_client,
    get_tour_table_client,
)
from tensortours.utils.aws import upload_to_s3

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Constants
PREVIEW_PATH_PREFIX = "preview"
DEFAULT_RADIUS = 5000  # 5km radius
DEFAULT_MAX_RESULTS = 20  # Google Places API limit is 20
CONTENT_BUCKET = "tensortours-content-us-west-2"
CLOUDFRONT_DOMAIN = os.environ.get("CLOUDFRONT_DOMAIN")

# Read Google Maps API key from environment variable
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")
if not GOOGLE_MAPS_API_KEY:
    logger.warning("GOOGLE_MAPS_API_KEY environment variable not set")


def get_local_google_places_client() -> GooglePlacesClient:
    """Get a Google Places client instance using the API key from environment variables.
    
    Returns:
        GooglePlacesClient instance
    """
    if not GOOGLE_MAPS_API_KEY:
        raise ValueError("GOOGLE_MAPS_API_KEY environment variable not set")
        
    # Create and return the client with the API key
    client = GooglePlacesClient(GOOGLE_MAPS_API_KEY)
    return client


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
        # Hard-coded queue URL instead of using environment variable
        photo_queue_url = "https://sqs.us-west-2.amazonaws.com/934308926622/TTGenerationPhotoQueue"
        
        # Use the resource API
        sqs = boto3.resource("sqs")
        queue = sqs.Queue(photo_queue_url)

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
        logger.info(f"Forwarded place {place_info.place_id} for {tour_type.value} tour generation to photo queue")
    except Exception as e:
        logger.error(f"Failed to forward place {place_info.place_id} to generation queue: {str(e)}")


def get_places_for_location(
    city_name: str, 
    coordinates: Dict[str, float], 
    tour_type: TourType, 
    radius: int = DEFAULT_RADIUS, 
    max_results: int = DEFAULT_MAX_RESULTS
) -> List[TTPlaceInfo]:
    """
    Get places for a specific city and tour type.
    
    Args:
        city_name: Name of the city
        coordinates: Dictionary with lat and lng keys
        tour_type: Type of tour to search for
        radius: Radius in meters
        max_results: Maximum number of results to return
        
    Returns:
        List of TTPlaceInfo objects
    """
    logger.info(f"Getting places for {city_name}, tour type: {tour_type.value}")
    
    # Get Google Places client using the local function that uses env vars
    google_places_client = get_local_google_places_client()

    # Determine place types to include based on tour type using the enum mapping
    include_types = TourTypeToGooglePlaceTypes.get_place_types(tour_type)
    exclude_types = []

    try:
        # Search for places using Google Places API
        places_data = google_places_client.search_nearby(
            latitude=coordinates["lat"],
            longitude=coordinates["lng"],
            radius=radius,
            include_types=include_types,
            exclude_types=exclude_types,
            max_results=max_results,
        )

        # Transform Google Places data to TTPlaceInfo objects
        places = transform_google_places_to_tt_place_info(places_data)
        logger.info(f"Found {len(places)} places for {city_name}, tour type: {tour_type.value}")
        return places
    except Exception as e:
        logger.error(f"Error getting places for {city_name}, tour type {tour_type.value}: {str(e)}")
        return []


def save_to_local_file(city_name: str, tour_type: TourType, places: List[TTPlaceInfo]) -> bool:
    """
    Save the places data to a local file in the preview path (dry-run mode).
    
    Args:
        city_name: Name of the city
        tour_type: Type of tour
        places: List of TTPlaceInfo objects
        
    Returns:
        Boolean indicating success
    """
    try:
        # Convert places to JSON
        response = GetPlacesResponse(
            places=places,
            total_count=len(places),
            is_authenticated=False,
        )
        
        # Create directory structure if it doesn't exist
        output_dir = f"preview_data/{city_name}/{tour_type.value}"
        os.makedirs(output_dir, exist_ok=True)
        
        # Define local file path
        file_path = f"{output_dir}/places.json"
        
        # Write indented JSON to file
        with open(file_path, "w") as f:
            f.write(response.model_dump_json(indent=2))
        
        logger.info(f"Saved preview data for {city_name}, tour type: {tour_type.value} to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Error saving preview data for {city_name}, tour type {tour_type.value}: {str(e)}")
        return False


def save_to_content_bucket(city_name: str, tour_type: TourType, places: List[TTPlaceInfo]) -> bool:
    """
    Save the places data to the content bucket under the preview path.
    
    Args:
        city_name: Name of the city
        tour_type: Type of tour
        places: List of TTPlaceInfo objects
        
    Returns:
        Boolean indicating success
    """
    if not CONTENT_BUCKET:
        logger.error("CONTENT_BUCKET environment variable not set")
        return False
        
    try:
        # Convert places to JSON
        response = GetPlacesResponse(
            places=places,
            total_count=len(places),
            is_authenticated=False,
        )
        
        # Define key in the content bucket
        key = f"{PREVIEW_PATH_PREFIX}/{city_name}/{tour_type.value}/places.json"
        
        # Upload indented JSON to S3
        upload_to_s3(
            bucket_name=CONTENT_BUCKET,
            key=key,
            data=response.model_dump_json(indent=2),
            content_type="application/json"
        )
        
        # Create CloudFront URL if available
        if CLOUDFRONT_DOMAIN:
            cloudfront_url = f"https://{CLOUDFRONT_DOMAIN}/{key}"
            logger.info(f"Preview data available at: {cloudfront_url}")
        
        logger.info(f"Saved preview data for {city_name}, tour type: {tour_type.value} to s3://{CONTENT_BUCKET}/{key}")
        return True
    except Exception as e:
        logger.error(f"Error saving preview data for {city_name}, tour type {tour_type.value}: {str(e)}")
        return False


def process_city_tour_type(city_name: str, coordinates: Dict[str, float], tour_type: TourType, 
                         publish_to_queue: bool = False, save_to_bucket: bool = True, dry_run: bool = False,
                         items_per_second: float = 1.0) -> Dict:
    """
    Process a city and tour type combination.
    
    Args:
        city_name: Name of the city
        coordinates: Dictionary with lat and lng keys
        tour_type: Type of tour
        publish_to_queue: Whether to publish to the generation queue
        save_to_bucket: Whether to save to the content bucket
        
    Returns:
        Dictionary with results
    """
    result = {
        "city": city_name,
        "tour_type": tour_type.value,
        "places_count": 0,
        "published_to_queue": False,
        "saved_to_bucket": False
    }
    
    # Get places for this city and tour type
    places = get_places_for_location(city_name, coordinates, tour_type)
    result["places_count"] = len(places)
    
    if not places:
        return result
        
    # Publish to queue if requested
    if publish_to_queue:
        # Calculate delay between items to achieve desired rate
        delay = 1.0 / items_per_second if items_per_second > 0 else 0
        logger.info(f"Publishing to queue at rate of {items_per_second} items per second (delay: {delay:.4f}s)")
        
        for i, place in enumerate(places):
            # Log before sending to queue
            logger.info(f"Publishing place {i+1}/{len(places)}: {place.place_name} to queue")
            
            # Add to queue
            start_time = time.time()
            forward_to_generation_queue(place, tour_type)
            
            # Sleep to maintain the specified rate (except for the last item)
            if i < len(places) - 1 and delay > 0:
                # Calculate remaining time to wait to maintain the specified rate
                processing_time = time.time() - start_time
                actual_delay = max(0, delay - processing_time)
                
                if actual_delay > 0:
                    logger.info(f"Waiting {actual_delay:.4f}s before next item...")
                    time.sleep(actual_delay)
                
        result["published_to_queue"] = True
        
    # Save to content bucket if requested (or local file in dry run mode)
    if save_to_bucket:
        if dry_run:
            result["saved_to_bucket"] = save_to_local_file(city_name, tour_type, places)
        else:
            result["saved_to_bucket"] = save_to_content_bucket(city_name, tour_type, places)
        
    return result


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Generate preview data for TensorTours")
    parser.add_argument("--cities", nargs="+", help="Specific cities to generate data for (default: all)")
    parser.add_argument("--tour-types", nargs="+", help="Specific tour types to generate data for (default: all)")
    parser.add_argument("--publish-queue", action="store_true", help="Publish to generation queue")
    parser.add_argument("--no-save", action="store_true", help="Don't save to content bucket")
    parser.add_argument("--dry-run", action="store_true", help="Save to local files instead of S3 bucket")
    parser.add_argument("--max-results", type=int, default=DEFAULT_MAX_RESULTS, help="Max results per city/tour type")
    parser.add_argument("--radius", type=int, default=DEFAULT_RADIUS, help="Search radius in meters")
    parser.add_argument("--items-per-second", type=float, default=0.1, help="Rate at which to publish items to the queue (items/second)")
    
    args = parser.parse_args()
    
    # Determine which cities to process
    cities_to_process = args.cities if args.cities else CITY_COORDINATES.keys()
    
    # Determine which tour types to process
    if args.tour_types:
        tour_types_to_process = [TourType(t) for t in args.tour_types if t in [tt.value for tt in TourType]]
    else:
        tour_types_to_process = list(TourType)
    
    logger.info(f"Generating preview data for cities: {', '.join(cities_to_process)}")
    logger.info(f"Tour types: {', '.join([tt.value for tt in tour_types_to_process])}")
    
    all_results = []
    
    # Process each city and tour type combination
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_task = {}
        
        for city_name in cities_to_process:
            if city_name not in CITY_COORDINATES:
                logger.warning(f"City {city_name} not found in CITY_COORDINATES")
                continue
                
            coordinates = CITY_COORDINATES[city_name]
            
            for tour_type in tour_types_to_process:
                future = executor.submit(
                    process_city_tour_type,
                    city_name,
                    coordinates,
                    tour_type,
                    args.publish_queue,
                    not args.no_save,
                    args.dry_run,
                    args.items_per_second
                )
                future_to_task[(city_name, tour_type.value)] = future
        
        # Collect results as they complete
        for (city, tour_type), future in future_to_task.items():
            try:
                result = future.result()
                all_results.append(result)
                logger.info(f"Completed {city}/{tour_type}: {result['places_count']} places")
            except Exception as e:
                logger.error(f"Error processing {city}/{tour_type}: {str(e)}")
    
    # Print summary
    logger.info("=== SUMMARY ===")
    total_places = sum(r["places_count"] for r in all_results)
    logger.info(f"Total cities processed: {len(set(r['city'] for r in all_results))}")
    logger.info(f"Total tour types processed: {len(set(r['tour_type'] for r in all_results))}")
    logger.info(f"Total places found: {total_places}")
    if args.publish_queue:
        logger.info(f"Places published to queue: {sum(1 for r in all_results if r['published_to_queue'])}")
    if not args.no_save:
        if args.dry_run:
            logger.info(f"Places saved to local files: {sum(1 for r in all_results if r['saved_to_bucket'])}")
            logger.info(f"Output directory: {os.path.abspath('preview_data')}")
        else:
            logger.info(f"Places saved to S3 bucket: {sum(1 for r in all_results if r['saved_to_bucket'])}")


if __name__ == "__main__":
    main()
