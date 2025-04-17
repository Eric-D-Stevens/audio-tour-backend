"""
Lambda handler for the tour generation service

This service orchestrates the process of generating audio tours by:
1. Retrieving place details from Google Places API
2. Generating tour scripts using OpenAI
3. Converting scripts to audio using AWS Polly
4. Parallelizing photo retrieval and caching
5. Storing content in S3 and DynamoDB for future use

The implementation prioritizes efficiency through:
- Parallel photo processing
- Modular service components for easier testing
- Detailed performance metrics logging
- Proper error handling and retry logic
"""
import json
import os
import time
import logging
import traceback
import concurrent.futures
import boto3
from botocore.exceptions import ClientError

# Import service modules
from utils.logging_config import configure_logging, log_event_and_context
from utils.timing import timed, timed_operation, metrics
from services.photo_service import PhotoService
from services.tts_service import TTSService
from services.content_service import ContentService
from services.place_service import PlaceService

# Initialize AWS clients
s3 = boto3.client('s3')

# Constants
BUCKET_NAME = os.environ.get('CONTENT_BUCKET_NAME')
CLOUDFRONT_DOMAIN = os.environ.get('CLOUDFRONT_DOMAIN')
MAX_PARALLEL_TASKS = int(os.environ.get('MAX_PARALLEL_TASKS', '5'))


@timed("check_if_file_exists")
def check_if_file_exists(key):
    """Check if a file exists in S3 bucket"""
    try:
        s3.head_object(Bucket=BUCKET_NAME, Key=key)
        return True
    except ClientError:
        return False


@timed("upload_to_s3")
def upload_to_s3(key, data, content_type="text/plain", binary=False):
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
        return f"https://{CLOUDFRONT_DOMAIN}/{key}"
    except Exception as e:
        logging.exception(f"Error uploading to S3: {str(e)}")
        raise


@timed("get_script_content")
def get_script_content(key):
    """Get script content from S3"""
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=key)
        return response['Body'].read().decode('utf-8')
    except ClientError as e:
        logging.exception(f"Error getting script content: {str(e)}")
        raise


@timed("generate_tour_content")
def generate_tour_content(place_id, tour_type, place_details):
    """
    Generate tour content (script and audio) for a place
    
    Args:
        place_id (str): Google Place ID
        tour_type (str): Type of tour
        place_details (dict): Place details from Google Places API
        
    Returns:
        dict: Tour content data
    """
    # Initialize services
    content_service = ContentService()
    tts_service = TTSService()
    
    # Define file keys
    script_key = f"scripts/{place_id}_{tour_type}.txt"
    audio_key = f"audio/{place_id}_{tour_type}.mp3"
    
    # Check if script exists in S3
    script_exists = check_if_file_exists(script_key)
    
    # Generate or retrieve script
    if script_exists:
        logging.info(f"Script already exists for place_id: {place_id}, tour_type: {tour_type}")
        script = get_script_content(script_key)
        script_url = f"https://{CLOUDFRONT_DOMAIN}/{script_key}"
    else:
        logging.info(f"Generating new script for place_id: {place_id}, tour_type: {tour_type}")
        
        # Generate script using OpenAI
        with timed_operation("script_generation"):
            script = content_service.generate_script(place_details, tour_type)
        
        # Upload script to S3
        script_url = upload_to_s3(script_key, script, content_type="text/plain")
        logging.info(f"Script uploaded to: {script_url}")
    
    # Check if audio exists in S3
    audio_exists = check_if_file_exists(audio_key)
    
    # Generate or retrieve audio
    if audio_exists:
        logging.info(f"Audio already exists for place_id: {place_id}, tour_type: {tour_type}")
        audio_url = f"https://{CLOUDFRONT_DOMAIN}/{audio_key}"
    else:
        logging.info(f"Generating new audio for place_id: {place_id}, tour_type: {tour_type}")
        
        # Generate audio using AWS Polly
        with timed_operation("audio_generation"):
            audio_url = tts_service.generate_audio(script, place_id, tour_type)
        
        logging.info(f"Audio generated and uploaded to: {audio_url}")
    
    # Return content data
    return {
        "script": script,
        "script_url": script_url,
        "audio_url": audio_url
    }


@timed("process_place_photos")
def process_place_photos(place_id):
    """
    Process and cache photos for a place
    
    Args:
        place_id (str): Google Place ID
        
    Returns:
        list: Photo URLs
    """
    photo_service = PhotoService()
    
    # Get cached photos or retrieve new ones
    with timed_operation("photo_retrieval"):
        photo_urls = photo_service.get_cached_photo_urls(place_id)
        
        if not photo_urls:
            logging.info(f"No cached photos found for place_id: {place_id}, fetching new ones")
            photo_urls = photo_service.cache_place_photos(place_id)
    
    return photo_urls


@timed("handler")
def handler(event, context):
    """
    Lambda handler for the tour generation API
    
    Expected parameters:
    - placeId: Google Place ID (path parameter)
    - tourType: Type of tour (query parameter)
    """
    # Configure logging
    logger = configure_logging(level=logging.INFO, request_id=getattr(context, 'aws_request_id', None))
    log_event_and_context(event, context)
    
    try:
        # Initialize services
        place_service = PlaceService()
        
        # Start timing
        start_time = time.time()
        
        # Extract parameters
        path_params = event.get('pathParameters', {}) or {}
        query_params = event.get('queryStringParameters', {}) or {}
        
        if 'placeId' not in path_params:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing required parameter: placeId'})
            }
        
        place_id = path_params['placeId']
        tour_type = query_params.get('tourType')
        if not tour_type:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing required parameter: tourType', 'query_params': query_params})
            }
        
        # Check if content is already cached in DynamoDB
        with timed_operation("cache_check"):
            cache_hit, cached_data = place_service.check_cached_content(place_id, tour_type)
        
        if cache_hit and cached_data:
            logger.info(f"Returning cached content for place_id: {place_id}, tour_type: {tour_type}")
            # Log metrics summary before returning
            metrics.log_summary()
            return {
                'statusCode': 200,
                'body': json.dumps(cached_data)
            }
        
        # Get place details from Google Places API
        with timed_operation("place_details_retrieval"):
            place_details = place_service.get_place_details(place_id)
        
        if not place_details:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Place details not found'})
            }
        
        # Process tasks in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_PARALLEL_TASKS) as executor:
            # Start photo processing in parallel
            photos_future = executor.submit(process_place_photos, place_id)
            
            # Generate tour content (script and audio)
            tour_content = generate_tour_content(place_id, tour_type, place_details)
            
            # Wait for photo processing to complete
            photos = photos_future.result()
        
        # Prepare response data
        response_data = {
            'place_id': place_id,
            'tour_type': tour_type,
            'place_details': place_details,
            'script_url': tour_content['script_url'],
            'audio_url': tour_content['audio_url'],
            'photos': photos,
            'cached': False,
            'generated_at': int(time.time())
        }
        
        # Update content cache in DynamoDB
        with timed_operation("cache_update"):
            place_service.update_content_cache(place_id, tour_type, response_data)
        
        # Calculate total processing time
        total_time = (time.time() - start_time) * 1000
        logger.info(f"Total processing time: {total_time:.2f}ms")
        
        # Log metrics summary
        metrics.log_summary()
        
        return {
            'statusCode': 200,
            'body': json.dumps(response_data)
        }
    
    except Exception as e:
        logger.exception(f"Error in tour generation: {str(e)}")
        traceback_str = traceback.format_exc()
        
        # Log metrics summary even on error
        try:
            metrics.log_summary()
        except Exception:
            pass
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': f"Internal server error: {str(e)}",
                'traceback': traceback_str
            })
        }
