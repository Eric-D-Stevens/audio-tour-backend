"""Unit tests for the get_tour lambda handler."""

import json
import os
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from tensortours.lambda_handlers.get_tour import handler
from tensortours.models.api import GetPregeneratedTourRequest
from tensortours.models.tour import TourType, TTAudio, TTPlaceInfo, TTPlacePhotos, TTScript
from tensortours.services.tour_table import GenerationStatus, TourTableClient, TourTableItem
from tensortours.services.user_event_table import UserEventTableClient


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
def tour_table(dynamodb):
    """Tour table for testing."""
    # Set the table name for testing
    os.environ["TOUR_TABLE_NAME"] = "test-tour-table"

    # Create the table
    table = dynamodb.create_table(
        TableName="test-tour-table",
        KeySchema=[
            {"AttributeName": "place_id", "KeyType": "HASH"},  # Partition key
            {"AttributeName": "tour_type", "KeyType": "RANGE"},  # Sort key
        ],
        AttributeDefinitions=[
            {"AttributeName": "place_id", "AttributeType": "S"},
            {"AttributeName": "tour_type", "AttributeType": "S"},
        ],
        ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
    )

    return table


@pytest.fixture(scope="function")
def user_event_table(dynamodb):
    """User event table for testing."""
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

    return table


@pytest.fixture
def sample_tour_item():
    """Sample tour item for testing."""
    return TourTableItem(
        place_id="test_place_id",
        tour_type=TourType.HISTORY,
        status=GenerationStatus.COMPLETED,
        place_info=TTPlaceInfo(
            place_id="test_place_id",
            place_name="Test Place",
            place_editorial_summary="A test place for tours",
            place_address="123 Test St, Test City, TC 12345",
            place_primary_type="tourist_attraction",
            place_types=["tourist_attraction", "point_of_interest"],
            place_location={"lat": 37.7749, "lng": -122.4194},
        ),
        photos=[
            TTPlacePhotos(
                photo_id="test_photo_id",
                place_id="test_place_id",
                cloudfront_url="https://example-cloudfront.com/photo.jpg",
                s3_url="https://example-s3.com/photo.jpg",
                attribution={"author": "Test Author", "license": "CC BY"},
                size_width=800,
                size_height=600,
            )
        ],
        script=TTScript(
            script_id="test_script_id",
            place_id="test_place_id",
            place_name="Test Place",
            tour_type=TourType.HISTORY,
            model_info={"model": "gpt-4", "version": "1.0"},
            s3_url="https://example-s3.com/script.txt",
            cloudfront_url="https://example-cloudfront.com/script.txt",
        ),
        audio=TTAudio(
            audio_id="test_audio_id",
            place_id="test_place_id",
            script_id="test_script_id",
            cloudfront_url="https://example-cloudfront.com/audio.mp3",
            s3_url="https://example-s3.com/audio.mp3",
            model_info={"model": "polly", "voice": "Joanna"},
        ),
    )


@patch("tensortours.lambda_handlers.get_tour.get_tour_table_client")
@patch("tensortours.lambda_handlers.get_tour.get_user_event_table_client")
def test_handler_success(
    mock_get_user_event_table_client, mock_get_tour_table_client, sample_tour_item
):
    """Test the handler with a successful tour retrieval."""
    # Set up the mock tour table client
    mock_tour_client = MagicMock(spec=TourTableClient)
    mock_tour_client.get_item.return_value = sample_tour_item
    mock_get_tour_table_client.return_value = mock_tour_client

    # Set up the mock user event table client
    mock_user_event_client = MagicMock(spec=UserEventTableClient)
    mock_get_user_event_table_client.return_value = mock_user_event_client

    # Create a sample event with authenticated user context
    event = {
        "body": {"place_id": "test_place_id", "tour_type": TourType.HISTORY.value},
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": "test_user_123",
                    "cognito:username": "testuser",
                    "email": "test@example.com",
                    "cognito:groups": "users",
                }
            },
            "requestId": "test-request-id",
        },
    }

    # Call the handler
    response = handler(event, {})

    # Check that the response is correct
    assert response["statusCode"] == 200
    response_body = json.loads(response["body"])
    assert "tour" in response_body
    assert response_body["tour"]["place_id"] == "test_place_id"
    assert response_body["tour"]["tour_type"] == "history"

    # Verify that the tour table client was called correctly
    mock_tour_client.get_item.assert_called_once_with("test_place_id", TourType.HISTORY)

    # Verify that the user event table client was called to log the event
    mock_user_event_client.log_get_tour_event.assert_called_once()

    # Verify the request passed to log_get_tour_event
    log_call_args = mock_user_event_client.log_get_tour_event.call_args[0][0]
    assert isinstance(log_call_args, GetPregeneratedTourRequest)
    assert log_call_args.place_id == "test_place_id"
    assert log_call_args.tour_type == TourType.HISTORY
    # Now the user information should be properly extracted
    assert log_call_args.user is not None
    assert log_call_args.user.user_id == "test_user_123"
    assert log_call_args.user.username == "testuser"
    assert log_call_args.user.email == "test@example.com"
    assert "users" in log_call_args.user.groups


@patch("tensortours.lambda_handlers.get_tour.get_tour_table_client")
@patch("tensortours.lambda_handlers.get_tour.get_user_event_table_client")
def test_handler_tour_not_found(mock_get_user_event_table_client, mock_get_tour_table_client):
    """Test the handler when a tour is not found."""
    # Set up the mock tour table client
    mock_tour_client = MagicMock(spec=TourTableClient)
    mock_tour_client.get_item.return_value = None
    mock_get_tour_table_client.return_value = mock_tour_client

    # Set up the mock user event table client
    mock_user_event_client = MagicMock(spec=UserEventTableClient)
    mock_get_user_event_table_client.return_value = mock_user_event_client

    # Create a sample event with no user context
    event = {
        "body": {
            "place_id": "nonexistent_place_id",
            "tour_type": TourType.HISTORY.value,
        },
        # No requestContext.authorizer means no user information
        "requestContext": {"requestId": "test-request-id-2"},
    }

    # Call the handler
    response = handler(event, {})

    # Check that the response is a 404
    assert response["statusCode"] == 404
    response_body = json.loads(response["body"])
    assert "error" in response_body
    assert response_body["error"] == "Tour not found"

    # Verify that the tour table client was called correctly
    mock_tour_client.get_item.assert_called_once_with("nonexistent_place_id", TourType.HISTORY)

    # Verify that the user event was still logged even though the tour was not found
    mock_user_event_client.log_get_tour_event.assert_called_once()

    # Verify the request passed to log_get_tour_event and check it's using "anonymous" for user_id
    log_call_args = mock_user_event_client.log_get_tour_event.call_args[0][0]
    assert isinstance(log_call_args, GetPregeneratedTourRequest)
    assert log_call_args.place_id == "nonexistent_place_id"
    assert log_call_args.tour_type == TourType.HISTORY
    assert (
        log_call_args.user is None
    )  # This should result in "anonymous" user_id in the logged event


@patch("tensortours.lambda_handlers.get_tour.get_tour_table_client")
@patch("tensortours.lambda_handlers.get_tour.get_user_event_table_client")
def test_handler_with_anonymous_user(
    mock_get_user_event_table_client, mock_get_tour_table_client, sample_tour_item
):
    """Test the handler with an anonymous user (no user context)."""
    # Set up the mock tour table client
    mock_tour_client = MagicMock(spec=TourTableClient)
    mock_tour_client.get_item.return_value = sample_tour_item
    mock_get_tour_table_client.return_value = mock_tour_client

    # Set up the mock user event table client with a spy to capture the actual event being logged
    mock_user_event_client = MagicMock(spec=UserEventTableClient)

    # Use a side effect to capture the event data
    event_data = {}

    def capture_event(request):
        # Simulate what happens in log_get_tour_event
        user_id = request.user.user_id if request.user else "anonymous"
        event_data["user_id"] = user_id
        event_data["event_type"] = "get_tour"
        event_data["request_data"] = request.model_dump_json()
        return None  # Return None to avoid the nonlocal issue

    mock_user_event_client.log_get_tour_event.side_effect = capture_event
    mock_get_user_event_table_client.return_value = mock_user_event_client

    # Create a sample event with explicitly empty authorizer to test anonymous user case
    event = {
        "body": {
            "place_id": "test_place_id",
            "tour_type": TourType.HISTORY.value,
        },
        "requestContext": {"authorizer": {}, "requestId": "test-request-id-3"},  # Empty authorizer
    }

    # Call the handler
    response = handler(event, {})

    # Check that the response is correct
    assert response["statusCode"] == 200

    # Verify that the user event was logged with "anonymous" user_id
    mock_user_event_client.log_get_tour_event.assert_called_once()
    assert event_data["user_id"] == "anonymous"
    assert event_data["event_type"] == "get_tour"
    assert "place_id" in event_data["request_data"]
    assert "tour_type" in event_data["request_data"]
