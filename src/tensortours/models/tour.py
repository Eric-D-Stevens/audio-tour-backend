"""Tour-related models for TensorTours backend."""

from datetime import datetime
from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, Field


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

    HISTORY = [
        "historical_place", "monument", "historical_landmark", "cultural_landmark",
        "courthouse", "city_hall", "government_office", "embassy", 
        "cultural_center", "museum"
    ]

    CULTURE = [
        "art_gallery", "museum", "performing_arts_theater", "cultural_center",
        "tourist_attraction", "cultural_landmark", "historical_landmark", 
        "market", "restaurant", "community_center", "event_venue",
        "historical_place", "plaza"
    ]

    ART = [
        "art_gallery", "art_studio", "sculpture", "museum", "cultural_center",
        "performing_arts_theater", "opera_house", "concert_hall", "philharmonic_hall",
        "cultural_landmark"
    ]

    NATURE = [
        "park", "national_park", "state_park", "botanical_garden",
        "garden", "wildlife_park", "zoo", "aquarium", "beach", "hiking_area",
        "wildlife_refuge", "observation_deck", "marina", "fishing_pond",
        "cycling_park", "off_roading_area", "picnic_ground"
    ]

    ARCHITECTURE = [
        "cultural_landmark", "monument", "church", "hindu_temple",
        "mosque", "synagogue", "stadium", "opera_house", "university",
        "city_hall", "courthouse", "government_office", "concert_hall",
        "convention_center", "housing_complex", "apartment_building",
        "amphitheatre", "historical_landmark"
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
    cloudfront_url: str
    s3_url: str
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
    s3_url: str
    cloudfront_url: str
    generated_at: datetime = Field(default_factory=datetime.now)


class TTAudio(BaseModel):
    """Tour audio model"""

    place_id: str
    script_id: str
    cloudfront_url: str
    s3_url: str
    model_info: Dict
    generated_at: datetime = Field(default_factory=datetime.now)


class TTour(BaseModel):
    place_id: str
    tour_type: TourType
    place_info: TTPlaceInfo
    photos: List[TTPlacePhotos]
    script: TTScript
    audio: TTAudio
