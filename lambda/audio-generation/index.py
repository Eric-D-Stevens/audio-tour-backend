import json
import os
import time
import boto3
import requests
import base64
import logging
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3 = boto3.client('s3')
BUCKET_NAME = os.environ['CONTENT_BUCKET_NAME']
CLOUDFRONT_DOMAIN = os.environ['CLOUDFRONT_DOMAIN']

# API keys from environment variables
OPENAI_API_KEY = os.environ['OPENAI_API_KEY']
ELEVENLABS_API_KEY = os.environ['ELEVENLABS_API_KEY']

# API endpoints
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"

# Default voice ID for Eleven Labs (professional narrator voice)
DEFAULT_VOICE_ID = "ThT5KcBeYPX3keUQqHPh"  # Josh - professional narrator voice

def handler(event, context):
    """
    Lambda handler for the audio tour generation API.
    
    Expected parameters:
    - placeId: Google Place ID
    - tourType: Type of tour (history, cultural, etc.)
    """
    try:
        # Extract parameters
        path_params = event.get('pathParameters', {}) or {}
        query_params = event.get('queryStringParameters', {}) or {}
        
        if 'placeId' not in path_params:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing required parameter: placeId'})
            }
        
        place_id = path_params['placeId']
        tour_type = query_params.get('tourType', 'history')
        
        # Check if this is a preview or authenticated request
        is_preview = 'preview' in event.get('path', '')
        
        # Check if content already exists in S3
        script_key = f"scripts/{place_id}_{tour_type}.txt"
        audio_key = f"audio/{place_id}_{tour_type}.mp3"
        
        script_exists = check_if_file_exists(script_key)
        audio_exists = check_if_file_exists(audio_key)
        
        response_data = {}
        
        if script_exists and audio_exists:
            # Both script and audio exist, return their URLs
            script_url = f"https://{CLOUDFRONT_DOMAIN}/{script_key}"
            audio_url = f"https://{CLOUDFRONT_DOMAIN}/{audio_key}"
            
            response_data = {
                'place_id': place_id,
                'tour_type': tour_type,
                'script_url': script_url,
                'audio_url': audio_url,
                'cached': True
            }
        else:
            # Need to generate content
            # First, get place details from Google Places API
            place_details = get_place_details(place_id)
            
            if not place_details:
                return {
                    'statusCode': 404,
                    'body': json.dumps({'error': 'Place details not found'})
                }
            
            # Generate script with OpenAI
            script = generate_script(place_details, tour_type)
            
            if not script:
                return {
                    'statusCode': 500,
                    'body': json.dumps({'error': 'Failed to generate script'})
                }
            
            # Save script to S3
            upload_to_s3(script_key, script, 'text/plain')
            script_url = f"https://{CLOUDFRONT_DOMAIN}/{script_key}"
            
            # Generate audio with Eleven Labs
            audio_data = generate_audio(script)
            
            if not audio_data:
                return {
                    'statusCode': 500,
                    'body': json.dumps({'error': 'Failed to generate audio'})
                }
            
            # Save audio to S3
            upload_to_s3(audio_key, audio_data, 'audio/mpeg', binary=True)
            audio_url = f"https://{CLOUDFRONT_DOMAIN}/{audio_key}"
            
            response_data = {
                'place_id': place_id,
                'tour_type': tour_type,
                'script_url': script_url,
                'audio_url': audio_url,
                'cached': False,
                'place_details': place_details
            }
        
        # For preview mode, we include the actual script content as well
        if is_preview:
            try:
                script_content = get_script_content(script_key)
                response_data['script'] = script_content
            except Exception as e:
                logger.warning(f"Could not retrieve script content: {str(e)}")
        
        return {
            'statusCode': 200,
            'body': json.dumps(response_data)
        }
    
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal server error: {str(e)}'})
        }

def check_if_file_exists(key):
    """Check if a file exists in S3 bucket"""
    try:
        s3.head_object(Bucket=BUCKET_NAME, Key=key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        else:
            logger.error(f"Error checking S3 object: {str(e)}")
            raise

def upload_to_s3(key, data, content_type, binary=False):
    """Upload data to S3 bucket"""
    try:
        if binary:
            s3.put_object(
                Bucket=BUCKET_NAME,
                Key=key,
                Body=data,
                ContentType=content_type
            )
        else:
            s3.put_object(
                Bucket=BUCKET_NAME,
                Key=key,
                Body=data.encode('utf-8'),
                ContentType=content_type
            )
        return True
    except Exception as e:
        logger.error(f"Error uploading to S3: {str(e)}")
        return False

def get_script_content(key):
    """Get script content from S3"""
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=key)
        return response['Body'].read().decode('utf-8')
    except Exception as e:
        logger.error(f"Error getting script from S3: {str(e)}")
        raise

def get_place_details(place_id):
    """Get place details from Google Places API"""
    # This would make a call to the Google Places API
    # For simplicity, we'll simulate it here - in a real implementation,
    # you would make the actual API call to get details
    
    # Use the Google Maps API key from environment variables
    api_key = os.environ['GOOGLE_MAPS_API_KEY']
    url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=name,formatted_address,rating,types,editorial_summary,website,formatted_phone_number&key={api_key}"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'OK':
                return data.get('result', {})
    except Exception as e:
        logger.error(f"Error fetching place details: {str(e)}")
    
    return None

def generate_script(place_details, tour_type):
    """Generate script for the audio tour using OpenAI"""
    try:
        # Prepare the place information for prompt
        place_name = place_details.get('name', 'this location')
        place_address = place_details.get('formatted_address', '')
        place_types = place_details.get('types', [])
        place_summary = place_details.get('editorial_summary', {}).get('overview', '')
        
        # Craft the prompt for OpenAI
        system_prompt = f"""
        You are an expert tour guide creating an audio script for {tour_type} tours.
        Write an engaging, informative, and factual script about this place.
        The script should be 2-3 minutes when read aloud (approximately 300-400 words).
        Focus on the most interesting aspects relevant to a {tour_type} tour.
        Use a conversational, engaging tone as if speaking directly to the listener.
        Start with a brief introduction to the place and then share the most interesting facts or stories.
        End with a suggestion of what to observe or experience at the location.
        """
        
        user_prompt = f"""
        Create an audio tour script for: {place_name}
        Address: {place_address}
        Category: {', '.join(place_types)}
        Additional information: {place_summary}
        
        This is for a {tour_type} focused tour.
        """
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}"
        }
        
        payload = {
            "model": "gpt-4-turbo",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 1000
        }
        
        response = requests.post(OPENAI_API_URL, headers=headers, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            script = result['choices'][0]['message']['content'].strip()
            return script
        else:
            logger.error(f"OpenAI API error: {response.text}")
            return None
    
    except Exception as e:
        logger.error(f"Error generating script: {str(e)}")
        return None

def generate_audio(script):
    """Generate audio from script using Eleven Labs API"""
    try:
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": ELEVENLABS_API_KEY
        }
        
        payload = {
            "text": script,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }
        
        url = f"{ELEVENLABS_API_URL}/{DEFAULT_VOICE_ID}"
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            return response.content
        else:
            logger.error(f"Eleven Labs API error: {response.status_code}: {response.text}")
            return None
    
    except Exception as e:
        logger.error(f"Error generating audio: {str(e)}")
        return None