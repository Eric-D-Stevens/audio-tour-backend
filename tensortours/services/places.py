"""Google Places API service for TensorTours backend."""
import os
import json
import logging
import boto3
from typing import Dict, List, Optional, Any

import requests
from botocore.exceptions import ClientError

from tensortours.models.place import PlaceDetails, PlacePhoto

logger = logging.getLogger(__name__)


class PlacesService:
    """Service for interacting with Google Places API."""
    
    def __init__(self, api_key: Optional[str] = None, secrets_client=None, s3_client=None):
        """Initialize the Places service.
        
        Args:
            api_key: Optional Google Maps API key (will be fetched from Secrets Manager if not provided)
            secrets_client: Optional boto3 Secrets Manager client
            s3_client: Optional boto3 S3 client
        """
        self.api_key = api_key
        self._secrets_client = secrets_client or boto3.client('secretsmanager')
        self._s3_client = s3_client or boto3.client('s3')
        self.bucket_name = os.environ.get('CONTENT_BUCKET_NAME')
        self.cloudfront_domain = os.environ.get('CLOUDFRONT_DOMAIN')
        self.places_api_base_url = 'https://places.googleapis.com/v1/places'
        
    def get_api_key(self) -> str:
        """Get Google Maps API key from environment or Secrets Manager."""
        if self.api_key:
            return self.api_key
            
        secret_name = os.environ.get('GOOGLE_MAPS_API_KEY_SECRET_NAME')
        if not secret_name:
            raise ValueError("GOOGLE_MAPS_API_KEY_SECRET_NAME not set in environment")
            
        try:
            response = self._secrets_client.get_secret_value(SecretId=secret_name)
            if 'SecretString' in response:
                secret = response['SecretString']
                try:
                    secret_dict = json.loads(secret)
                    self.api_key = secret_dict.get('GOOGLE_MAPS_API_KEY', secret)
                except json.JSONDecodeError:
                    self.api_key = secret
                return self.api_key
        except ClientError as e:
            logger.exception(f"Error retrieving secret {secret_name}")
            raise e
    
    def get_place_details(self, place_id: str) -> PlaceDetails:
        """Get details for a place from Google Places API v1.
        
        Args:
            place_id: The Google Place ID
            
        Returns:
            PlaceDetails object with place information
        """
        api_key = self.get_api_key()
        
        # Define the fields we want to get
        fields = [
            "name",
            "formattedAddress",
            "location",
            "photos",
            "types",
            "rating",
            "websiteUri",
            "formattedPhoneNumber",
            "regularOpeningHours",
            "priceLevel",
            "editorialSummary",
            "reviews",
        ]
        
        url = f"{self.places_api_base_url}/{place_id}"
        headers = {
            'Content-Type': 'application/json',
            'X-Goog-Api-Key': api_key,
            'X-Goog-FieldMask': ','.join(fields)
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # Convert Google Places API v1 response to our model
        place_data = {
            'place_id': place_id,
            'name': data.get('name', ''),
            'formatted_address': data.get('formattedAddress', ''),
            'location': {
                'lat': data.get('location', {}).get('latitude', 0),
                'lng': data.get('location', {}).get('longitude', 0)
            },
            'types': data.get('types', []),
            'rating': data.get('rating'),
            'website': data.get('websiteUri'),
            'formatted_phone_number': data.get('formattedPhoneNumber'),
            'price_level': data.get('priceLevel'),
        }
        
        # Handle photos if present
        if 'photos' in data:
            place_data['photos'] = [
                {
                    'photo_reference': photo.get('name', ''),
                    'height': photo.get('heightPx', 0),
                    'width': photo.get('widthPx', 0),
                    'html_attributions': photo.get('authorAttributions', []),
                }
                for photo in data.get('photos', [])
            ]
        
        # Parse other fields as needed
        if 'editorialSummary' in data:
            place_data['editorial_summary'] = data['editorialSummary'].get('text', '')
        
        if 'reviews' in data:
            place_data['reviews'] = data.get('reviews', [])
            
        return PlaceDetails(**place_data)
    
    def get_place_photos(self, place_id: str) -> List[str]:
        """Get photo URLs for a place, either from cache or Google Places API.
        
        Args:
            place_id: The Google Place ID
            
        Returns:
            List of photo URLs
        """
        # First check if photos are already cached
        cached_urls = self._get_cached_photo_urls(place_id)
        if cached_urls:
            return cached_urls
            
        # If not cached, fetch and cache them
        return self.cache_place_photos(place_id)
    
    def _get_cached_photo_urls(self, place_id: str) -> List[str]:
        """Get CloudFront URLs for cached photos.
        
        Args:
            place_id: The Google Place ID
            
        Returns:
            List of CloudFront URLs for cached photos
        """
        if not self.bucket_name or not self.cloudfront_domain:
            return []
            
        photo_urls = []
        photo_dir = f"photos/{place_id}"
        idx = 0
        
        while True:
            photo_key = f"{photo_dir}/{idx}.jpg"
            if not self._check_if_file_exists(photo_key):
                break
            photo_urls.append(f"https://{self.cloudfront_domain}/{photo_key}")
            idx += 1
        
        return photo_urls
    
    def _check_if_file_exists(self, key: str) -> bool:
        """Check if a file exists in S3 bucket.
        
        Args:
            key: S3 object key
            
        Returns:
            True if file exists, False otherwise
        """
        if not self.bucket_name:
            return False
            
        try:
            self._s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            else:
                logger.exception(f"Error checking if file exists: {key}")
                return False
    
    def cache_place_photos(self, place_id: str) -> List[str]:
        """Cache photos for a place and return CloudFront URLs.
        
        Args:
            place_id: The Google Place ID
            
        Returns:
            List of CloudFront URLs for cached photos
        """
        if not self.bucket_name or not self.cloudfront_domain:
            logger.warning("S3 bucket or CloudFront domain not configured. Cannot cache photos.")
            return []
            
        place_details = self.get_place_details(place_id)
        if not place_details.photos:
            logger.info(f"No photos found for place {place_id}")
            return []
            
        api_key = self.get_api_key()
        photo_urls = []
        
        # Cache each photo
        for i, photo in enumerate(place_details.photos):
            try:
                # Google Places API v1 photo reference format
                photo_url = f"https://places.googleapis.com/v1/{photo.photo_reference}/media?key={api_key}&maxHeightPx=1200&maxWidthPx=1200"
                response = requests.get(photo_url)
                response.raise_for_status()
                
                # Save to S3
                photo_key = f"photos/{place_id}/{i}.jpg"
                self._s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=photo_key,
                    Body=response.content,
                    ContentType='image/jpeg'
                )
                
                # Add CloudFront URL
                photo_urls.append(f"https://{self.cloudfront_domain}/{photo_key}")
                
            except Exception as e:
                logger.exception(f"Error caching photo {i} for place {place_id}")
                continue
                
        return photo_urls
