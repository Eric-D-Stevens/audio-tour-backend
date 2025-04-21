"""Tour-related models for TensorTours backend."""

import os
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

import boto3
from mypy_boto3_dynamodb.service_resource import Table
from pydantic import BaseModel, Field

from ..models.tour import TourType, TTAudio, TTPlaceInfo, TTPlacePhotos, TTScript


class GenerationStatus(Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TourTableItem(BaseModel):
    """DDB Stored tour item model"""

    place_id: str  # Primary key
    tour_type: TourType  # Sort key
    place_info: TTPlaceInfo
    status: GenerationStatus
    photos: Optional[List[TTPlacePhotos]]
    script: Optional[TTScript]
    audio: Optional[TTAudio]
    created_at: datetime = Field(default_factory=datetime.now)

    def dump(self) -> Dict:
        return {
            "place_id": self.place_id,
            "tour_type": self.tour_type.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "data": self.model_dump_json(),
        }

    @classmethod
    def load(cls, data: Dict) -> "TourTableItem":
        if "data" in data:
            data = data["data"]
        return cls.model_validate_json(data)


class TourTableClient:
    """DDB Tour table client"""

    def __init__(self):
        self.table_name = os.environ["TOUR_TABLE_NAME"]
        self._table: Table = boto3.resource("dynamodb").Table(self.table_name)

    def get_item(self, place_id: str, tour_type: TourType) -> Optional[TourTableItem]:
        """Get a tour item by place_id and tour_type."""
        response = self._table.get_item(Key={"place_id": place_id, "tour_type": tour_type.value})

        # Check if the item exists in the response
        if "Item" not in response or not response["Item"]:
            return None

        return TourTableItem.load(response["Item"])

    def put_item(self, item: TourTableItem):
        """Put a tour item into the table."""
        self._table.put_item(Item=item.dump())

    def delete_item(self, place_id: str, tour_type: TourType):
        """Delete a tour item from the table."""
        self._table.delete_item(Key={"place_id": place_id, "tour_type": tour_type.value})
