"""
Tour generation Lambda handler for TensorTours backend.
Handles the audio generation phase of tour creation.
"""
import json
import logging
import os
import time
import boto3
import requests
from typing import Dict, Any, List

from tensortours.models.message import TourPreGenerationResult
from tensortours.utils.aws import get_api_key_from_secret, upload_to_s3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3 = boto3.client('s3')
secrets_client = boto3.client('secretsmanager')
sqs = boto3.client('sqs')

# Environment variables
BUCKET_NAME = os.environ.get('CONTENT_BUCKET_NAME')
CLOUDFRONT_DOMAIN = os.environ.get('CLOUDFRONT_DOMAIN')
OPENAI_API_KEY_SECRET_NAME = os.environ.get('OPENAI_API_KEY_SECRET_NAME')
ELEVENLABS_API_KEY_SECRET_NAME = os.environ.get('ELEVENLABS_API_KEY_SECRET_NAME')

# API endpoints
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"

# Default voice ID for Eleven Labs
DEFAULT_VOICE_ID = "ThT5KcBeYPX3keUQqHPh"  # Josh - professional narrator voice


def handler(event, context):
    """
    Lambda handler for generating audio tours.
    
    Expected input (from SQS or direct invocation):
    TourPreGenerationResult containing place details, script, and photo URLs
    """
    logger.info(f"Received event for tour generation")
    
    # Process SQS messages
    if 'Records' in event:
        for record in event['Records']:
            if 'body' in record:
                try:
                    # Parse SQS message
                    result = TourPreGenerationResult(**json.loads(record['body']))
                    process_tour_generation(result)
                except Exception as e:
                    logger.exception(f"Error processing SQS message: {e}")
    else:
        # Direct invocation
        try:
            result = TourPreGenerationResult(**event)
            return process_tour_generation(result)
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


def process_tour_generation(result: TourPreGenerationResult) -> Dict[str, Any]:
    """Process the tour generation request and generate audio for each segment."""
    place_id = result.place_id
    script = result.script
    logger.info(f"Processing tour generation for place: {place_id}")
    
    if not script or not script.get('segments'):
        raise ValueError("No script segments found in the input")
    
    # Generate audio for each script segment
    audio_segments = []
    for i, segment in enumerate(script.get('segments', [])):
        logger.info(f"Generating audio for segment {i+1}: {segment.get('title')}")
        
        try:
            # Generate audio with Eleven Labs
            audio_data = generate_audio(segment.get('content'))
            
            # Upload to S3
            audio_key = f"audio/{place_id}/{i}.mp3"
            audio_url = upload_audio(audio_data, audio_key)
            
            # Add to segments
            audio_segments.append({
                "segment_id": f"{place_id}_{i}",
                "title": segment.get('title'),
                "url": audio_url,
                "duration_seconds": segment.get('duration_seconds', 120),
                "transcript": segment.get('content')
            })
        except Exception as e:
            logger.exception(f"Error generating audio for segment {i+1}: {e}")
            continue
    
    # Create the complete tour object
    tour_id = f"tour_{place_id}_{int(time.time())}"
    complete_tour = {
        "tour_id": tour_id,
        "place_id": place_id,
        "place_name": script.get('place_name'),
        "tour_type": script.get('tour_type'),
        "duration_minutes": sum(segment.get('duration_seconds', 0) for segment in script.get('segments', [])) // 60,
        "language": "en",
        "audio_segments": audio_segments,
        "photos": result.photo_urls,
        "generated_at": script.get('generated_at', time.strftime("%Y-%m-%dT%H:%M:%SZ")),
        "status": "complete"
    }
    
    # Save the complete tour to S3
    tour_key = f"tours/{place_id}/tour.json"
    uploaded = upload_to_s3(
        bucket_name=BUCKET_NAME,
        key=tour_key,
        data=json.dumps(complete_tour),
        content_type='application/json'
    )
    
    if uploaded:
        logger.info(f"Tour generation complete for {place_id}, saved to {tour_key}")
    else:
        logger.error(f"Failed to save tour for {place_id}")
    
    return complete_tour


def generate_audio(text: str) -> bytes:
    """Generate audio from text using Eleven Labs API."""
    api_key = get_api_key_from_secret(ELEVENLABS_API_KEY_SECRET_NAME, 'ELEVENLABS_API_KEY')
    
    if not api_key:
        raise ValueError("Could not retrieve Eleven Labs API key")
    
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }
    
    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.75,
            "similarity_boost": 0.75
        }
    }
    
    url = f"{ELEVENLABS_API_URL}/{DEFAULT_VOICE_ID}"
    
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    
    return response.content


def upload_audio(audio_data: bytes, key: str) -> str:
    """Upload audio to S3 and return CloudFront URL."""
    if not BUCKET_NAME or not CLOUDFRONT_DOMAIN:
        raise ValueError("S3 bucket or CloudFront domain not configured")
    
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=audio_data,
        ContentType='audio/mpeg'
    )
    
    return f"https://{CLOUDFRONT_DOMAIN}/{key}"
