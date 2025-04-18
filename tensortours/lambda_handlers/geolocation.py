"""
Geolocation Lambda handler for TensorTours backend.
Handles nearby place search requests using the Google Places API.
"""
import json
import logging
import os
from typing import Dict, Any, List

import boto3
import requests

from tensortours.services.places import PlacesService

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
PLACES_TABLE_NAME = os.environ.get('PLACES_TABLE_NAME', 'tensortours-places')
places_table = dynamodb.Table(PLACES_TABLE_NAME)


def handler(event, context):
    """
    Lambda handler for geolocation service.
    
    Expected request format:
    {
        "latitude": float,
        "longitude": float,
        "radius": int (meters),
        "types": ["point_of_interest", "tourist_attraction", ...] (optional)
    }
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    # API Gateway proxy integration
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
    try:
        latitude = float(body.get('latitude'))
        longitude = float(body.get('longitude'))
        radius = int(body.get('radius', 1000))  # Default 1km
        types = body.get('types', ["tourist_attraction", "museum", "park", "church", "historic"])
    except (ValueError, TypeError):
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid parameters'})
        }
    
    try:
        # First check if we have cached results
        cached_results = get_cached_places(latitude, longitude, radius, types)
        if cached_results:
            logger.info(f"Returning {len(cached_results)} cached places")
            return {
                'statusCode': 200,
                'body': json.dumps({'places': cached_results})
            }
        
        # No cached results, query Google Places API
        places_service = PlacesService()
        results = search_nearby_places(places_service, latitude, longitude, radius, types)
        
        # Cache results
        cache_places(results, latitude, longitude, radius, types)
        
        return {
            'statusCode': 200,
            'body': json.dumps({'places': results})
        }
        
    except Exception as e:
        logger.exception(f"Error processing request: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }


def search_nearby_places(places_service: PlacesService, latitude: float, longitude: float, 
                        radius: int, types: List[str]) -> List[Dict[str, Any]]:
    """Search for nearby places using Google Places API."""
    api_key = places_service.get_api_key()
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    
    # Prepare parameters
    params = {
        "location": f"{latitude},{longitude}",
        "radius": radius,
        "type": "|".join(types),
        "key": api_key
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    
    if data['status'] != 'OK' and data['status'] != 'ZERO_RESULTS':
        logger.error(f"Google Places API error: {data['status']}")
        if 'error_message' in data:
            logger.error(f"Error message: {data['error_message']}")
        raise Exception(f"Google Places API returned error: {data['status']}")
    
    # Process and normalize results
    results = []
    for place in data.get('results', []):
        results.append({
            'place_id': place.get('place_id'),
            'name': place.get('name'),
            'vicinity': place.get('vicinity'),
            'location': {
                'lat': place.get('geometry', {}).get('location', {}).get('lat'),
                'lng': place.get('geometry', {}).get('location', {}).get('lng')
            },
            'types': place.get('types', []),
            'rating': place.get('rating'),
            'user_ratings_total': place.get('user_ratings_total'),
            'photos': place.get('photos', [])
        })
    
    return results


def get_cached_places(latitude: float, longitude: float, radius: int, 
                    types: List[str]) -> List[Dict[str, Any]]:
    """Check for cached places in DynamoDB."""
    if not PLACES_TABLE_NAME:
        return []
    
    # Create a cache key
    cache_key = f"{latitude:.3f},{longitude:.3f},{radius},{','.join(sorted(types))}"
    
    try:
        response = places_table.get_item(Key={'cache_key': cache_key})
        if 'Item' in response:
            item = response['Item']
            # Check if cache is still valid (24 hours)
            return item.get('places', [])
    except Exception as e:
        logger.exception(f"Error retrieving from cache: {str(e)}")
    
    return []


def cache_places(places: List[Dict[str, Any]], latitude: float, longitude: float, 
                radius: int, types: List[str]) -> bool:
    """Cache places in DynamoDB."""
    if not PLACES_TABLE_NAME or not places:
        return False
    
    # Create a cache key
    cache_key = f"{latitude:.3f},{longitude:.3f},{radius},{','.join(sorted(types))}"
    
    try:
        places_table.put_item(
            Item={
                'cache_key': cache_key,
                'latitude': latitude,
                'longitude': longitude,
                'radius': radius,
                'types': types,
                'places': places,
                'timestamp': int(boto3.client('dynamodb').meta.config.credentials.expiry_time.timestamp())
            }
        )
        return True
    except Exception as e:
        logger.exception(f"Error caching places: {str(e)}")
        return False
