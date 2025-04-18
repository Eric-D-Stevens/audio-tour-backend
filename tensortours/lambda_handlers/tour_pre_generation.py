"""Pre-generation Lambda handler for TensorTours backend."""
import json
import logging
import os
from typing import Dict, Any

import boto3

from tensortours.models.message import TourGenerationMessage, TourPreGenerationResult
from tensortours.models.tour import TourType
from tensortours.services.places import PlacesService
# Import other services as needed

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients - will be initialized once per Lambda container
s3 = boto3.client('s3')
sqs = boto3.client('sqs')
dynamodb = boto3.resource('dynamodb')

# Get environment variables
BUCKET_NAME = os.environ['CONTENT_BUCKET_NAME']
CLOUDFRONT_DOMAIN = os.environ['CLOUDFRONT_DOMAIN']
PLACES_TABLE_NAME = os.environ.get('PLACES_TABLE_NAME', 'tensortours-places')
TOUR_GENERATION_QUEUE_URL = os.environ.get('TOUR_GENERATION_QUEUE_URL')


def handler(event, context):
    """
    Lambda handler for pre-generating audio tours triggered by SQS events.
    
    Expected SQS message format:
    {
        "placeId": "Google Place ID",
        "tourType": "Type of tour (history, cultural, etc.)"
    }
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Process SQS messages
    if 'Records' in event:
        for record in event['Records']:
            if 'body' in record:
                try:
                    # Parse SQS message
                    message_body = json.loads(record['body'])
                    message = TourGenerationMessage(
                        message_id=record.get('messageId'),
                        receipt_handle=record.get('receiptHandle'),
                        **message_body
                    )
                    
                    # Process the message
                    result = process_tour_request(message)
                    
                    # Send result to next step in pipeline
                    if result and TOUR_GENERATION_QUEUE_URL:
                        sqs.send_message(
                            QueueUrl=TOUR_GENERATION_QUEUE_URL,
                            MessageBody=json.dumps(result.dict())
                        )
                        
                except Exception as e:
                    logger.exception(f"Error processing SQS message: {e}")
    else:
        # Direct invocation (not from SQS)
        try:
            message = TourGenerationMessage(**event)
            return process_tour_request(message).dict()
        except Exception as e:
            logger.exception(f"Error processing direct invocation: {e}")
            return {
                "statusCode": 500,
                "body": json.dumps({"error": str(e)})
            }
    
    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Processing complete"})
    }


def process_tour_request(message: TourGenerationMessage) -> TourPreGenerationResult:
    """Process a tour generation request.
    
    Args:
        message: The tour generation message
        
    Returns:
        TourPreGenerationResult with place details, script, and photo URLs
    """
    logger.info(f"Processing tour request for place: {message.place_id}")
    
    # Initialize services
    places_service = PlacesService()
    
    # Get place details
    place_details = places_service.get_place_details(message.place_id)
    logger.info(f"Retrieved details for place: {place_details.name}")
    
    # Get place photos
    photo_urls = places_service.get_place_photos(message.place_id)
    logger.info(f"Retrieved {len(photo_urls)} photos for place: {place_details.name}")
    
    # In a real implementation, you would generate a script here
    # This would likely involve a call to an AI service like OpenAI
    # For this example, we'll use a placeholder
    script = {
        "place_id": message.place_id,
        "place_name": place_details.name,
        "tour_type": message.tour_type,
        "segments": [
            {
                "title": f"Introduction to {place_details.name}",
                "content": f"Welcome to {place_details.name}, a fascinating location...",
                "duration_seconds": 120
            }
        ],
        "total_duration_seconds": 120,
        "generated_at": "2025-04-17T16:00:00Z"
    }
    
    # Create result
    result = TourPreGenerationResult(
        place_id=message.place_id,
        place_details=place_details.dict(),
        script=script,
        photo_urls=photo_urls
    )
    
    return result
