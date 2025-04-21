import os
from functools import lru_cache

from ..services.google_places import GooglePlacesClient
from ..services.tour_table import TourTableClient
from ..services.user_event_table import UserEventTableClient
from ..utils.aws import get_api_key_from_secret


@lru_cache
def get_tour_table_client() -> TourTableClient:
    return TourTableClient()


@lru_cache
def get_user_event_table_client() -> UserEventTableClient:
    return UserEventTableClient()


# Constants
GOOGLE_MAPS_API_KEY_SECRET_NAME = os.environ.get(
    "GOOGLE_MAPS_API_KEY_SECRET_NAME", "tensor-tours/google-maps-api-key"
)


def get_google_maps_api_key() -> str:
    """Get Google Maps API key from AWS Secrets Manager.

    Returns:
        The Google Maps API key as a string. Raises ValueError if not found.

    Raises:
        ValueError: If the API key cannot be retrieved.
    """
    api_key = get_api_key_from_secret(GOOGLE_MAPS_API_KEY_SECRET_NAME, "GOOGLE_MAPS_API_KEY")
    if api_key is None:
        raise ValueError(
            f"Failed to retrieve Google Maps API key from secret {GOOGLE_MAPS_API_KEY_SECRET_NAME}"
        )
    return api_key


@lru_cache
def get_google_places_client() -> GooglePlacesClient:
    """Get a Google Places client instance.

    Returns a cached instance of the GooglePlacesClient to avoid creating
    multiple instances during the lifetime of the Lambda function.
    """
    api_key = get_google_maps_api_key()
    # Create and return the client with the API key
    client = GooglePlacesClient(api_key)
    return client
