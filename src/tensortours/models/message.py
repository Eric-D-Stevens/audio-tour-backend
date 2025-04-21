"""Message models for TensorTours backend."""

from typing import Optional, Dict, Any
from pydantic import BaseModel

from tensortours.models.tour import TourType


class SQSMessage(BaseModel):
    """Base SQS message model"""

    message_id: Optional[str] = None
    receipt_handle: Optional[str] = None


class TourGenerationMessage(SQSMessage):
    """SQS message for tour generation requests"""

    place_id: str
    tour_type: str
    user_id: Optional[str] = None
    duration_minutes: Optional[int] = 30
    language: str = "en"


class TourGenerationResponse(BaseModel):
    """Response model for tour generation"""

    success: bool
    tour_id: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None


class TourPreGenerationResult(BaseModel):
    """Result of the pre-generation lambda"""

    place_id: str
    place_details: Dict[str, Any]  # Using Dict for flexibility
    script: Dict[str, Any]  # Using Dict for flexibility
    photo_urls: list[str]
    status: str = "pending_audio"
