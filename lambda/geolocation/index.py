import json
import os
import time
import boto3
import requests
from decimal import Decimal
import logging
import traceback
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['PLACES_TABLE_NAME'])
secrets_client = boto3.client('secretsmanager')

# Secret name for Google Maps API key
GOOGLE_MAPS_API_KEY_SECRET_NAME = os.environ['GOOGLE_MAPS_API_KEY_SECRET_NAME']

# New Google Places API v1 endpoint
PLACES_API_BASE_URL = 'https://places.googleapis.com/v1/places'

# Default cache expiration (24 hours)
CACHE_TTL = 24 * 60 * 60

# Maximum number of results to fetch with pagination
MAX_RESULTS = 100

# Function to retrieve secret from AWS Secrets Manager
def get_secret(secret_name):
    logger.info(f"Retrieving secret: {secret_name}")
    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        if 'SecretString' in response:
            logger.info(f"Successfully retrieved secret: {secret_name}")
            return response['SecretString']
        else:
            logger.warning(f"Secret {secret_name} does not contain SecretString")
            return None
    except ClientError as e:
        logger.error(f"Error retrieving secret {secret_name}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise e

# Get Google Maps API key from Secrets Manager
def get_google_maps_api_key():
    logger.info(f"Getting Google Maps API key from secret: {GOOGLE_MAPS_API_KEY_SECRET_NAME}")
    try:
        secret = get_secret(GOOGLE_MAPS_API_KEY_SECRET_NAME)
        if not secret:
            logger.error("Retrieved empty secret for Google Maps API key")
            return None
            
        # The secret might be a JSON string with key-value pairs
        try:
            secret_dict = json.loads(secret)
            api_key = secret_dict.get('GOOGLE_MAPS_API_KEY', secret)
            logger.info("Successfully parsed API key from JSON secret")
            return api_key
        except json.JSONDecodeError:
            # If it's not JSON, return the string directly
            logger.info("Secret is not in JSON format, using as raw string")
            return secret
    except Exception as e:
        logger.error(f"Unexpected error getting Google Maps API key: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise

def handler(event, context):
    """
    Lambda handler for the geolocation places API.
    
    Expected parameters:
    - lat: Latitude
    - lng: Longitude
    - radius: Search radius in meters (default: 500)
    - tour_type: Type of tour (history, cultural, etc.)
    - max_results: Maximum number of places to return (default: 5)
    """
    logger.info(f"Received event: {json.dumps(event)}")
    try:
        query_params = event.get('queryStringParameters', {}) or {}
        logger.info(f"Query parameters: {query_params}")
        
        # Default values
        tour_type = query_params.get('tour_type', 'history')
        radius = query_params.get('radius', '2000')
        max_results = int(query_params.get('max_results', '5'))
        logger.info(f"Using tour_type: {tour_type}, radius: {radius}, max_results: {max_results}")
        
        # Required parameters for coordinate-based search
        if 'lat' not in query_params or 'lng' not in query_params:
            logger.warning("Missing required parameters: lat and lng")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing required parameters: lat and lng'})
            }
        
        lat = query_params['lat']
        lng = query_params['lng']
        logger.info(f"Coordinates: lat={lat}, lng={lng}")
        
        return get_nearby_places(lat, lng, radius, tour_type, max_results)
    
    except Exception as e:
        error_traceback = traceback.format_exc()
        logger.error(f"Error processing request: {str(e)}")
        logger.error(f"Traceback: {error_traceback}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error', 
                'details': str(e),
                'traceback': error_traceback.split('\n')
            })
        }

def get_nearby_places(lat, lng, radius, tour_type, max_results=5):
    """Get nearby places based on coordinates and tour type using the new Places API v1"""
    logger.info(f"Starting get_nearby_places with lat={lat}, lng={lng}, radius={radius}, tour_type={tour_type}, max_results={max_results}")
    
    # Generate a cache key based on location and tour type
    # We round coordinates to reduce cache fragmentation while maintaining proximity
    try:
        rounded_lat = round(float(lat), 4)
        rounded_lng = round(float(lng), 4)
        cache_key = f"{rounded_lat}_{rounded_lng}_{radius}_{tour_type}"
        logger.info(f"Generated cache key: {cache_key}")
    except ValueError as e:
        logger.error(f"Error converting coordinates to float: {str(e)}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid coordinates format', 'details': str(e)})
        }
    
    # Check cache first
    try:
        logger.info(f"Checking cache for key: {cache_key}, tourType: {tour_type}")
        response = table.get_item(
            Key={
                'placeId': cache_key,
                'tourType': tour_type
            }
        )
        
        if 'Item' in response:
            item = response['Item']
            logger.info(f"Cache hit for key: {cache_key}")
            # Check if the cache is still valid
            current_time = int(time.time())
            if 'expiresAt' not in item:
                logger.info("No expiration time in cache item, using cached data")
                return {
                    'statusCode': 200,
                    'body': item['data']
                }
            elif item['expiresAt'] > current_time:
                logger.info(f"Cache valid until {item['expiresAt']} (current time: {current_time})")
                return {
                    'statusCode': 200,
                    'body': item['data']
                }
            else:
                logger.info(f"Cache expired at {item['expiresAt']} (current time: {current_time})")
        else:
            logger.info(f"Cache miss for key: {cache_key}")
    except Exception as e:
        logger.error(f"Cache retrieval error: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
    
    # Cache miss or expired - fetch from Google Places API v1
    logger.info(f"Fetching place types for tour type: {tour_type}")
    try:
        place_types = get_place_types_for_tour(tour_type)
        logger.info(f"Place types for {tour_type}: {place_types}")
    except Exception as e:
        logger.error(f"Error getting place types: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Error determining place types', 'details': str(e)})
        }
    
    # Get API key from Secrets Manager
    logger.info("Retrieving Google Maps API key from Secrets Manager")
    try:
        api_key = get_google_maps_api_key()
        if not api_key:
            logger.error("Failed to retrieve valid API key")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Failed to retrieve valid API key'})
            }
        logger.info("Successfully retrieved API key")
    except Exception as e:
        logger.error(f"Error retrieving API key: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Error retrieving API key', 'details': str(e)})
        }
    
    # Define the field mask for the response
    field_mask = [
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.types",
        "places.primaryType",
        "places.id",
        "places.photos",
        "places.editorialSummary"
    ]
    
    # Fetch places using the new Places API v1 with pagination
    all_places = []
    
    # Request headers
    headers = {
        'Content-Type': 'application/json',
        'X-Goog-Api-Key': api_key,
        'X-Goog-FieldMask': ','.join(field_mask)
    }
    
    # Determine how many API calls we need to make to reach max_results
    # Each call can return up to 20 results
    max_api_calls = (max_results + 19) // 20  # Ceiling division
    
    for i in range(max_api_calls):
        # If we already have enough results, break
        if len(all_places) >= max_results:
            break
            
        # Calculate how many more results we need
        remaining_results = max_results - len(all_places)
        batch_size = min(20, remaining_results)  # API max is 20 per request
        
        # Request payload
        payload = {
            "includedTypes": place_types,
            "maxResultCount": batch_size,
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": float(lat),
                        "longitude": float(lng)
                    },
                    "radius": float(radius)
                }
            },
            "rankPreference": "POPULARITY"  # Use POPULARITY for most interesting places
        }
        
        # For subsequent requests, increase the radius to find more places
        if i > 0:
            # Increase radius by 50% each time
            payload["locationRestriction"]["circle"]["radius"] = float(radius) * (1.5 ** i)
        
        # Make the POST request
        request_url = f"{PLACES_API_BASE_URL}:searchNearby"
        logger.info(f"Making API request to: {request_url}")
        logger.info(f"Request payload: {json.dumps(payload)}")
        
        try:
            response = requests.post(request_url, headers=headers, json=payload, timeout=10)
            logger.info(f"API response status code: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"API error: {response.status_code}")
                logger.error(f"Response body: {response.text}")
                # If the first request fails, return error
                if i == 0:
                    return {
                        'statusCode': response.status_code,
                        'body': json.dumps({
                            'error': 'Failed to fetch data from Google Places API',
                            'details': response.text
                        })
                    }
                # Otherwise, just use what we have so far
                logger.info("Continuing with places already collected")
                break
        except requests.exceptions.RequestException as e:
            logger.error(f"Request exception: {str(e)}")
            if i == 0:
                return {
                    'statusCode': 500,
                    'body': json.dumps({
                        'error': 'Failed to connect to Google Places API',
                        'details': str(e)
                    })
                }
            logger.info("Continuing with places already collected despite request error")
            break
        
        try:
            result = response.json()
            logger.info(f"Successfully parsed JSON response")
            places = result.get("places", [])
            logger.info(f"Found {len(places)} places in this batch")
            
            # If no new places found, break
            if not places:
                logger.info("No places returned in this batch, stopping pagination")
                break
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {str(e)}")
            logger.error(f"Response content: {response.text[:500]}...")
            if i == 0:
                return {
                    'statusCode': 500,
                    'body': json.dumps({
                        'error': 'Invalid response from Google Places API',
                        'details': str(e)
                    })
                }
            break
            
        # Add new places to our collection
        all_places.extend(places)
        
        # Deduplicate based on place ID
        seen_ids = set()
        unique_places = []
        for place in all_places:
            place_id = place.get("id")
            if place_id and place_id not in seen_ids:
                seen_ids.add(place_id)
                unique_places.append(place)
        
        all_places = unique_places
        
        # Small delay to avoid rate limiting
        if i < max_api_calls - 1:
            time.sleep(0.2)
    
    # Process and enrich the places data
    logger.info(f"Processing {len(all_places)} places")
    try:
        enriched_places = process_places_data(all_places, tour_type)
        logger.info(f"Successfully processed {len(enriched_places)} places")
    except Exception as e:
        logger.error(f"Error processing places data: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Error processing places data',
                'details': str(e),
                'traceback': traceback.format_exc().split('\n')
            })
        }
    
    # Cache the result
    try:
        logger.info(f"Storing results in cache with key: {cache_key}")
        # Store in DynamoDB with TTL
        current_time = int(time.time())
        expiration_time = current_time + CACHE_TTL
        logger.info(f"Setting cache expiration to {expiration_time} (current time: {current_time})")
        
        table.put_item(
            Item={
                'placeId': cache_key,
                'tourType': tour_type,
                'data': json.dumps(enriched_places, default=str),
                'expiresAt': expiration_time,
                'createdAt': current_time
            }
        )
        logger.info("Successfully stored results in cache")
    except Exception as e:
        logger.error(f"Cache storage error: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
    
    # Return the response
    try:
        response_body = json.dumps(enriched_places, default=str)
        logger.info(f"Successfully serialized response, returning 200 status code")
        return {
            'statusCode': 200,
            'body': response_body
        }
    except Exception as e:
        logger.error(f"Error serializing final response: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Error serializing response',
                'details': str(e)
            })
        }



def get_place_types_for_tour(tour_type):
    """Map tour types to relevant Google Places API v1 types"""
    logger.info(f"Mapping tour type '{tour_type}' to place types")
    tour_type_mapping = {
        'history': ['historical_place', 'monument', 'historical_landmark', 'cultural_landmark'],
        'cultural': ['art_gallery', 'museum', 'performing_arts_theater', 'cultural_center', 'tourist_attraction'],
        'art': ['art_gallery', 'art_studio', 'sculpture'],
        'nature': ['park', 'national_park', 'state_park', 'botanical_garden', 'garden', 'wildlife_park', 'zoo', 'aquarium'],
        'architecture': ['cultural_landmark', 'monument', 'church', 'hindu_temple', 'mosque', 'synagogue', 'stadium', 'opera_house'],
    }
    
    # Default to tourist attractions if tour type not recognized
    place_types = tour_type_mapping.get(tour_type.lower(), ['tourist_attraction'])
    logger.info(f"Mapped '{tour_type}' to place types: {place_types}")
    return place_types

def process_places_data(places, tour_type):
    """Process and enrich the places data from Google Places API v1"""
    logger.info(f"Processing {len(places)} places for tour type: {tour_type}")
    processed_places = []
    
    try:
        for i, place in enumerate(places):
            try:
                # Only include places with display names and IDs
                if 'displayName' in place and 'id' in place:
                    logger.debug(f"Processing place {i+1}/{len(places)}: {place.get('displayName', {}).get('text', 'Unknown')}")
                    
                    # Extract location data
                    location = {}
                    if 'location' in place:
                        location = {
                            'lat': place['location'].get('latitude', 0),
                            'lng': place['location'].get('longitude', 0)
                        }
                    
                    # Extract photo references
                    photos = []
                    if 'photos' in place:
                        logger.debug(f"Place has {len(place['photos'])} photos")
                        for photo in place['photos']:
                            if 'name' in photo:
                                photos.append({
                                    'photo_reference': photo['name'],
                                    'width': photo.get('width', 0),
                                    'height': photo.get('height', 0)
                                })
                    
                    # Create processed place object
                    processed_place = {
                        'place_id': place['id'],
                        'name': place['displayName'].get('text', ''),
                        'location': location,
                        'rating': place.get('rating', 0),
                        'user_ratings_total': place.get('userRatingCount', 0),
                        'vicinity': place.get('formattedAddress', ''),
                        'types': place.get('types', []),
                        'primary_type': place.get('primaryType', ''),
                        'photos': photos,
                        'tour_type': tour_type,
                        # Flag whether this place has audio content (will be determined by the audio generation service)
                        'has_audio': False
                    }
                    
                    # Add editorial summary if available
                    if 'editorialSummary' in place:
                        processed_place['description'] = place['editorialSummary'].get('text', '')
                    
                    processed_places.append(processed_place)
                    logger.debug(f"Successfully processed place: {processed_place['name']}")
                else:
                    logger.warning(f"Skipping place without required fields: {place.get('id', 'Unknown ID')}")
            except Exception as e:
                logger.error(f"Error processing place {i}: {str(e)}")
                logger.error(f"Problematic place data: {json.dumps(place)[:500]}...")
                # Continue with next place instead of failing the entire batch
                continue
        
        # Sort by a combination of rating and popularity
        # This creates an "interestingness" score
        logger.info(f"Sorting {len(processed_places)} processed places by interestingness score")
        try:
            def interestingness_score(place):
                rating = place.get('rating', 0)
                user_count = min(place.get('user_ratings_total', 0), 1000) / 1000  # Normalize to 0-1
                has_description = 1 if 'description' in place else 0
                return (rating * 0.6) + (user_count * 0.3) + (has_description * 0.1)
            
            processed_places.sort(key=interestingness_score, reverse=True)
            logger.info(f"Successfully sorted places")
        except Exception as e:
            logger.error(f"Error sorting places: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Continue without sorting if there's an error
        
        result = {
            'places': processed_places,
            'count': len(processed_places),
            'tour_type': tour_type
        }
        logger.info(f"Returning {len(processed_places)} processed places")
        return result
        
    except Exception as e:
        logger.error(f"Unexpected error in process_places_data: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise