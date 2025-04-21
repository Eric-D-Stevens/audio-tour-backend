"""Place-related models for TensorTours backend."""

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, HttpUrl


class PlacePhoto(BaseModel):
    """Google Places photo model"""

    photo_reference: str
    height: int
    width: int
    html_attributions: List[str]
    url: Optional[HttpUrl] = None


class PlaceDetails(BaseModel):
    """Google Places details model"""

    place_id: str
    name: str
    formatted_address: str
    location: Dict[str, float]
    photos: Optional[List[PlacePhoto]] = None
    types: List[str]
    rating: Optional[float] = None
    website: Optional[HttpUrl] = None
    formatted_phone_number: Optional[str] = None
    opening_hours: Optional[Dict[str, Any]] = None
    price_level: Optional[int] = None
    editorial_summary: Optional[str] = None
    reviews: Optional[List[Dict[str, Any]]] = None
