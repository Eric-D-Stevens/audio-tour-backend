"""Pydantic models for the TensorTours POI API."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .api import BaseRequest


class PoiInsertRequest(BaseRequest):
    """Request model for inserting a new Point of Interest."""

    # Required
    title: str = Field(..., description="Display name of the POI")
    lat: float = Field(..., description="Latitude (WGS-84)")
    lng: float = Field(..., description="Longitude (WGS-84)")

    # Optional — caller supplies what it has; DB defaults to empty / zero
    source_ids: Dict = Field(
        default_factory=dict,
        description='External source identifiers, e.g. {"google":"ChIJ...", "osm":"node/456"}',
    )
    location_meta: Optional[Dict] = Field(
        None,
        description="Freeform location metadata (display address, country, city, etc.)",
    )
    summary: Optional[str] = Field(None, description="Short preview text")
    overall_score: float = Field(0.0, description="Aggregate quality score")
    scores_vector: Dict = Field(
        default_factory=dict, description="Category subscores"
    )
    photo_urls: Dict = Field(
        default_factory=dict,
        description='Photo URLs, e.g. {"thumbnail":"...","images":["..."]}',
    )
    scripts: Dict = Field(
        default_factory=dict,
        description='Audio tour scripts by language, e.g. {"en":"...","es":"..."}',
    )
    audio_urls: Dict = Field(
        default_factory=dict,
        description='Audio file URLs by language, e.g. {"en":"https://cdn/.../en.mp3"}',
    )


class PoiInsertResponse(BaseModel):
    """Response model for a successful POI insert."""

    id: str = Field(..., description="UUID of the newly created POI")


class PoiRecord(BaseModel):
    """A single Point of Interest returned from the database."""

    id: str
    title: str
    summary: Optional[str]
    lat: float
    lng: float
    overall_score: float
    status: str
    scores_vector: Dict
    audio_urls: Dict
    photo_urls: Dict
    scripts: Dict
    location_meta: Optional[Dict]
    generation_error: Optional[Dict] = None


class PoiQueryRequest(BaseRequest):
    """Request model for querying nearby Points of Interest."""

    lat: float = Field(..., description="Center latitude for the search")
    lng: float = Field(..., description="Center longitude for the search")
    radius_meters: float = Field(5000.0, description="Search radius in metres")
    limit: int = Field(50, description="Maximum number of results to return")


class PoiQueryResponse(BaseModel):
    """Response model for a nearby POI search."""

    pois: List[PoiRecord]
    total: int
