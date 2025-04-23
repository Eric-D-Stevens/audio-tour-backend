"""On-demand tour generation handler for TensorTours backend.

This module provides a Lambda handler that combines all three stages of the tour generation pipeline:
1. photo_retriever: Retrieves photos for a place from Google Places API
2. script_generator: Generates a script for the audio tour using OpenAI
3. audio_generator: Generates audio from the script using AWS Polly

Unlike the standard pipeline, this on-demand handler:
- Does not use a tour table to track progress
- Uses faster models with higher quotas
- Stores all artifacts with a 'temp/' prefix in S3 where a lifecycle policy can be applied
- Serves as an alternative when the regular generation queue is backed up
"""

import concurrent.futures
import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

import boto3

from ..models.api import GetOnDemandTourRequest, GetOnDemandTourResponse
from ..models.tour import TourType, TTAudio, TTPlaceInfo, TTPlacePhotos, TTScript, TTour
from ..services.openai_client import ChatMessage
from ..services.user_event_table import UserEventTableClient
from ..utils.aws import upload_to_s3
from ..utils.general_utils import (
    get_google_places_client,
    get_openai_client,
    get_polly_client,
    get_user_event_table_client
)
from ..utils.script_utils import create_tour_script_prompt

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Environment variables
CONTENT_BUCKET = os.environ.get("CONTENT_BUCKET")
CLOUDFRONT_DOMAIN = os.environ.get("CLOUDFRONT_DOMAIN")

# Constants
TEMP_PREFIX = "temp/"  # Prefix for temporary storage in S3


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for generating a complete tour on-demand.

    This handler combines all three stages of the tour generation pipeline into a single function.
    Unlike the standard pipeline, it does not use a tour table to track progress and uses
    temporary storage in S3.

    Args:
        event: Lambda event containing place_id, tour_type, and place_info
        context: Lambda context

    Returns:
        Dict with status information and a complete TTour object
    """
    try:
        # Merge the body with the event to include both request data and context
        body = event.get("body", {})
        if isinstance(body, str):
            # API Gateway might send the body as a JSON string
            body = json.loads(body)

        # Create a merged dict with both body fields and the original event
        # This allows the validator to see both the request fields and the context
        merged_event = {**body, "requestContext": event.get("requestContext", {})}

        # Validate the merged event
        request = GetOnDemandTourRequest.model_validate(merged_event)
        
        # Log the user's request to get an on-demand tour
        user_event_table_client: UserEventTableClient = get_user_event_table_client()
        user_event_table_client.log_get_tour_event(request)

        place_id = request.place_id
        tour_type = request.tour_type
        
        # If place_info_json is provided in the request, use it
        place_info = None
        if request.place_info_json:
            place_info = TTPlaceInfo.model_validate_json(request.place_info_json)
        
        # If place_info is not provided, fetch it from Google Places API
        if not place_info:
            google_places_client = get_google_places_client()
            place_details = google_places_client.get_place_details(place_id)
            
            # Extract place info from place details
            place_info = TTPlaceInfo(
                place_id=place_id,
                place_name=place_details.get("displayName", {}).get("text", ""),
                place_editorial_summary=place_details.get("editorialSummary", {}).get("text", ""),
                place_address=place_details.get("formattedAddress", ""),
                place_primary_type=place_details.get("primaryType", ""),
                place_types=place_details.get("types", []),
                place_location={
                    "lat": place_details.get("location", {}).get("latitude", 0.0),
                    "lng": place_details.get("location", {}).get("longitude", 0.0),
                }
            )

        logger.info(f"Processing on-demand tour generation for place {place_id}, tour type {tour_type.value}")

        # Step 1: Retrieve photos for the place
        photos = retrieve_photos(place_id, tour_type, place_info)

        # Step 2: Generate script for the tour
        script = generate_script(place_id, tour_type, place_info)

        # Step 3: Generate audio from the script
        audio = generate_audio(place_id, tour_type, script)

        # Combine everything into a TTour object
        tour = TTour(
            place_id=place_id,
            tour_type=tour_type,
            place_info=place_info,
            photos=photos,
            script=script,
            audio=audio,
        )
        
        # Create the response using our API model
        tour_response = GetOnDemandTourResponse(
            tour=tour,
            is_authenticated=request.user is not None,
            generated_on_demand=True
        )

        return {
            "statusCode": 200,
            "body": tour_response.model_dump_json(),
        }

    except Exception as e:
        logger.exception(f"Error in on-demand tour generation: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"internal server error"}),
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"  # For CORS support
            }
        }


def retrieve_photos(
    place_id: str, tour_type: TourType, place_info: TTPlaceInfo
) -> List[TTPlacePhotos]:
    """
    Retrieve photos for a place from Google Places API.

    Args:
        place_id: Place ID
        tour_type: Tour type
        place_info: Place information

    Returns:
        List of TTPlacePhotos objects
    """
    logger.info(f"Retrieving photos for place {place_id}")

    # Get the Google Places client
    google_places_client = get_google_places_client()

    # Get place details to retrieve photos
    place_details = google_places_client.get_place_details(place_id)

    # Extract photo references from place details
    photos = []
    if "photos" in place_details:
        # Define a function to process a single photo
        def process_photo(photo_data, index):
            photo_reference = photo_data.get("name")
            if not photo_reference:
                return None

            try:
                # Download the photo
                photo_binary = google_places_client.get_place_photo(photo_reference)

                # Define S3 key for the photo with temp prefix
                photo_key = f"{TEMP_PREFIX}{place_id}/photos/photo_{index}.jpg"

                # Upload the photo to S3
                if not CONTENT_BUCKET:
                    raise ValueError("CONTENT_BUCKET environment variable not set")

                upload_to_s3(
                    bucket_name=CONTENT_BUCKET,
                    key=photo_key,
                    data=photo_binary,
                    content_type="image/jpeg",
                    binary=True
                )

                # Create CloudFront URL
                if not CLOUDFRONT_DOMAIN:
                    raise ValueError("CLOUDFRONT_DOMAIN environment variable not set")

                cloudfront_url = f"https://{CLOUDFRONT_DOMAIN}/{photo_key}"
                s3_url = f"s3://{CONTENT_BUCKET}/{photo_key}"

                # Create TTPlacePhotos object
                return TTPlacePhotos(
                    photo_id=photo_reference,
                    place_id=place_id,
                    cloudfront_url=cloudfront_url,
                    s3_url=s3_url,
                    attribution=photo_data.get("attribution", {}),
                    size_width=photo_data.get("widthPx", 0),
                    size_height=photo_data.get("heightPx", 0),
                )

            except Exception as e:
                logger.error(f"Error processing photo {photo_reference}: {str(e)}")
                return None

        # Limit to 10 photos to avoid excessive processing for on-demand generation
        photo_data_list = place_details["photos"][:10]

        # Use ThreadPoolExecutor to process photos in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # Submit all photo processing tasks to the executor with index
            future_to_photo = {
                executor.submit(process_photo, photo_data, i): photo_data
                for i, photo_data in enumerate(photo_data_list)
            }

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_photo):
                photo = future.result()
                if photo:
                    photos.append(photo)

    return photos


def generate_script(place_id: str, tour_type: TourType, place_info: TTPlaceInfo) -> TTScript:
    """
    Generate a script for the audio tour using OpenAI.

    Args:
        place_id: Place ID
        tour_type: Tour type
        place_info: Place information

    Returns:
        TTScript object
    """
    logger.info(f"Generating script for place {place_id}")

    # Get the cached OpenAI client
    client = get_openai_client()

    # Create prompts
    prompts = create_tour_script_prompt(place_info, tour_type)

    # Create messages with proper ChatMessage model
    messages = [
        ChatMessage(role="system", content=prompts["system_prompt"]),
        ChatMessage(role="user", content=prompts["user_prompt"]),
    ]

    # Generate completion - using a faster model for on-demand generation
    try:
        script_text = client.generate_completion(
            messages=messages,
            model="gpt-4o",  # Using a faster model with higher quota
            temperature=0.7,
            max_tokens=10000,
        )
    except Exception as e:
        logger.error(f"Error generating script: {str(e)}")
        raise

    # Generate a unique script ID
    script_id = str(uuid.uuid4())

    # Define S3 key for the script with temp prefix
    script_key = f"{TEMP_PREFIX}{place_id}/script/script.txt"

    # Check environment variables
    if not CONTENT_BUCKET:
        raise ValueError("CONTENT_BUCKET environment variable not set")

    if not CLOUDFRONT_DOMAIN:
        raise ValueError("CLOUDFRONT_DOMAIN environment variable not set")

    # Upload the script to S3
    upload_to_s3(
        bucket_name=CONTENT_BUCKET,
        key=script_key,
        data=script_text,
        content_type="text/plain",
    )

    # Create CloudFront and S3 URLs
    cloudfront_url = f"https://{CLOUDFRONT_DOMAIN}/{script_key}"
    s3_url = f"s3://{CONTENT_BUCKET}/{script_key}"

    # Create TTScript object
    script = TTScript(
        script_id=script_id,
        place_id=place_id,
        place_name=place_info.place_name,
        tour_type=tour_type,
        model_info={"model": "gpt-3.5-turbo", "version": "1.0"},
        s3_url=s3_url,
        cloudfront_url=cloudfront_url,
    )

    return script


def generate_audio(place_id: str, tour_type: TourType, script: TTScript) -> TTAudio:
    """
    Generate audio from the script using AWS Polly.

    Args:
        place_id: Place ID
        tour_type: Tour type
        script: Script object

    Returns:
        TTAudio object
    """
    logger.info(f"Generating audio for place {place_id}")

    # Read the script content from S3
    s3_client = boto3.client("s3")
    bucket_name = CONTENT_BUCKET
    script_key = script.s3_url.replace(f"s3://{bucket_name}/", "")

    script_obj = s3_client.get_object(Bucket=bucket_name, Key=script_key)
    script_text = script_obj["Body"].read().decode("utf-8")

    # Get the cached AWS Polly client
    polly_client = get_polly_client()

    # Define S3 key for the audio with temp prefix
    audio_key = f"{TEMP_PREFIX}{place_id}/audio/audio.mp3"

    # Generate the audio using AWS Polly and store it in S3
    polly_client.synthesize_speech_to_s3(
        text=script_text,
        bucket=bucket_name,
        key=audio_key,
        voice_id="Joanna",  # Use a different voice for on-demand tours
        engine="standard",  # Use standard engine for faster processing
        metadata={
            "place_id": place_id,
            "tour_type": tour_type.value,
            "script_id": script.script_id,
            "temp": "true",
        },
    )

    # Create CloudFront URL
    if not CLOUDFRONT_DOMAIN:
        raise ValueError("CLOUDFRONT_DOMAIN environment variable not set")

    cloudfront_url = f"https://{CLOUDFRONT_DOMAIN}/{audio_key}"
    s3_url = f"s3://{CONTENT_BUCKET}/{audio_key}"

    # Create TTAudio object
    audio = TTAudio(
        place_id=place_id,
        script_id=script.script_id,
        cloudfront_url=cloudfront_url,
        s3_url=s3_url,
        model_info={"model": "aws_polly", "voice": "Joanna", "engine": "standard"},
    )

    return audio