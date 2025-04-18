"""Tour-related models for TensorTours backend."""
from typing import List, Dict, Optional, Any, Union
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, validator


class TourType(str, Enum):
    """Types of tours available"""
    HISTORY = "history"
    CULTURE = "cultural"
    ARCHITECTURE = "architecture"
    FOOD = "food_drink"
    ART = "art"
    NATURE = "nature"
    GENERAL = "general"


class ScriptSegment(BaseModel):
    """Individual segment of a tour script"""
    title: str
    content: str
    duration_seconds: int


class TourScript(BaseModel):
    """Complete tour script model"""
    place_id: str
    place_name: str
    tour_type: TourType
    segments: List[ScriptSegment]
    total_duration_seconds: int
    generated_at: datetime = Field(default_factory=datetime.now)


class AudioSegment(BaseModel):
    """Audio segment model with metadata"""
    segment_id: str
    title: str
    url: HttpUrl
    duration_seconds: float
    transcript: str


class CompleteTour(BaseModel):
    """Complete tour with all metadata and audio segments"""
    tour_id: str
    place_id: str
    place_name: str
    tour_type: TourType
    duration_minutes: int
    language: str
    audio_segments: List[AudioSegment]
    photos: List[str]
    generated_at: datetime
    status: str = "complete"


class TourRequest(BaseModel):
    """Request model for tour generation"""
    place_id: str
    tour_type: TourType = TourType.GENERAL
    user_id: Optional[str] = None
    duration_minutes: Optional[int] = 30
    language: str = "en"
