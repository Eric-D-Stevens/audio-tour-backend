"""Tour-related models for TensorTours backend."""
from typing import List, Dict
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl


class TourType(str, Enum):
    """Types of tours available"""
    HISTORY = "history"
    CULTURE = "cultural"
    ARCHITECTURE = "architecture"
    ART = "art"
    NATURE = "nature"


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
    audio_id: str
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
    scripts: TTScript
    audio: TTAudio