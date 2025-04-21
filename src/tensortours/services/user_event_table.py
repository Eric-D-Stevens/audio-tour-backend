"""User event logging models for TensorTours backend."""

import os
import time
from enum import Enum
from typing import Dict, List

import boto3
from mypy_boto3_dynamodb.service_resource import Table
from pydantic import BaseModel

from ..models.api import GenerateTourRequest, GetPlacesRequest, GetPregeneratedTourRequest


class EventType(Enum):
    """Types of user events that can be logged"""

    GET_PLACES = "get_places"
    GET_TOUR = "get_tour"
    GENERATE_TOUR = "generate_tour"


class UserEventItem(BaseModel):
    """DDB Stored user event item model"""

    user_id: str  # Primary key
    timestamp: int  # sort key
    event_type: EventType
    request_data: str  # JSON string of request data

    def dump(self) -> Dict:
        """Convert the model to a DynamoDB item format"""
        return {
            "user_id": self.user_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type.value,
            "request_data": self.request_data,
        }

    @classmethod
    def load(cls, data: Dict) -> "UserEventItem":
        """Load a UserEventItem from DynamoDB item format"""
        if "data" in data:
            data = data["data"]
        # Explicitly cast the return value to ensure mypy knows it's a UserEventItem
        result: "UserEventItem" = cls.model_validate_json(data)
        return result


class UserEventTableClient:
    """DDB User Event table client for logging user actions"""

    def __init__(self):
        self.table_name = os.environ["USER_EVENT_TABLE_NAME"]
        self._table: Table = boto3.resource("dynamodb").Table(self.table_name)

    def _get_current_timestamp(self) -> int:
        """Get current time in milliseconds"""
        return int(time.time() * 1000)

    def log_get_places_event(self, request: GetPlacesRequest) -> None:
        """Log a get places API request"""
        user_id = request.user.user_id if request.user else "anonymous"
        event = UserEventItem(
            user_id=user_id,
            timestamp=self._get_current_timestamp(),
            event_type=EventType.GET_PLACES,
            request_data=request.model_dump_json(),
        )
        self.put_item(event)

    def log_get_tour_event(self, request: GetPregeneratedTourRequest) -> None:
        """Log a get tour API request"""
        user_id = request.user.user_id if request.user else "anonymous"
        event = UserEventItem(
            user_id=user_id,
            timestamp=self._get_current_timestamp(),
            event_type=EventType.GET_TOUR,
            request_data=request.model_dump_json(),
        )
        self.put_item(event)

    def log_generate_tour_event(self, request: GenerateTourRequest) -> None:
        """Log a generate tour API request"""
        user_id = request.user.user_id if request.user else "anonymous"
        event = UserEventItem(
            user_id=user_id,
            timestamp=self._get_current_timestamp(),
            event_type=EventType.GENERATE_TOUR,
            request_data=request.model_dump_json(),
        )
        self.put_item(event)

    def put_item(self, item: UserEventItem) -> None:
        """Put a user event item into the table."""
        self._table.put_item(Item=item.dump())

    def get_user_events(self, user_id: str, limit: int = 100) -> List[UserEventItem]:
        """Get user events by user_id, sorted by timestamp (newest first)."""
        response = self._table.query(
            KeyConditionExpression="user_id = :user_id",
            ExpressionAttributeValues={":user_id": user_id},
            ScanIndexForward=False,  # Sort in descending order (newest first)
            Limit=limit,
        )

        if "Items" not in response or not response["Items"]:
            return []

        return [UserEventItem.load(item) for item in response["Items"]]

    def get_user_events_by_type(
        self, user_id: str, event_type: EventType, limit: int = 100
    ) -> List[UserEventItem]:
        """Get user events by user_id and event_type, sorted by timestamp (newest first)."""
        response = self._table.query(
            KeyConditionExpression="user_id = :user_id",
            FilterExpression="event_type = :event_type",
            ExpressionAttributeValues={":user_id": user_id, ":event_type": event_type.value},
            ScanIndexForward=False,  # Sort in descending order (newest first)
            Limit=limit,
        )

        if "Items" not in response or not response["Items"]:
            return []

        return [UserEventItem.load(item) for item in response["Items"]]

    def delete_item(self, user_id: str, timestamp: int) -> None:
        """Delete a user event item from the table."""
        self._table.delete_item(Key={"user_id": user_id, "timestamp": timestamp})
