import json
import os
import boto3
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
lambda_client = boto3.client('lambda')

# City coordinates for preview mode
CITY_COORDINATES = {
    'san-francisco': {'lat': 37.7749, 'lng': -122.4194},
    'new-york': {'lat': 40.7128, 'lng': -74.0060},
    'london': {'lat': 51.5074, 'lng': -0.1278},
    'paris': {'lat': 48.8566, 'lng': 2.3522},
    'tokyo': {'lat': 35.6762, 'lng': 139.6503},
    'rome': {'lat': 41.9028, 'lng': 12.4964}
}

def invoke_lambda(function_name, payload):
    """Invoke another Lambda function directly"""
    try:
        logger.info(f"Invoking Lambda: {function_name} with payload: {json.dumps(payload)}")
        
        # Invoke the Lambda function
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        # Process the response
        if response['StatusCode'] == 200:
            payload = json.loads(response['Payload'].read().decode())
            logger.info(f"Lambda response: {json.dumps(payload)}")
            return payload
        else:
            logger.error(f"Lambda invocation failed: {response}")
            return None
    except Exception as e:
        logger.error(f"Error invoking Lambda {function_name}: {str(e)}")
        return None

def create_api_gateway_event(path, method, query_params=None, path_params=None, body=None):
    """Create a mock API Gateway event"""
    event = {
        "resource": path,
        "path": path,
        "httpMethod": method,
        "headers": {
            "Accept": "*/*",
            "Content-Type": "application/json"
        },
        "queryStringParameters": query_params or {},
        "pathParameters": path_params or {},
        "body": json.dumps(body) if body else None,
        "isBase64Encoded": False
    }
    return event

def get_city_preview(city_name, tour_type="history"):
    """Get preview data for a specific city"""
    logger.info(f"Getting preview for city: {city_name}, tour type: {tour_type}")
    
    # Get coordinates for the city
    city_id = city_name.lower().replace(" ", "-")
    coordinates = CITY_COORDINATES.get(city_id)
    
    if not coordinates:
        logger.warning(f"City not found: {city_name}. Using San Francisco as default.")
        coordinates = CITY_COORDINATES['san-francisco']
    
    # Create API Gateway event for geolocation Lambda
    event = create_api_gateway_event(
        "/places",
        "GET",
        query_params={
            "lat": str(coordinates['lat']),
            "lng": str(coordinates['lng']),
            "radius": "10000",
            "tour_type": tour_type,
            "max_results": "30"
        }
    )
    
    # Invoke the geolocation Lambda function
    logger.info(f"Invoking geolocation Lambda with event: {json.dumps(event)}")
    response = invoke_lambda("tensortours-geolocation", event)
    
    # Process the response
    if isinstance(response, dict) and 'statusCode' in response and response['statusCode'] == 200:
        try:
            body = json.loads(response['body'])
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps({
                    "city": city_name,
                    "places": body.get("places", []),
                    "tour_type": tour_type
                })
            }
        except Exception as e:
            logger.error(f"Error processing geolocation response: {str(e)}")
    
    # Return error if something went wrong
    return {
        "statusCode": response.get("statusCode", 500),
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": response.get("body", json.dumps({"error": "Failed to get city preview"}))
    }

def get_preview_audio(place_id, tour_type="history"):
    """Get preview audio for a specific place"""
    logger.info(f"Getting preview audio for place: {place_id}, tour type: {tour_type}")
    
    # Create API Gateway event for audio-generation Lambda
    event = create_api_gateway_event(
        "/audio/{placeId}",
        "GET",
        query_params={"tourType": tour_type},
        path_params={"placeId": place_id}
    )
    
    # Invoke the audio-generation Lambda function
    logger.info(f"Invoking audio-generation Lambda with event: {json.dumps(event)}")
    response = invoke_lambda("tensortours-audio-generation", event)
    
    # Return the response directly
    return response

def lambda_handler(event, context):
    """Main handler for the tour-preview Lambda"""
    logger.info(f"Received event: {json.dumps(event)}")
    
    try:
        # Extract path and method from the event
        path = event.get("path", "")
        method = event.get("httpMethod", "GET")
        
        # Route the request based on the path
        if path.startswith("/preview/"):
            # Extract city name from path
            parts = path.split("/")
            if len(parts) >= 3:
                city_name = parts[2]
                
                # Get query parameters
                query_params = event.get("queryStringParameters", {}) or {}
                tour_type = query_params.get("tour_type", "history")
                
                return get_city_preview(city_name, tour_type)
                
        elif path.startswith("/preview/audio/"):
            # Extract place ID from path
            parts = path.split("/")
            if len(parts) >= 4:
                place_id = parts[3]
                
                # Get query parameters
                query_params = event.get("queryStringParameters", {}) or {}
                tour_type = query_params.get("tourType", "history")
                
                return get_preview_audio(place_id, tour_type)
        
        # Default response for unrecognized paths
        return {
            "statusCode": 404,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"error": "Not found"})
        }
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"error": f"Internal server error: {str(e)}"})
        }


# Functions for testing/script usage

def test_city_preview(city_name, tour_type="history"):
    """
    Test function to get preview data for a city
    
    Args:
        city_name (str): Name of the city to get preview data for
        tour_type (str): Type of tour (history, cultural, etc.)
        
    Returns:
        dict: Preview data for the city
    """
    # Create a mock API Gateway event
    event = {
        "path": f"/preview/{city_name}",
        "httpMethod": "GET",
        "queryStringParameters": {"tour_type": tour_type}
    }
    
    # Call the Lambda handler
    response = lambda_handler(event, {})
    
    # Return the parsed response body
    if response.get("statusCode") == 200:
        return json.loads(response.get("body", "{}"))
    else:
        print(f"Error: {response.get('statusCode')} - {response.get('body')}")
        return None


def test_place_audio(place_id, tour_type="history"):
    """
    Test function to get audio data for a place
    
    Args:
        place_id (str): ID of the place to get audio for
        tour_type (str): Type of tour (history, cultural, etc.)
        
    Returns:
        dict: Audio data for the place
    """
    # Create a mock API Gateway event
    event = {
        "path": f"/preview/audio/{place_id}",
        "httpMethod": "GET",
        "queryStringParameters": {"tourType": tour_type}
    }
    
    # Call the Lambda handler
    response = lambda_handler(event, {})
    
    # Return the parsed response body
    if response.get("statusCode") == 200:
        return json.loads(response.get("body", "{}"))
    else:
        print(f"Error: {response.get('statusCode')} - {response.get('body')}")
        return None


# Main function for script execution
if __name__ == "__main__":
    import argparse
    import pprint
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Test TensorTours preview functionality')
    parser.add_argument('--city', type=str, default='san-francisco', help='City name to preview')
    parser.add_argument('--tour-type', type=str, default='history', help='Tour type')
    parser.add_argument('--place-id', type=str, help='Place ID for audio preview')
    args = parser.parse_args()
    
    # Configure pretty printer
    pp = pprint.PrettyPrinter(indent=2)
    
    # Test based on provided arguments
    if args.place_id:
        print(f"\nGetting audio preview for place {args.place_id} with tour type {args.tour_type}...\n")
        result = test_place_audio(args.place_id, args.tour_type)
        if result:
            pp.pprint(result)
    else:
        print(f"\nGetting city preview for {args.city} with tour type {args.tour_type}...\n")
        result = test_city_preview(args.city, args.tour_type)
        if result:
            # Print city info
            print(f"City: {result.get('city')}")
            print(f"Tour type: {result.get('tour_type')}")
            print(f"Found {len(result.get('places', []))} places\n")
            
            # Print place details
            for i, place in enumerate(result.get('places', [])):
                print(f"Place {i+1}: {place.get('name')}")
                print(f"  ID: {place.get('place_id')}")
                print(f"  Location: {place.get('location', {})}")
                print(f"  Rating: {place.get('rating', 'N/A')}")
                print(f"  Types: {', '.join(place.get('types', []))}\n")
                
            # If places were found, suggest testing audio for the first place
            if result.get('places'):
                first_place = result.get('places')[0]
                place_id = first_place.get('place_id')
                print(f"\nTo test audio for {first_place.get('name')}, run:")
                print(f"python {os.path.basename(__file__)} --place-id {place_id} --tour-type {args.tour_type}")
