"""Pydantic models for the POI tour generation pipeline."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .api import BaseRequest


class PoiInputData(BaseModel):
    """Input data describing the point of interest to generate a tour for."""

    title: str = Field(..., description="Display name of the POI")
    lat: float = Field(..., description="Latitude (WGS-84)")
    lng: float = Field(..., description="Longitude (WGS-84)")
    source_ids: Dict = Field(
        default_factory=dict,
        description='External source identifiers, e.g. {"google":"ChIJ...", "osm":"node/456"}',
    )
    location_meta: Optional[Dict] = Field(
        None,
        description="Freeform location metadata (display address, country, city, etc.)",
    )
    # Pre-known data the caller already has (optional)
    summary: Optional[str] = Field(None, description="Short preview text, if already known")
    photo_urls: Dict = Field(
        default_factory=dict,
        description='Photo URLs the caller already has, e.g. {"thumbnail":"..."}',
    )


class GenerationConfig(BaseModel):
    """Configuration controlling how the tour is generated."""

    language: str = Field("en", description="BCP-47 language code for the tour script")
    tour_style: str = Field(
        "general",
        description="Tour style: general | history | culture | nature",
    )
    force_regenerate: bool = Field(
        False,
        description="Re-run generation even if a ready POI already exists",
    )


class PoiGenerateRequest(BaseRequest):
    """Request model for POST /poi/generate."""

    poi_data: PoiInputData
    generation_config: GenerationConfig = Field(default_factory=GenerationConfig)


class PoiGenerateResponse(BaseModel):
    """Response model for POST /poi/generate."""

    poi_id: str = Field(..., description="UUID of the POI (new or existing)")
    status: str = Field(..., description="POI status: pending | ready")
    was_duplicate: bool = Field(..., description="True if an existing POI was found")
    canonical_id: Optional[str] = Field(
        None,
        description="Set if the request was merged into a pre-existing POI row",
    )
