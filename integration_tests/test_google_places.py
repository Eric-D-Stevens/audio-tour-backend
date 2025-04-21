import json
import os

import pytest
import requests
from dotenv import load_dotenv

from tensortours.services.google_places import GooglePlacesClient

# Load environment variables from .env file
load_dotenv()


@pytest.fixture
def google_places_client():
    """Fixture to create a GooglePlacesClient instance"""
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        pytest.skip("GOOGLE_MAPS_API_KEY environment variable not found")
    return GooglePlacesClient(api_key)


def test_search_nearby(google_places_client):
    """Test the search_nearby method"""
    # Golden Gate Park, San Francisco coordinates
    latitude = 37.7694
    longitude = -122.4862

    # Search for tourist attractions and museums within 1500 meters
    results = google_places_client.search_nearby(
        latitude=latitude,
        longitude=longitude,
        radius=1500,
        include_types=["tourist_attraction", "museum"],
        exclude_types=[],
        max_results=5,
    )

    # Verify the response structure
    assert isinstance(results, dict)
    assert "places" in results
    assert isinstance(results["places"], list)

    # Check that we got some results
    places = results.get("places", [])
    assert len(places) > 0, "No places found"

    # Check the first place has the expected fields
    place = places[0]
    assert "displayName" in place
    assert "id" in place
    assert "formattedAddress" in place

    # Print some information about the first place
    place_id = place.get("id")
    display_name = place.get("displayName", {}).get("text", "Unknown")
    print(f"\nFound place: {display_name} (ID: {place_id})")

    # Return the place_id for other tests to use
    return place_id


def test_get_place_details(google_places_client):
    """Test the get_place_details method"""
    # First get a place_id by searching
    place_id = test_search_nearby(google_places_client)

    try:
        # Get details for the place
        details = google_places_client.get_place_details(place_id)

        # Verify the response structure
        assert isinstance(details, dict)
        assert "displayName" in details
        assert "formattedAddress" in details

        # Print some details
        print(f"\nDetails for place {place_id}:")
        print(f"Name: {details.get('displayName', {}).get('text', 'Unknown')}")
        print(f"Address: {details.get('formattedAddress', 'N/A')}")

    except requests.exceptions.HTTPError as e:
        # Print the full error response
        print(f"\nHTTP Error: {e}")

        # Get the response object from the exception
        response = e.response
        print(f"Status code: {response.status_code}")

        # Try to parse and print the error response body
        try:
            error_details = response.json()
            print(f"Error details: {json.dumps(error_details, indent=2)}")
        except Exception:
            print(f"Raw response: {response.text}")

        # Re-raise the exception
        raise


def test_get_place_photo(google_places_client):
    """Test the get_place_photo method"""
    # First get a place with details to extract photo references
    place_id = test_search_nearby(google_places_client)

    try:
        # Get details for the place to get photo references
        details = google_places_client.get_place_details(place_id)

        # Check if the place has photos
        if "photos" not in details or not details["photos"]:
            pytest.skip("No photos available for this place")

        # Get the first photo reference
        photo_reference = details["photos"][0]["name"]
        print(f"\nFound photo reference: {photo_reference}")

        # Get the photo data
        photo_data = google_places_client.get_place_photo(photo_reference)

        # Verify the response structure
        assert isinstance(photo_data, dict)
        assert "mediaItems" in photo_data, "No mediaItems in response"
        assert len(photo_data["mediaItems"]) > 0, "Empty mediaItems list"

        # Check the first media item
        media_item = photo_data["mediaItems"][0]
        assert "name" in media_item

        # Print some information about the photo
        print(f"Photo name: {media_item.get('name')}")
        if "uri" in media_item:
            print(f"Photo URI: {media_item.get('uri')}")

    except requests.exceptions.HTTPError as e:
        # Print the full error response
        print(f"\nHTTP Error: {e}")

        # Get the response object from the exception
        response = e.response
        print(f"Status code: {response.status_code}")

        # Try to parse and print the error response body
        try:
            error_details = response.json()
            print(f"Error details: {json.dumps(error_details, indent=2)}")
        except Exception:
            print(f"Raw response: {response.text}")

        # Re-raise the exception
        raise
    except Exception as e:
        print(f"Exception: {e}")
        raise
