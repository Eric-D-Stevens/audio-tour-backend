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
secrets_client = boto3.client('secretsmanager')
BUCKET_NAME = os.environ['CONTENT_BUCKET_NAME']
CLOUDFRONT_DOMAIN = os.environ['CLOUDFRONT_DOMAIN']

# Secret names for API keys
OPENAI_API_KEY_SECRET_NAME = os.environ['OPENAI_API_KEY_SECRET_NAME']
ELEVENLABS_API_KEY_SECRET_NAME = os.environ['ELEVENLABS_API_KEY_SECRET_NAME']
GOOGLE_MAPS_API_KEY_SECRET_NAME = os.environ['GOOGLE_MAPS_API_KEY_SECRET_NAME']

# Function to retrieve secret from AWS Secrets Manager
def get_secret(secret_name):
    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        if 'SecretString' in response:
            return response['SecretString']
    except ClientError as e:
        logger.exception(f"Error retrieving secret {secret_name}")
        raise e

# Get API keys from Secrets Manager
def get_openai_api_key():
    secret = get_secret(OPENAI_API_KEY_SECRET_NAME)
    try:
        secret_dict = json.loads(secret)
        return secret_dict.get('OPENAI_API_KEY', secret)
    except json.JSONDecodeError:
        return secret

def get_elevenlabs_api_key():
    secret = get_secret(ELEVENLABS_API_KEY_SECRET_NAME)
    try:
        secret_dict = json.loads(secret)
        return secret_dict.get('ELEVENLABS_API_KEY', secret)
    except json.JSONDecodeError:
        return secret

def get_google_maps_api_key():
    secret = get_secret(GOOGLE_MAPS_API_KEY_SECRET_NAME)
    try:
        secret_dict = json.loads(secret)
        return secret_dict.get('GOOGLE_MAPS_API_KEY', secret)
    except json.JSONDecodeError:
        return secret

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
        
        # Check if content already exists in S3
        script_key = f"scripts/{place_id}_{tour_type}.txt"
        audio_key = f"audio/{place_id}_{tour_type}.mp3"
        
        script_exists = check_if_file_exists(script_key)
        audio_exists = check_if_file_exists(audio_key)
        
        response_data = {}
        
        # Get place details from Google Places API
        place_details = get_place_details(place_id)
        
        if not place_details:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Place details not found'})
            }
        
        if script_exists and audio_exists:
            # Both script and audio exist, return their URLs
            script_url = f"https://{CLOUDFRONT_DOMAIN}/{script_key}"
            audio_url = f"https://{CLOUDFRONT_DOMAIN}/{audio_key}"
            
            response_data = {
                'place_id': place_id,
                'tour_type': tour_type,
                'script_url': script_url,
                'audio_url': audio_url,
                'cached': True,
                'place_details': place_details
            }
        else:
            # Need to generate content
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
                'place_details': place_details,
                'place_details': place_details
            }
        
        
        return {
            'statusCode': 200,
            'body': json.dumps(response_data)
        }
    
    except Exception as e:
        logger.exception("Error processing request")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': f'Internal server error: {str(e)}',
                'details': str(e)
            })
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
            logger.exception(f"Error checking S3 object")
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
        logger.exception(f"Error uploading to S3")
        return False

def get_script_content(key):
    """Get script content from S3"""
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=key)
        return response['Body'].read().decode('utf-8')
    except Exception as e:
        logger.error(f"Error getting script from S3: {str(e)}")
        raise

# New Google Places API v1 endpoint
PLACES_API_BASE_URL = 'https://places.googleapis.com/v1/places'

def get_place_details(place_id):
    """Get place details from Google Places API v1"""
    logger.info(f"Fetching place details for place_id: {place_id}")
    
    try:
        # Get the API key
        api_key = get_google_maps_api_key()
        logger.debug("Successfully retrieved Google Maps API key")
            
        url = f"{PLACES_API_BASE_URL}/{place_id}"
        logger.debug(f"Making request to Google Places API v1 for place_id: {place_id}")
        
        headers = {
            'Content-Type': 'application/json',
            'X-Goog-Api-Key': api_key,
            'X-Goog-FieldMask': 'displayName,formattedAddress,rating,types,editorialSummary,websiteUri,nationalPhoneNumber,photos'
        }
        
        try:
            response = requests.get(url, headers=headers)
            logger.info(f"Google Places API response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Successfully retrieved details for {result.get('displayName', 'unknown place')}")
                
                # Convert v1 API response to match old format for compatibility
                editorial_text = ''
                if 'editorialSummary' in result:
                    editorial_text = result['editorialSummary'].get('text', '')
                
                converted_result = {
                    'name': result.get('displayName'),
                    'formatted_address': result.get('formattedAddress'),
                    'rating': result.get('rating'),
                    'types': result.get('types', []),
                    'editorial_summary': {'overview': editorial_text},
                    'website': result.get('websiteUri'),
                    'formatted_phone_number': result.get('nationalPhoneNumber'),
                    'photos': [f"https://places.googleapis.com/v1/{photo.get('name')}/media?key={api_key}" for photo in result.get('photos', [])]
                }
                
                return converted_result
            else:
                logger.error(f"Google Places API request failed with status {response.status_code}")
                logger.error(f"Response content: {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error fetching place details: {str(e)}")
            logger.exception("Full traceback:")
            return None
            
    except Exception as e:
        logger.error(f"Error retrieving Google Maps API key: {str(e)}")
        logger.exception("Full traceback:")
        return None

def generate_script(place_details, tour_type):
    """Generate script for the audio tour using OpenAI"""
    try:
        # Log input parameters
        logger.info(f"Generating script for tour_type: {tour_type}")
        logger.debug(f"Place details received: {json.dumps(place_details, indent=2)}")
        
        # Prepare the place information for prompt
        place_name = place_details.get('name', 'this location')
        place_address = place_details.get('formatted_address', '')
        place_types = place_details.get('types', [])
        place_summary = place_details.get('editorial_summary', {}).get('overview', '')
        
        logger.info(f"Generating script for: {place_name}")
        
        # Craft the prompt for OpenAI
        system_prompt = f"""
        You are an expert tour guide creating an audio script for {tour_type} tours.
        Write an engaging, informative, and factual script about this place.
        The script should be 2-3 minutes when read aloud (approximately 300-400 words).
        Focus on the most interesting aspects relevant to a {tour_type} tour.
        Use a conversational, engaging tone as if speaking directly to the listener.
        Start with a brief introduction to the place and then share the most interesting facts or stories.
        End with a suggestion of what to observe or experience at the location.
        Everything you return will be read out loud, so don't include any additional formatting.
        """
        
        user_prompt = f"""
        Create an audio tour script for: {place_name}
        Address: {place_address}
        Category: {', '.join(place_types)}
        Additional information: {place_summary}
        
        This is for a {tour_type} focused tour.
        """
        
        logger.debug(f"System prompt length: {len(system_prompt)} chars")
        logger.debug(f"User prompt length: {len(user_prompt)} chars")
        
        # Get OpenAI API key from Secrets Manager
        logger.debug("Retrieving OpenAI API key")
        openai_api_key = get_openai_api_key()
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openai_api_key}"
        }
        
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 5000
        }
        
        logger.info(f"Making request to OpenAI API with model: {payload['model']}")
        
        try:
            response = requests.post(OPENAI_API_URL, headers=headers, json=payload)
            logger.info(f"OpenAI API response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                script = result['choices'][0]['message']['content'].strip()
                script_length = len(script)
                logger.info(f"Successfully generated script of length: {script_length} chars")
                logger.debug(f"Generated script preview: {script[:100]}...")
                return script
            else:
                logger.error(f"OpenAI API error status {response.status_code}: {response.text}")
                try:
                    error_data = response.json()
                    logger.error(f"OpenAI error details: {json.dumps(error_data, indent=2)}")
                except:
                    logger.error(f"Raw response text: {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error calling OpenAI API: {str(e)}")
            logger.exception("Full traceback:")
            return None
    
    except Exception as e:
        logger.error(f"Error generating script: {str(e)}")
        logger.exception("Full traceback:")
        return None

def generate_audio(script):
    """Generate audio from script using Eleven Labs API"""
    try:
        script_length = len(script)
        logger.info(f"Generating audio for script of length: {script_length} chars")
        logger.debug(f"Script preview: {script[:100]}...")
        
        # Get ElevenLabs API key from Secrets Manager
        logger.debug("Retrieving ElevenLabs API key")
        elevenlabs_api_key = get_elevenlabs_api_key()
        
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": elevenlabs_api_key
        }
        
        payload = {
            "text": script,
            "model_id": "eleven_flash_v2_5",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }
        
        url = f"{ELEVENLABS_API_URL}/{DEFAULT_VOICE_ID}"
        logger.info(f"Making request to ElevenLabs API with model: {payload['model_id']}")
        logger.debug(f"Using voice ID: {DEFAULT_VOICE_ID}")
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            logger.info(f"ElevenLabs API response status: {response.status_code}")
            
            if response.status_code == 200:
                audio_size = len(response.content)
                logger.info(f"Successfully generated audio of size: {audio_size} bytes")
                return response.content
            else:
                logger.error(f"ElevenLabs API error status {response.status_code}")
                try:
                    error_data = response.json()
                    logger.error(f"ElevenLabs error details: {json.dumps(error_data, indent=2)}")
                except:
                    logger.error(f"Raw response text: {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error calling ElevenLabs API: {str(e)}")
            logger.exception("Full traceback:")
            return None
    
    except Exception as e:
        logger.error(f"Error generating audio: {str(e)}")
        logger.exception("Full traceback:")
        return None