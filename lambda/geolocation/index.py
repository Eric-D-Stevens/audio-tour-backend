import json
import os
import time
import boto3
import requests
from decimal import Decimal
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['PLACES_TABLE_NAME'])

# Google Maps API key
GOOGLE_MAPS_API_KEY = os.environ['GOOGLE_MAPS_API_KEY']
PLACES_API_BASE_URL = 'https://maps.googleapis.com/maps/api/place'

# Default cache expiration (24 hours)
CACHE_TTL = 24 * 60 * 60

def handler(event, context):
    """
    Lambda handler for the geolocation places API.
    
    Expected parameters:
    - lat: Latitude
    - lng: Longitude
    - radius: Search radius in meters (default: 500)
    - tour_type: Type of tour (history, cultural, etc.)
    
    Or for preview mode:
    - city: City name (extracted from path)
    """
    try:
        # Check if this is a preview request (by city) or regular request (by coordinates)
        path_params = event.get('pathParameters', {}) or {}
        query_params = event.get('queryStringParameters', {}) or {}
        
        # Default values
        tour_type = query_params.get('tour_type', 'history')
        radius = query_params.get('radius', '500')
        
        is_preview = 'city' in path_params
        
        if is_preview:
            city = path_params['city']
            return get_city_highlights(city, tour_type)
        else:
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
    """Get nearby places based on coordinates and tour type"""
    
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
    
    # Cache miss or expired - fetch from Google Maps API
    place_types = get_place_types_for_tour(tour_type)
    
    # First search for nearby places
    nearby_url = f"{PLACES_API_BASE_URL}/nearbysearch/json"
    params = {
        'location': f"{lat},{lng}",
        'radius': radius,
        'types': '|'.join(place_types),
        'key': GOOGLE_MAPS_API_KEY
    }
    
    response = requests.get(nearby_url, params=params)
    
    if response.status_code != 200:
        return {
            'statusCode': response.status_code,
            'body': json.dumps({'error': 'Failed to fetch data from Google Places API'})
        }
    
    places_data = response.json()
    
    # Process and enrich the places data
    enriched_places = process_places_data(places_data, tour_type)
    
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

def get_city_highlights(city, tour_type):
    """Get highlight attractions for a specific city (preview mode)"""
    
    # Check cache first with the city as the key
    cache_key = f"city_{city}"
    
    try:
        response = table.get_item(
            Key={
                'placeId': cache_key,
                'tourType': tour_type
            }
        )
        
        if 'Item' in response:
            item = response['Item']
            if 'expiresAt' not in item or item['expiresAt'] > int(time.time()):
                return {
                    'statusCode': 200,
                    'body': json.dumps(item['data'], parse_float=str)
                }
    except Exception as e:
        logger.warning(f"Cache retrieval error: {str(e)}")
    
    # Cache miss or expired - fetch from Google Maps API
    # First, geocode the city to get coordinates
    geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        'address': city,
        'key': GOOGLE_MAPS_API_KEY
    }
    
    response = requests.get(geocode_url, params=params)
    
    if response.status_code != 200:
        return {
            'statusCode': response.status_code,
            'body': json.dumps({'error': 'Failed to geocode city'})
        }
    
    geocode_data = response.json()
    
    if not geocode_data.get('results'):
        return {
            'statusCode': 404,
            'body': json.dumps({'error': 'City not found'})
        }
    
    # Get the city coordinates
    location = geocode_data['results'][0]['geometry']['location']
    lat = location['lat']
    lng = location['lng']
    
    # Search for top attractions in this city
    place_types = get_place_types_for_tour(tour_type)
    text_search_url = f"{PLACES_API_BASE_URL}/textsearch/json"
    
    params = {
        'query': f"top attractions in {city}",
        'type': '|'.join(place_types),
        'key': GOOGLE_MAPS_API_KEY
    }
    
    response = requests.get(text_search_url, params=params)
    
    if response.status_code != 200:
        return {
            'statusCode': response.status_code,
            'body': json.dumps({'error': 'Failed to fetch data from Google Places API'})
        }
    
    places_data = response.json()
    
    # Process and limit to top attractions
    enriched_places = process_places_data(places_data, tour_type)
    top_places = enriched_places['places'][:5]  # Limit to top 5 for preview
    enriched_places['places'] = top_places
    
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
    """Map tour types to relevant Google Places API types"""
    tour_type_mapping = {
        'history': ['museum', 'church', 'hindu_temple', 'mosque', 'synagogue', 'city_hall', 'landmark', 'historic'],
        'cultural': ['art_gallery', 'museum', 'movie_theater', 'tourist_attraction', 'performing_arts_theater'],
        'food': ['restaurant', 'cafe', 'bakery', 'food'],
        'nature': ['park', 'natural_feature', 'campground', 'zoo'],
        'architecture': ['church', 'hindu_temple', 'mosque', 'synagogue', 'city_hall', 'stadium'],
    }
    
    # Default to tourist attractions if tour type not recognized
    return tour_type_mapping.get(tour_type.lower(), ['tourist_attraction'])

def process_places_data(places_data, tour_type):
    """Process and enrich the places data from Google API"""
    places = places_data.get('results', [])
    
    # Filter out places without sufficient information
    processed_places = []
    
    for place in places:
        # Only include places with names and place_ids
        if 'name' in place and 'place_id' in place:
            processed_place = {
                'place_id': place['place_id'],
                'name': place['name'],
                'location': place.get('geometry', {}).get('location', {}),
                'rating': place.get('rating', 0),
                'user_ratings_total': place.get('user_ratings_total', 0),
                'vicinity': place.get('vicinity', ''),
                'types': place.get('types', []),
                'photos': place.get('photos', []),
                'tour_type': tour_type,
                # Flag whether this place has audio content (will be determined by the audio generation service)
                'has_audio': False  
            }
            
            processed_places.append(processed_place)
    
    # Sort by rating (if available) or default order
    processed_places.sort(key=lambda x: (x.get('rating', 0) * min(x.get('user_ratings_total', 0), 1000) / 1000), reverse=True)
    
    return {
        'places': processed_places,
        'count': len(processed_places),
        'tour_type': tour_type
    }