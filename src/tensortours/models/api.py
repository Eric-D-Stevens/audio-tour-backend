"""API models for TensorTours backend API Gateway integration."""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from ..models.tour import TourType, TTour, TTPlaceInfo


class CognitoUser(BaseModel):
    """Model for Cognito user information extracted from the request context"""

    user_id: str = Field(..., description="Cognito user ID (sub)")
    username: Optional[str] = Field(None, description="Cognito username")
    email: Optional[str] = Field(None, description="User email address")
    groups: List[str] = Field(default_factory=list, description="Cognito user groups")

    @classmethod
    def from_request_context(cls, request_context: Dict) -> Optional["CognitoUser"]:
        """Extract user information from the API Gateway request context"""
        if not request_context or "authorizer" not in request_context:
            return None

        authorizer = request_context.get("authorizer", {})
        if not authorizer or "claims" not in authorizer:
            return None

        claims = authorizer.get("claims", {})
        if not claims or "sub" not in claims:
            return None

        # Extract user groups if available
        groups = []
        cognito_groups = claims.get("cognito:groups")
        if cognito_groups:
            if isinstance(cognito_groups, str):
                groups = [g.strip() for g in cognito_groups.split(",")]
            elif isinstance(cognito_groups, list):
                groups = cognito_groups

        return cls(
            user_id=claims.get("sub"),
            username=claims.get("cognito:username"),
            email=claims.get("email"),
            groups=groups,
        )


class BaseRequest(BaseModel):
    """Base request model with user information"""

    user: Optional[CognitoUser] = Field(None, description="User information from Cognito")
    request_id: Optional[str] = Field(None, description="Unique request identifier")
    timestamp: Optional[datetime] = Field(None, description="Request timestamp")

    @model_validator(mode="before")
    @classmethod
    def extract_context_data(cls, data: Dict) -> Dict:
        """Extract context data from the raw event if available"""
        # This is used when parsing the raw Lambda event
        if isinstance(data, dict) and "requestContext" in data:
            request_context = data.get("requestContext", {})
            data["user"] = CognitoUser.from_request_context(request_context)
            data["request_id"] = request_context.get("requestId")
            data["timestamp"] = datetime.now()
        return data


class GetPlacesRequest(BaseRequest):
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
    is_authenticated: bool = Field(False, description="Whether the request was authenticated")


class GetPregeneratedTourRequest(BaseRequest):
    """Request model for getting a pregenerated tour"""

    place_id: str = Field(..., description="ID of the place to get a tour for")
    tour_type: TourType = Field(..., description="Type of tour to get")


class GetPregeneratedTourResponse(BaseModel):
    """Response model for getting a pregenerated tour"""

    tour: TTour
    is_authenticated: bool = Field(False, description="Whether the request was authenticated")


class GenerateTourRequest(BaseRequest):
    """Request model for generating a new tour"""

    place_id: str = Field(..., description="ID of the place to generate a tour for")
    tour_type: TourType = Field(..., description="Type of tour to generate")
    language_code: str = Field("en", description="Language code for the tour")


class GenerateTourResponse(BaseModel):
    """Response model for generating a new tour"""

    tour: TTour
    is_authenticated: bool = Field(False, description="Whether the request was authenticated")


class GetOnDemandTourRequest(BaseRequest):
    """Request model for getting an on-demand tour
    
    This model is similar to GetPregeneratedTourRequest but can also include place_info
    for places that don't have existing data in the database.
    """
    
    place_id: str = Field(..., description="ID of the place to get a tour for")
    tour_type: TourType = Field(..., description="Type of tour to get")
    place_info_json: Optional[str] = Field(None, description="JSON string with place information if not already in database")


class GetOnDemandTourResponse(BaseModel):
    """Response model for getting an on-demand tour
    
    This model is used for returning tours that are generated on-demand
    without using the tour table or generation queue.
    """
    
    tour: TTour
    is_authenticated: bool = Field(False, description="Whether the request was authenticated")
    generated_on_demand: bool = Field(True, description="Whether the tour was generated on-demand")


class GetPreviewRequest(BaseRequest):
    """Request model for getting a preview tour
    
    This model is used specifically for requesting preview tours that are
    pre-generated and available in the preview dataset.
    """
    
    place_id: str = Field(..., description="ID of the place to get a preview tour for")
    tour_type: TourType = Field(..., description="Type of tour to get")


class GetPreviewResponse(BaseModel):
    """Response model for getting a preview tour
    
    This model is used for returning preview tours that are pre-generated
    and available in the preview dataset.
    """
    
    tour: TTour
    is_authenticated: bool = Field(False, description="Whether the request was authenticated")
