import requests
from typing import List, Dict


class GooglePlacesClient:

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://places.googleapis.com/v1/places"

        # used for searchNearby - must be prefixed with 'places.'
        self.field_mask = [
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

        # Define fields to include in the place details response
        # Note: For place details, don't prefix with 'places.'
        self.place_details_fields = [
            "displayName",
            "formattedAddress",
            "location",
            "rating",
            "userRatingCount",
            "types",
            "primaryType",
            "editorialSummary",
            "photos",
            "websiteUri",
            "internationalPhoneNumber",
            "currentOpeningHours"
        ]

    def _request(self, method: str, url: str, headers: Dict, data: Dict = None, params: Dict = None) -> Dict:
        """Make a request to the Google Places API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: URL to request
            headers: HTTP headers
            data: JSON data for POST requests
            params: Query parameters for GET requests
            
        Returns:
            JSON response from the API
        """
        # For GET requests, use params. For POST requests, use json.
        if method.upper() == "GET":
            response = requests.request(method, url, headers=headers, params=params)
        else:  # POST, PUT, etc.
            response = requests.request(method, url, headers=headers, json=data)
            
        # Check if the response was successful
        if response.status_code != 200:
            # Print the error details
            print(f"Error response from Google Places API: Status {response.status_code}")
            print(f"URL: {url}")
            print(f"Headers: {headers}")
            if method.upper() == "POST" and data:
                import json
                print(f"Request data: {json.dumps(data, indent=2)}")
            try:
                error_details = response.json()
                import json
                print(f"Error details: {json.dumps(error_details, indent=2)}")
            except Exception:
                print(f"Raw response: {response.text}")
        
        response.raise_for_status()
        return response.json()


    def _request_binary(self, method: str, url: str, headers: Dict, params: Dict = None) -> bytes:
        """Make a request to the Google Places API and return binary content.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: URL to request
            headers: HTTP headers
            params: Query parameters for GET requests
            
        Returns:
            Binary content from the API response
        """
        # For GET requests, use params
        response = requests.request(method, url, headers=headers, params=params)
            
        # Check if the response was successful
        if response.status_code != 200:
            # Print the error details
            print(f"Error response from Google Places API: Status {response.status_code}")
            print(f"URL: {url}")
            print(f"Headers: {headers}")
            try:
                error_details = response.json()
                import json
                print(f"Error details: {json.dumps(error_details, indent=2)}")
            except Exception:
                print(f"Raw response: {response.text}")
        
        # Now raise the exception if needed
        response.raise_for_status()
        
        # Return the response with binary data in content field
        return response.content
    

    def search_nearby(
        self,
        latitude: float,
        longitude: float,
        radius: int,
        include_types: List[str],
        exclude_types: List[str],
        language_code: str = "en",
        max_results: int = 20
    ) -> Dict:
        """
        Search for places nearby a given location.

        Args:
            latitude (float): Latitude of the location
            longitude (float): Longitude of the location
            radius (int): Radius in meters
            include_types (List[str]): List of primary types to include
            exclude_types (List[str]): List of primary types to exclude
            language_code (str): Language code for the response

        Returns:
            dict: Response from the Google Places API
        """

        # setup request
        url = f"{self.base_url}:searchNearby"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": ",".join(self.field_mask)  # Use field_mask for search_nearby
        }

        # build the locationRestriction object
        location_restriction = {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude
                },
                "radius": radius
            }
        }

        # build the params object
        payload = {
            "locationRestriction": location_restriction,
            "includedTypes": include_types,
            "excludedTypes": exclude_types,
            "languageCode": language_code,
            "maxResultCount": max_results
        }
        
        return self._request("POST", url, headers, data=payload)


    def get_place_details(self, place_id: str) -> dict:
        """Get details for a place from Google Places API v1."""
        url = f"{self.base_url}/{place_id}"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": ",".join(self.place_details_fields)  # Use place_details_fields for get_place_details
        }
        
        return self._request("GET", url, headers)

    def get_place_photo(
        self,
        photo_reference: str,
        max_height_px: int = 400,
        max_width_px: int = 400
    ) -> bytes:
        """
        Get photo binary data for a place from Google Places API v1.

        Args:
            photo_reference (str): The photo reference from place details
                                   Format: places/{place_id}/photos/{photo_id}
            max_height_px (int): Maximum height of the photo in pixels
            max_width_px (int): Maximum width of the photo in pixels

        Returns:
            bytes: Binary image data from the API
        """
        # According to the documentation, the format should be:
        # https://places.googleapis.com/v1/NAME/media?key=API_KEY&PARAMETERS
        
        # The base API URL without the 'places' part
        base_api_url = "https://places.googleapis.com/v1"
        
        # Construct the URL with the photo reference and /media suffix
        url = f"{base_api_url}/{photo_reference}/media"
        
        headers = {
            "Accept": "image/*",  # Accept image content
            "X-Goog-Api-Key": self.api_key
        }
        
        params = {
            "maxHeightPx": max_height_px,
            "maxWidthPx": max_width_px,
        }
        
        # Use the binary request method
        return self._request_binary("GET", url, headers, params=params)