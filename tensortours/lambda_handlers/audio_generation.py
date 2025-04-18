"""
Audio generation Lambda handler for TensorTours backend.
Handles voice synthesis of tour scripts using ElevenLabs API.
"""
import json
import logging
import os
import boto3
import requests
from typing import Dict, Any

from tensortours.utils.aws import get_api_key_from_secret, upload_to_s3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3 = boto3.client('s3')
secrets_client = boto3.client('secretsmanager')

# Environment variables
BUCKET_NAME = os.environ.get('CONTENT_BUCKET_NAME')
CLOUDFRONT_DOMAIN = os.environ.get('CLOUDFRONT_DOMAIN')
ELEVENLABS_API_KEY_SECRET_NAME = os.environ.get('ELEVENLABS_API_KEY_SECRET_NAME')

# ElevenLabs API
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"
DEFAULT_VOICE_ID = "ThT5KcBeYPX3keUQqHPh"  # Josh - professional narrator voice


def handler(event, context):
    """
    Lambda handler for generating audio from text using ElevenLabs.
    
    Expected request format:
    {
        "text": "Text to convert to speech",
        "voice_id": "Optional voice ID, defaults to professional narrator",
        "output_key": "Optional S3 key for the output file"
    }
    """
    logger.info(f"Received audio generation request")
    
    # Handle API Gateway proxy integration
    if 'body' in event:
        try:
            body = json.loads(event['body'])
        except (TypeError, json.JSONDecodeError):
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid request body'})
            }
    else:
        body = event
    
    # Extract parameters
    text = body.get('text')
    if not text:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing required parameter: text'})
        }
    
    voice_id = body.get('voice_id', DEFAULT_VOICE_ID)
    output_key = body.get('output_key')
    
    try:
        # Generate audio
        audio_data = generate_audio(text, voice_id)
        
        # If output key provided, upload to S3
        if output_key and BUCKET_NAME and CLOUDFRONT_DOMAIN:
            upload_to_s3(
                bucket_name=BUCKET_NAME,
                key=output_key,
                data=audio_data,
                content_type='audio/mpeg',
                binary=True
            )
            
            audio_url = f"https://{CLOUDFRONT_DOMAIN}/{output_key}"
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'success': True,
                    'audio_url': audio_url
                })
            }
        else:
            # Return audio data as base64 encoded string
            import base64
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'audio/mpeg',
                    'Content-Disposition': 'attachment; filename="audio.mp3"'
                },
                'body': base64.b64encode(audio_data).decode('utf-8'),
                'isBase64Encoded': True
            }
    except Exception as e:
        logger.exception(f"Error generating audio: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Failed to generate audio', 'details': str(e)})
        }


def generate_audio(text: str, voice_id: str = DEFAULT_VOICE_ID) -> bytes:
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
    
    url = f"{ELEVENLABS_API_URL}/{voice_id}"
    
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    
    return response.content
