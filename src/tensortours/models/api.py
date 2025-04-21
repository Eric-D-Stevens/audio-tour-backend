"""API models for TensorTours backend API Gateway integration."""
from typing import List, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl

from ..models.tour import TourType, TTPlaceInfo, TTPlacePhotos, TTScript, TTAudio, TTour


class GetPlacesRequest(BaseModel):
    """Request model for getting places near a location"""
    tour_type: TourType = Field(..., description="Type of tour to get places for")
    latitude: float = Field(..., description="Latitude of the search location")
    longitude: float = Field(..., description="Longitude of the search location")
    radius: int = Field(1000, description="Search radius in meters")
    max_results: int = Field(20, description="Maximum number of results to return")


class GetPlacesResponse(BaseModel):
    """Response model for getting places near a location"""
    places: List[TTPlaceInfo]
    total_count: int


class GetPregeneratedTourRequest(BaseModel):
    """Request model for getting a pregenerated tour"""
    place_id: str = Field(..., description="ID of the place to get a tour for")
    tour_type: TourType = Field(..., description="Type of tour to get")


class GetPregeneratedTourResponse(BaseModel):
    """Response model for getting a pregenerated tour"""
    tour: TTour


class GenerateTourRequest(BaseModel):
    """Request model for generating a new tour"""
    place_id: str = Field(..., description="ID of the place to generate a tour for")
    tour_type: TourType = Field(..., description="Type of tour to generate")
    language_code: str = Field("en", description="Language code for the tour")


class GenerateTourResponse(BaseModel):
    """Response model for generating a new tour"""
    tour: TTour

