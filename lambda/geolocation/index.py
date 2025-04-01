import json
import os
import time
import boto3
import requests
from decimal import Decimal
import logging
from botocore.exceptions import ClientError

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
    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        if 'SecretString' in response:
            return response['SecretString']
    except ClientError as e:
        logger.error(f"Error retrieving secret {secret_name}: {str(e)}")
        raise e

# Get Google Maps API key from Secrets Manager
def get_google_maps_api_key():
    secret = get_secret(GOOGLE_MAPS_API_KEY_SECRET_NAME)
    # The secret might be a JSON string with key-value pairs
    try:
        secret_dict = json.loads(secret)
        return secret_dict.get('GOOGLE_MAPS_API_KEY', secret)
    except json.JSONDecodeError:
        # If it's not JSON, return the string directly
        return secret

def handler(event, context):
    """
    Lambda handler for the geolocation places API.
    
    Expected parameters:
    - lat: Latitude
    - lng: Longitude
    - radius: Search radius in meters (default: 500)
    - tour_type: Type of tour (history, cultural, etc.)
    """
    try:
        query_params = event.get('queryStringParameters', {}) or {}
        
        # Default values
        tour_type = query_params.get('tour_type', 'history')
        radius = query_params.get('radius', '2000')
        
        # Required parameters for coordinate-based search
        if 'lat' not in query_params or 'lng' not in query_params:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing required parameters: lat and lng'})
            }
        
        lat = query_params['lat']
        lng = query_params['lng']
        
        return get_nearby_places(lat, lng, radius, tour_type)
    
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }

def get_nearby_places(lat, lng, radius, tour_type):
    """Get nearby places based on coordinates and tour type using the new Places API v1"""
    
    # Generate a cache key based on location and tour type
    # We round coordinates to reduce cache fragmentation while maintaining proximity
    rounded_lat = round(float(lat), 4)
    rounded_lng = round(float(lng), 4)
    cache_key = f"{rounded_lat}_{rounded_lng}_{radius}_{tour_type}"
    
    # Check cache first
    try:
        response = table.get_item(
            Key={
                'placeId': cache_key,
                'tourType': tour_type
            }
        )
        
        if 'Item' in response:
            item = response['Item']
            # Check if the cache is still valid
            if 'expiresAt' not in item or item['expiresAt'] > int(time.time()):
                return {
                    'statusCode': 200,
                    'body': json.dumps(item['data'], parse_float=str)
                }
    except Exception as e:
        logger.warning(f"Cache retrieval error: {str(e)}")
    
    # Cache miss or expired - fetch from Google Places API v1
    place_types = get_place_types_for_tour(tour_type)
    
    # Get API key from Secrets Manager
    api_key = get_google_maps_api_key()
    
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
    
    # Determine how many API calls we need to make to reach MAX_RESULTS
    # Each call can return up to 20 results
    max_api_calls = (MAX_RESULTS + 19) // 20  # Ceiling division
    
    for i in range(max_api_calls):
        # If we already have enough results, break
        if len(all_places) >= MAX_RESULTS:
            break
            
        # Calculate how many more results we need
        remaining_results = MAX_RESULTS - len(all_places)
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
        response = requests.post(f"{PLACES_API_BASE_URL}:searchNearby", 
                                headers=headers, 
                                json=payload)
        
        if response.status_code != 200:
            logger.error(f"API error: {response.status_code}, {response.text}")
            # If the first request fails, return error
            if i == 0:
                return {
                    'statusCode': response.status_code,
                    'body': json.dumps({'error': 'Failed to fetch data from Google Places API'})
                }
            # Otherwise, just use what we have so far
            break
        
        result = response.json()
        places = result.get("places", [])
        
        # If no new places found, break
        if not places:
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
    enriched_places = process_places_data(all_places, tour_type)
    
    # Cache the result
    try:
        table.put_item(
            Item={
                'placeId': cache_key,
                'tourType': tour_type,
                'data': json.loads(json.dumps(enriched_places), parse_float=Decimal),
                'expiresAt': int(time.time()) + CACHE_TTL
            }
        )
    except Exception as e:
        logger.warning(f"Cache storage error: {str(e)}")
    
    return {
        'statusCode': 200,
        'body': json.dumps(enriched_places, parse_float=str)
    }



def get_place_types_for_tour(tour_type):
    """Map tour types to relevant Google Places API v1 types"""
    tour_type_mapping = {
        'history': ['historical_place', 'monument', 'historical_landmark', 'cultural_landmark'],
        'cultural': ['art_gallery', 'museum', 'performing_arts_theater', 'cultural_center', 'tourist_attraction'],
        'art': ['art_gallery', 'art_studio', 'sculpture'],
        'nature': ['park', 'national_park', 'state_park', 'botanical_garden', 'garden', 'wildlife_park', 'zoo', 'aquarium'],
        'architecture': ['cultural_landmark', 'monument', 'church', 'hindu_temple', 'mosque', 'synagogue', 'stadium', 'opera_house'],
    }
    
    # Default to tourist attractions if tour type not recognized
    return tour_type_mapping.get(tour_type.lower(), ['tourist_attraction'])

def process_places_data(places, tour_type):
    """Process and enrich the places data from Google Places API v1"""
    processed_places = []
    
    for place in places:
        # Only include places with display names and IDs
        if 'displayName' in place and 'id' in place:
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
    
    # Sort by a combination of rating and popularity
    # This creates an "interestingness" score
    def interestingness_score(place):
        rating = place.get('rating', 0)
        user_count = min(place.get('user_ratings_total', 0), 1000) / 1000  # Normalize to 0-1
        has_description = 1 if 'description' in place else 0
        return (rating * 0.6) + (user_count * 0.3) + (has_description * 0.1)
    
    processed_places.sort(key=interestingness_score, reverse=True)
    
    return {
        'places': processed_places,
        'count': len(processed_places),
        'tour_type': tour_type
    }