"""Tour generation pipeline for TensorTours backend.

This module provides three Lambda handlers that form a pipeline for generating audio tours:
1. photo_retriever: Retrieves photos for a place from Google Places API
2. script_generator: Generates a script for the audio tour using OpenAI
3. audio_generator: Generates audio from the script using AWS Polly

Each handler is triggered from an SQS queue and passes the result to the next stage.
"""

import concurrent.futures
import json
import logging
import os
from typing import Any, Dict

import boto3

from ..models.tour import TourType, TTAudio, TTPlaceInfo, TTPlacePhotos
from ..services.tour_table import GenerationStatus, TourTableItem
from ..utils.aws import upload_to_s3
from ..utils.general_utils import (
    get_google_places_client,
    get_polly_client,
    get_tour_table_client,
)
from ..utils.script_utils import generate_tour_script, save_script_to_s3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Environment variables
CONTENT_BUCKET = os.environ.get("CONTENT_BUCKET")
CLOUDFRONT_DOMAIN = os.environ.get("CLOUDFRONT_DOMAIN")
SCRIPT_QUEUE_URL = os.environ.get("SCRIPT_QUEUE_URL")
AUDIO_QUEUE_URL = os.environ.get("AUDIO_QUEUE_URL")

# Initialize AWS clients
sqs = boto3.resource("sqs")
script_queue = sqs.Queue(SCRIPT_QUEUE_URL) if SCRIPT_QUEUE_URL else None
audio_queue = sqs.Queue(AUDIO_QUEUE_URL) if AUDIO_QUEUE_URL else None


def photo_retriever_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for retrieving photos for a place from Google Places API.

    This handler is triggered from an SQS queue and retrieves photos for a place,
    stores them in S3, and sends a message to the script generation queue.

    Args:
        event: Lambda event containing SQS message with place_id, tour_type, and place_info
        context: Lambda context

    Returns:
        Dict with status information
    """
    # Extract message from SQS event
    try:
        # SQS can batch messages, but we expect one message at a time
        message = event["Records"][0]
        message_body = json.loads(message["body"])

        place_id = message_body.get("place_id")
        tour_type_str = message_body.get("tour_type")
        place_info_json = message_body.get("place_info")

        if not place_id or not tour_type_str or not place_info_json:
            raise ValueError("Missing required fields in message")

        # Parse the tour type and place info
        tour_type = TourType(tour_type_str)
        place_info = TTPlaceInfo.model_validate_json(place_info_json)

        logger.info(f"Processing photo retrieval for place {place_id}, tour type {tour_type.value}")

        # Get the tour table client
        tour_table_client = get_tour_table_client()

        # Check if the tour already exists and is in progress
        tour_item = tour_table_client.get_item(place_id, tour_type)

        if not tour_item:
            # Create a new tour item with status IN_PROGRESS
            tour_item = TourTableItem(
                place_id=place_id,
                tour_type=tour_type,
                place_info=place_info,
                status=GenerationStatus.IN_PROGRESS,
                photos=None,
                script=None,
                audio=None,
            )
            tour_table_client.put_item(tour_item)
        elif tour_item.status == GenerationStatus.IN_PROGRESS:
            # If there's already a tour in progress, skip to avoid duplicate processing
            logger.info(
                f"Tour for place {place_id}, type {tour_type.value} already in progress, skipping"
            )
            return {"statusCode": 200, "body": "Tour already in progress"}
        elif tour_item.status == GenerationStatus.COMPLETED:
            # If the tour is already completed, skip
            logger.info(
                f"Tour for place {place_id}, type {tour_type.value} already completed, skipping"
            )
            return {"statusCode": 200, "body": "Tour already completed"}
        else:
            # For any other status (like FAILED), update to IN_PROGRESS and continue
            # Use the new update_status method to only change the status field
            tour_table_client.update_status(place_id, tour_type, GenerationStatus.IN_PROGRESS)

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

                    # Define S3 key for the photo using the tours prefix structure
                    photo_key = f"tours/{place_id}/photos/photo_{index}.jpg"

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
                        attribution=photo_data.get("authorAttributions", {}),
                        size_width=photo_data.get("widthPx", 0),
                        size_height=photo_data.get("heightPx", 0),
                    )

                except Exception as e:
                    logger.error(f"Error processing photo {photo_reference}: {str(e)}")
                    return None

            # Limit to 15 photos to avoid excessive processing
            photo_data_list = place_details["photos"][:5]  # Limit to maximum 5 photos per place

            # Use ThreadPoolExecutor to process photos in parallel
            # AWS Lambda has 2 vCPUs by default, so using 10 workers is reasonable
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

        # Update the tour item with photos
        tour_item.photos = photos
        tour_table_client.put_item(tour_item)

        # Send message to script generation queue
        if script_queue:
            # Just use the TourTableItem's serialization method directly as the message body
            script_queue.send_message(MessageBody=tour_item.model_dump_json())
            logger.info(f"Sent message to script generation queue for place {place_id}")
        else:
            logger.warning("Script generation queue not configured, skipping")

        return {"statusCode": 200, "body": tour_item.model_dump_json()}

    except Exception as e:
        logger.error(f"Error in photo retriever: {str(e)}")
        # If we have the place_id and tour_type, update the status to failed
        try:
            if place_id and tour_type:
                tour_table_client = get_tour_table_client()
                tour_item = tour_table_client.get_item(place_id, tour_type)
                if tour_item:
                    # Use the new update_status method to only change the status field
                    tour_table_client.update_status(place_id, tour_type, GenerationStatus.FAILED)
        except Exception as update_error:
            logger.error(f"Error updating tour status: {str(update_error)}")

        # Re-raise the exception for Lambda to handle
        raise


def script_generator_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for generating a script for the audio tour using OpenAI.

    This handler is triggered from an SQS queue and generates a script for the audio tour,
    stores it in S3, and sends a message to the audio generation queue.

    Args:
        event: Lambda event containing SQS message with place_id, tour_type, photos, and place_info
        context: Lambda context

    Returns:
        Dict with status information
    """
    # Extract message from SQS event
    try:
        # SQS can batch messages, but we expect one message at a time
        message = event["Records"][0]
        message_body = message["body"]

        # Parse the tour item directly from the message body
        tour_item = TourTableItem.model_validate_json(message_body)

        # Extract the key fields for convenience
        place_id = tour_item.place_id
        tour_type = tour_item.tour_type
        place_info = tour_item.place_info

        logger.info(
            f"Processing script generation for place {place_id}, tour type {tour_type.value}"
        )

        # Get the tour table client
        tour_table_client = get_tour_table_client()

        # Check if the tour already exists and is in progress
        if tour_item.status == GenerationStatus.IN_PROGRESS and tour_item.script is not None:
            # If there's already an audio generation in progress with audio, skip to avoid duplicate processing
            logger.info(
                f"Audio generation for place {place_id}, type {tour_type.value} already in progress, skipping"
            )
            return {"statusCode": 200, "body": tour_item.model_dump_json()}
        elif tour_item.status == GenerationStatus.COMPLETED:
            # If the tour is already completed, skip
            logger.info(
                f"Tour for place {place_id}, type {tour_type.value} already completed, skipping"
            )
            return {"statusCode": 200, "body": tour_item.model_dump_json()}
        elif tour_item.status != GenerationStatus.IN_PROGRESS:
            # For any other status (like FAILED), update to IN_PROGRESS and continue
            # Use the new update_status method to only change the status field
            tour_table_client.update_status(place_id, tour_type, GenerationStatus.IN_PROGRESS)

        # Generate the script using our utility function
        script_text = generate_tour_script(place_info, tour_type)

        # Save the script to S3 and get a TTScript object
        script = save_script_to_s3(script_text, place_id, place_info.place_name, tour_type)

        # Update the tour item with the script
        tour_item.script = script
        tour_table_client.put_item(tour_item)

        # Send message to audio generation queue
        if audio_queue:
            # Just use the TourTableItem's serialization method directly as the message body
            audio_queue.send_message(MessageBody=tour_item.model_dump_json())
            logger.info(f"Sent message to audio generation queue for place {place_id}")
        else:
            logger.warning("Audio generation queue not configured, skipping")

        return {"statusCode": 200, "body": tour_item.model_dump_json()}

    except Exception as e:
        logger.error(f"Error in script generator: {str(e)}")
        # If we have the place_id and tour_type, update the status to failed
        try:
            if place_id and tour_type:
                tour_table_client = get_tour_table_client()
                tour_item = tour_table_client.get_item(place_id, tour_type)
                if tour_item:
                    # Use the new update_status method to only change the status field
                    tour_table_client.update_status(place_id, tour_type, GenerationStatus.FAILED)
        except Exception as update_error:
            logger.error(f"Error updating tour status: {str(update_error)}")

        # Re-raise the exception for Lambda to handle
        raise


def audio_generator_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for generating audio from the script using AWS Polly.

    This handler is triggered from an SQS queue and generates audio from the script,
    stores it in S3, and updates the tour item in the tour table.

    Args:
        event: Lambda event containing SQS message with place_id, tour_type, script, photos, and place_info
        context: Lambda context

    Returns:
        Dict with status information
    """
    # Extract message from SQS event
    try:
        # SQS can batch messages, but we expect one message at a time
        message = event["Records"][0]
        message_body = message["body"]

        # Parse the tour item directly from the message body
        tour_item = TourTableItem.model_validate_json(message_body)

        # Extract the key fields for convenience
        place_id = tour_item.place_id
        tour_type = tour_item.tour_type
        script = tour_item.script

        if not script:
            raise ValueError(f"Tour item for place {place_id} does not have a script")

        logger.info(
            f"Processing audio generation for place {place_id}, tour type {tour_type.value}"
        )

        # Get the tour table client
        tour_table_client = get_tour_table_client()

        # Check if the tour already exists and is in progress
        tour_item = tour_table_client.get_item(place_id, tour_type)

        if not tour_item:
            raise ValueError(f"Tour item for place {place_id}, type {tour_type.value} not found")

        if tour_item.status == GenerationStatus.IN_PROGRESS and tour_item.audio is not None:
            # If there's already an audio generation in progress with audio, skip to avoid duplicate processing
            logger.info(
                f"Audio generation for place {place_id}, type {tour_type.value} already in progress, skipping"
            )
            return {"statusCode": 200, "body": tour_item.model_dump_json()}
        elif tour_item.status == GenerationStatus.COMPLETED:
            # If the tour is already completed, skip
            logger.info(
                f"Tour for place {place_id}, type {tour_type.value} already completed, skipping"
            )
            return {"statusCode": 200, "body": tour_item.model_dump_json()}
        elif tour_item.status != GenerationStatus.IN_PROGRESS:
            # For any other status (like FAILED), update to IN_PROGRESS and continue
            # Use the new update_status method to only change the status field
            tour_table_client.update_status(place_id, tour_type, GenerationStatus.IN_PROGRESS)

        # Read the script content from S3
        s3_client = boto3.client("s3")
        bucket_name = CONTENT_BUCKET
        script_key = script.s3_url.replace(f"s3://{bucket_name}/", "")

        script_obj = s3_client.get_object(Bucket=bucket_name, Key=script_key)
        script_text = script_obj["Body"].read().decode("utf-8")

        # Get the cached AWS Polly client
        polly_client = get_polly_client()

        # Define S3 key for the audio using the tours prefix structure with tour type in filename
        audio_key = f"tours/{place_id}/audio/{tour_type.value}_audio.mp3"

        # Generate the audio using AWS Polly and store it in S3
        polly_client.synthesize_speech_to_s3(
            text=script_text,
            bucket=bucket_name,
            key=audio_key,
            voice_id="Amy",  # Use a neutral English voice
            engine="neural",  # Use the neural engine for better quality
            metadata={
                "place_id": place_id,
                "tour_type": tour_type.value,
                "script_id": script.script_id,
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
            model_info={"model": "aws_polly", "voice": "Amy", "engine": "generative"},
        )

        # Update the tour item with the audio and set status to COMPLETED
        tour_item.audio = audio
        tour_item.status = GenerationStatus.COMPLETED
        tour_table_client.put_item(tour_item)

        logger.info(f"Completed audio generation for place {place_id}, tour type {tour_type.value}")

        return {"statusCode": 200, "body": tour_item.model_dump_json()}

    except Exception as e:
        logger.error(f"Error in audio generator: {str(e)}")
        # If we have the place_id and tour_type, update the status to failed
        try:
            if place_id and tour_type:
                tour_table_client = get_tour_table_client()
                tour_item = tour_table_client.get_item(place_id, tour_type)
                if tour_item:
                    # Use the new update_status method to only change the status field
                    tour_table_client.update_status(place_id, tour_type, GenerationStatus.FAILED)
        except Exception as update_error:
            logger.error(f"Error updating tour status: {str(update_error)}")

        # Re-raise the exception for Lambda to handle
        raise
