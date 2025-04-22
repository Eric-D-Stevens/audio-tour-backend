"""Tour-related models for TensorTours backend."""

from datetime import datetime
from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, Field, HttpUrl


class TourType(str, Enum):
    """Types of tours available"""

    HISTORY = "history"
    CULTURE = "cultural"
    ARCHITECTURE = "architecture"
    ART = "art"
    NATURE = "nature"


class TourTypeToGooglePlaceTypes(Enum):
    """Mapping of tour types to Google Places API place types.

    This enum provides a standardized mapping between TensorTours tour types
    and the corresponding Google Places API place types to use when searching
    for places of a specific tour type.
    """

    HISTORY = ["historical_place", "monument", "historical_landmark", "cultural_landmark"]

    CULTURE = [
        "art_gallery",
        "museum",
        "performing_arts_theater",
        "cultural_center",
        "tourist_attraction",
    ]

    ART = ["art_gallery", "art_studio", "sculpture"]

    NATURE = [
        "park",
        "national_park",
        "state_park",
        "botanical_garden",
        "garden",
        "wildlife_park",
        "zoo",
        "aquarium",
    ]

    ARCHITECTURE = [
        "cultural_landmark",
        "monument",
        "church",
        "hindu_temple",
        "mosque",
        "synagogue",
        "stadium",
        "opera_house",
    ]

    @classmethod
    def get_place_types(cls, tour_type: TourType) -> List[str]:
        """Get Google Places API place types for a given tour type.

        Args:
            tour_type: The TourType to get place types for

        Returns:
            List of Google Places API place types corresponding to the tour type
        """
        try:
            return cls[tour_type.name].value
        except (KeyError, AttributeError):
            # Default to tourist_attraction if no mapping exists
            return ["tourist_attraction"]


class TTPlaceInfo(BaseModel):
    """Place information model"""

    place_id: str
    place_name: str
    place_editorial_summary: str
    place_address: str
    place_primary_type: str
    place_types: List[str]
    place_location: Dict[str, float]
    retrieved_at: datetime = Field(default_factory=datetime.now)


class TTPlacePhotos(BaseModel):
    """Place photos model"""

    photo_id: str
    place_id: str
    cloudfront_url: HttpUrl
    s3_url: HttpUrl
    attribution: Dict[str, str]
    size_width: int
    size_height: int
    retrieved_at: datetime = Field(default_factory=datetime.now)


class TTScript(BaseModel):
    """Tour script model"""

    script_id: str
    place_id: str
    place_name: str
    tour_type: TourType
    model_info: Dict
    s3_url: HttpUrl
    cloudfront_url: HttpUrl
    generated_at: datetime = Field(default_factory=datetime.now)


class TTAudio(BaseModel):
    """Tour audio model"""

    place_id: str
    script_id: str
    cloudfront_url: HttpUrl
    s3_url: HttpUrl
    model_info: Dict
    generated_at: datetime = Field(default_factory=datetime.now)


class TTour(BaseModel):
    place_id: str
    tour_type: TourType
    place_info: TTPlaceInfo
    photos: List[TTPlacePhotos]
    script: TTScript
    audio: TTAudio
