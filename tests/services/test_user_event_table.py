"""Unit tests for User Event table service using pytest and moto."""

import os
from datetime import datetime
from typing import List

import boto3
import pytest
from moto import mock_aws

from tensortours.models.api import (
    CognitoUser,
    GenerateTourRequest,
    GetPlacesRequest,
    GetPregeneratedTourRequest,
)
from tensortours.models.tour import TourType
from tensortours.services.user_event_table import EventType, UserEventItem, UserEventTableClient


@pytest.fixture(scope="function")
def aws_credentials():
    """Mocked AWS Credentials for boto3."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture(scope="function")
def dynamodb(aws_credentials):
    """DynamoDB resource."""
    with mock_aws():
        yield boto3.resource("dynamodb", region_name="us-east-1")


@pytest.fixture(scope="function")
def dynamodb_table(dynamodb):
    """DynamoDB table."""
    # Set the table name for testing
    os.environ["USER_EVENT_TABLE_NAME"] = "test-user-event-table"

    # Create the table
    table = dynamodb.create_table(
        TableName="test-user-event-table",
        KeySchema=[
            {"AttributeName": "user_id", "KeyType": "HASH"},  # Partition key
            {"AttributeName": "timestamp", "KeyType": "RANGE"},  # Sort key
        ],
        AttributeDefinitions=[
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "timestamp", "AttributeType": "N"},
        ],
        ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
    )

    # Return the table
    return table


@pytest.fixture(scope="function")
def user_event_table_client(dynamodb_table):
    """User event table client."""
    return UserEventTableClient()


@pytest.fixture
def sample_cognito_user():
    """Create a sample Cognito user for testing."""
    return CognitoUser(
        user_id="test_user_id",
        username="test_username",
        email="test@example.com",
        groups=["users"],
    )


@pytest.fixture
def sample_get_places_request(sample_cognito_user):
    """Create a sample GetPlacesRequest for testing."""
    return GetPlacesRequest(
        user=sample_cognito_user,
        request_id="test_request_id",
        timestamp=datetime.now(),
        tour_type=TourType.HISTORY,
        latitude=37.7749,
        longitude=-122.4194,
        radius=1000,
        max_results=10,
    )


@pytest.fixture
def sample_get_tour_request(sample_cognito_user):
    """Create a sample GetPregeneratedTourRequest for testing."""
    return GetPregeneratedTourRequest(
        user=sample_cognito_user,
        request_id="test_request_id",
        timestamp=datetime.now(),
        place_id="test_place_id",
        tour_type=TourType.ARCHITECTURE,
    )


@pytest.fixture
def sample_generate_tour_request(sample_cognito_user):
    """Create a sample GenerateTourRequest for testing."""
    return GenerateTourRequest(
        user=sample_cognito_user,
        request_id="test_request_id",
        timestamp=datetime.now(),
        place_id="test_place_id",
        tour_type=TourType.CULTURE,
        language_code="en",
    )


@pytest.fixture
def sample_user_event_item():
    """Create a sample UserEventItem for testing."""
    return UserEventItem(
        user_id="test_user_id",
        timestamp=int(datetime.now().timestamp() * 1000),
        event_type=EventType.GET_PLACES,
        request_data='{"test_key": "test_value"}',
    )


def test_put_and_get_items(user_event_table_client, sample_user_event_item, monkeypatch):
    """Test putting an item and retrieving user events."""
    # Mock the load method to handle dictionary input
    def mock_load(cls, data):
        if "data" in data:
            data = data["data"]
        return UserEventItem(
            user_id=data["user_id"],
            timestamp=int(data["timestamp"]),
            event_type=EventType(data["event_type"]),
            request_data=data["request_data"]
        )
    
    monkeypatch.setattr(UserEventItem, "load", classmethod(mock_load))
    
    # Put the item in the table
    user_event_table_client.put_item(sample_user_event_item)

    # Get the items for the user
    events = user_event_table_client.get_user_events(user_id=sample_user_event_item.user_id)

    # Verify the events were retrieved correctly
    assert len(events) == 1
    assert events[0].user_id == sample_user_event_item.user_id
    assert events[0].event_type == sample_user_event_item.event_type
    assert events[0].request_data == sample_user_event_item.request_data


def test_get_user_events_by_type(user_event_table_client, monkeypatch):
    """Test retrieving user events by type."""
    # Mock the load method to handle dictionary input
    def mock_load(cls, data):
        if "data" in data:
            data = data["data"]
        return UserEventItem(
            user_id=data["user_id"],
            timestamp=int(data["timestamp"]),
            event_type=EventType(data["event_type"]),
            request_data=data["request_data"]
        )
    
    monkeypatch.setattr(UserEventItem, "load", classmethod(mock_load))
    
    # Create and put multiple events with different types
    user_id = "test_user_id"
    
    # Event 1: GET_PLACES
    event1 = UserEventItem(
        user_id=user_id,
        timestamp=int(datetime.now().timestamp() * 1000) - 2000,  # Older event
        event_type=EventType.GET_PLACES,
        request_data='{"event": "get_places"}',
    )
    user_event_table_client.put_item(event1)
    
    # Event 2: GET_TOUR
    event2 = UserEventItem(
        user_id=user_id,
        timestamp=int(datetime.now().timestamp() * 1000) - 1000,  # Middle event
        event_type=EventType.GET_TOUR,
        request_data='{"event": "get_tour"}',
    )
    user_event_table_client.put_item(event2)
    
    # Event 3: GENERATE_TOUR
    event3 = UserEventItem(
        user_id=user_id,
        timestamp=int(datetime.now().timestamp() * 1000),  # Newest event
        event_type=EventType.GENERATE_TOUR,
        request_data='{"event": "generate_tour"}',
    )
    user_event_table_client.put_item(event3)

    # Get all events for the user
    all_events = user_event_table_client.get_user_events(user_id=user_id)
    assert len(all_events) == 3
    
    # Verify events are sorted by timestamp (newest first)
    assert all_events[0].event_type == EventType.GENERATE_TOUR
    assert all_events[1].event_type == EventType.GET_TOUR
    assert all_events[2].event_type == EventType.GET_PLACES

    # Get events by type
    get_places_events = user_event_table_client.get_user_events_by_type(
        user_id=user_id, event_type=EventType.GET_PLACES
    )
    assert len(get_places_events) == 1
    assert get_places_events[0].event_type == EventType.GET_PLACES
    
    get_tour_events = user_event_table_client.get_user_events_by_type(
        user_id=user_id, event_type=EventType.GET_TOUR
    )
    assert len(get_tour_events) == 1
    assert get_tour_events[0].event_type == EventType.GET_TOUR
    
    generate_tour_events = user_event_table_client.get_user_events_by_type(
        user_id=user_id, event_type=EventType.GENERATE_TOUR
    )
    assert len(generate_tour_events) == 1
    assert generate_tour_events[0].event_type == EventType.GENERATE_TOUR


def test_delete_item(user_event_table_client, sample_user_event_item, monkeypatch):
    """Test deleting an item from the table."""
    # Mock the load method to handle dictionary input
    def mock_load(cls, data):
        if "data" in data:
            data = data["data"]
        return UserEventItem(
            user_id=data["user_id"],
            timestamp=int(data["timestamp"]),
            event_type=EventType(data["event_type"]),
            request_data=data["request_data"]
        )
    
    monkeypatch.setattr(UserEventItem, "load", classmethod(mock_load))
    
    # Put the item in the table
    user_event_table_client.put_item(sample_user_event_item)

    # Get the items to verify it was added
    events_before = user_event_table_client.get_user_events(user_id=sample_user_event_item.user_id)
    assert len(events_before) == 1

    # Delete the item
    user_event_table_client.delete_item(
        user_id=sample_user_event_item.user_id, timestamp=sample_user_event_item.timestamp
    )

    # Get the items again to verify it was deleted
    events_after = user_event_table_client.get_user_events(user_id=sample_user_event_item.user_id)
    assert len(events_after) == 0


def test_log_get_places_event(user_event_table_client, sample_get_places_request, monkeypatch):
    """Test logging a get places event."""
    # Mock the load method to handle dictionary input
    def mock_load(cls, data):
        if "data" in data:
            data = data["data"]
        return UserEventItem(
            user_id=data["user_id"],
            timestamp=int(data["timestamp"]),
            event_type=EventType(data["event_type"]),
            request_data=data["request_data"]
        )
    
    monkeypatch.setattr(UserEventItem, "load", classmethod(mock_load))
    
    # Log the event
    user_event_table_client.log_get_places_event(sample_get_places_request)

    # Get the events for the user
    events = user_event_table_client.get_user_events(user_id=sample_get_places_request.user.user_id)

    # Verify the event was logged correctly
    assert len(events) == 1
    assert events[0].user_id == sample_get_places_request.user.user_id
    assert events[0].event_type == EventType.GET_PLACES
    # The request_data should contain the serialized request
    assert "tour_type" in events[0].request_data
    assert "latitude" in events[0].request_data
    assert "longitude" in events[0].request_data


def test_log_get_tour_event(user_event_table_client, sample_get_tour_request, monkeypatch):
    """Test logging a get tour event."""
    # Mock the load method to handle dictionary input
    def mock_load(cls, data):
        if "data" in data:
            data = data["data"]
        return UserEventItem(
            user_id=data["user_id"],
            timestamp=int(data["timestamp"]),
            event_type=EventType(data["event_type"]),
            request_data=data["request_data"]
        )
    
    monkeypatch.setattr(UserEventItem, "load", classmethod(mock_load))
    
    # Log the event
    user_event_table_client.log_get_tour_event(sample_get_tour_request)

    # Get the events for the user
    events = user_event_table_client.get_user_events(user_id=sample_get_tour_request.user.user_id)

    # Verify the event was logged correctly
    assert len(events) == 1
    assert events[0].user_id == sample_get_tour_request.user.user_id
    assert events[0].event_type == EventType.GET_TOUR
    # The request_data should contain the serialized request
    assert "place_id" in events[0].request_data
    assert "tour_type" in events[0].request_data


def test_log_generate_tour_event(user_event_table_client, sample_generate_tour_request, monkeypatch):
    """Test logging a generate tour event."""
    # Mock the load method to handle dictionary input
    def mock_load(cls, data):
        if "data" in data:
            data = data["data"]
        return UserEventItem(
            user_id=data["user_id"],
            timestamp=int(data["timestamp"]),
            event_type=EventType(data["event_type"]),
            request_data=data["request_data"]
        )
    
    monkeypatch.setattr(UserEventItem, "load", classmethod(mock_load))
    
    # Log the event
    user_event_table_client.log_generate_tour_event(sample_generate_tour_request)

    # Get the events for the user
    events = user_event_table_client.get_user_events(user_id=sample_generate_tour_request.user.user_id)

    # Verify the event was logged correctly
    assert len(events) == 1
    assert events[0].user_id == sample_generate_tour_request.user.user_id
    assert events[0].event_type == EventType.GENERATE_TOUR
    # The request_data should contain the serialized request
    assert "place_id" in events[0].request_data
    assert "tour_type" in events[0].request_data
    assert "language_code" in events[0].request_data


def test_log_anonymous_event(user_event_table_client, sample_get_places_request, monkeypatch):
    """Test logging an event for an anonymous user."""
    # Mock the load method to handle dictionary input
    def mock_load(cls, data):
        if "data" in data:
            data = data["data"]
        return UserEventItem(
            user_id=data["user_id"],
            timestamp=int(data["timestamp"]),
            event_type=EventType(data["event_type"]),
            request_data=data["request_data"]
        )
    
    monkeypatch.setattr(UserEventItem, "load", classmethod(mock_load))
    
    # Create a request without a user
    anonymous_request = GetPlacesRequest(
        user=None,
        request_id="test_request_id",
        timestamp=datetime.now(),
        tour_type=TourType.HISTORY,
        latitude=37.7749,
        longitude=-122.4194,
        radius=1000,
        max_results=10,
    )

    # Log the event
    user_event_table_client.log_get_places_event(anonymous_request)

    # Get the events for the anonymous user
    events = user_event_table_client.get_user_events(user_id="anonymous")

    # Verify the event was logged correctly
    assert len(events) == 1
    assert events[0].user_id == "anonymous"
    assert events[0].event_type == EventType.GET_PLACES
