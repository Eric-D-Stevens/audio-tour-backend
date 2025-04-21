"""Unit tests for the get_places lambda handler."""

import json
import os
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from tensortours.lambda_handlers.get_places import handler, transform_google_places_to_tt_place_info
from tensortours.models.api import GetPlacesRequest
from tensortours.models.tour import TourType, TourTypeToGooglePlaceTypes, TTPlaceInfo
from tensortours.services.google_places import GooglePlacesClient
from tensortours.services.tour_table import GenerationStatus, TourTableItem
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
def sqs_queue(aws_credentials):
    """SQS queue for testing."""
    with mock_aws():
        # Create the SQS client
        sqs = boto3.resource("sqs", region_name="us-east-1")

        # Create the queue
        queue = sqs.create_queue(QueueName="test-generation-queue")

        # Set the environment variable for the queue URL
        os.environ["TOUR_GENERATION_QUEUE_URL"] = queue.url

        yield queue


@pytest.fixture
def sample_google_places_response():
    """Sample Google Places API response for testing."""
    return {
        "places": [
            {
                "id": "test_place_id_1",
                "displayName": {"text": "Test Museum"},
                "location": {"latitude": 37.7749, "longitude": -122.4194},
                "formattedAddress": "123 Test St, Test City, TC 12345",
                "rating": 4.5,
                "userRatingCount": 100,
                "types": ["museum", "tourist_attraction"],
                "primaryType": "museum",
                "editorialSummary": {"text": "A fascinating museum with historical artifacts."},
            },
            {
                "id": "test_place_id_2",
                "displayName": {"text": "Test Monument"},
                "location": {"latitude": 37.7750, "longitude": -122.4195},
                "formattedAddress": "456 Monument Ave, Test City, TC 12345",
                "rating": 4.7,
                "userRatingCount": 200,
                "types": ["monument", "tourist_attraction", "historical_landmark"],
                "primaryType": "monument",
                "editorialSummary": {
                    "text": "A beautiful monument commemorating historical events."
                },
            },
        ]
    }


def test_transform_google_places_to_tt_place_info(sample_google_places_response):
    """Test the transformation of Google Places API response to TTPlaceInfo objects."""
    # Call the transformation function
    places = transform_google_places_to_tt_place_info(sample_google_places_response)

    # Check that the correct number of places were returned
    assert len(places) == 2

    # Check the first place
    place1 = places[0]
    assert isinstance(place1, TTPlaceInfo)
    assert place1.place_id == "test_place_id_1"
    assert place1.place_name == "Test Museum"
    assert place1.place_editorial_summary == "A fascinating museum with historical artifacts."
    assert place1.place_address == "123 Test St, Test City, TC 12345"
    assert place1.place_primary_type == "museum"
    assert place1.place_types == ["museum", "tourist_attraction"]
    assert place1.place_location["latitude"] == 37.7749
    assert place1.place_location["longitude"] == -122.4194

    # Check the second place
    place2 = places[1]
    assert isinstance(place2, TTPlaceInfo)
    assert place2.place_id == "test_place_id_2"
    assert place2.place_name == "Test Monument"
    assert place2.place_editorial_summary == "A beautiful monument commemorating historical events."
    assert place2.place_address == "456 Monument Ave, Test City, TC 12345"
    assert place2.place_primary_type == "monument"
    assert place2.place_types == ["monument", "tourist_attraction", "historical_landmark"]
    assert place2.place_location["latitude"] == 37.7750
    assert place2.place_location["longitude"] == -122.4195


@patch("tensortours.lambda_handlers.get_places.get_google_places_client")
@patch("tensortours.lambda_handlers.get_places.get_user_event_table_client")
@patch("tensortours.lambda_handlers.get_places.get_tour_table_client")
@patch("tensortours.lambda_handlers.get_places.get_generation_queue")
def test_handler_success(
    mock_get_generation_queue,
    mock_get_tour_table_client,
    mock_get_user_event_table_client,
    mock_get_google_places_client,
    sample_google_places_response,
):
    """Test the handler with a successful places retrieval."""
    # Set up the mock Google Places client
    mock_google_client = MagicMock(spec=GooglePlacesClient)
    mock_google_client.search_nearby.return_value = sample_google_places_response
    mock_get_google_places_client.return_value = mock_google_client

    # Set up the mock user event table client
    mock_user_event_client = MagicMock(spec=UserEventTableClient)
    mock_get_user_event_table_client.return_value = mock_user_event_client

    # Set up the mock tour table client
    mock_tour_table_client = MagicMock()
    mock_get_tour_table_client.return_value = mock_tour_table_client

    # Set up the mock generation queue
    mock_queue = MagicMock()
    mock_get_generation_queue.return_value = mock_queue

    # Create a sample event with authenticated user context
    event = {
        "body": {
            "tour_type": TourType.HISTORY.value,
            "latitude": 37.7749,
            "longitude": -122.4194,
            "radius": 1000,
            "max_results": 20,
        },
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
    assert "places" in response_body
    assert len(response_body["places"]) == 2
    assert response_body["total_count"] == 2
    assert response_body["is_authenticated"] is True

    # Check the first place in the response
    place1 = response_body["places"][0]
    assert place1["place_id"] == "test_place_id_1"
    assert place1["place_name"] == "Test Museum"

    # Verify that the Google Places client was called correctly
    expected_place_types = TourTypeToGooglePlaceTypes.get_place_types(TourType.HISTORY)
    mock_google_client.search_nearby.assert_called_once_with(
        latitude=37.7749,
        longitude=-122.4194,
        radius=1000,
        include_types=expected_place_types,
        exclude_types=[],
        max_results=20,
    )

    # Verify that the user event table client was called to log the event
    mock_user_event_client.log_get_places_event.assert_called_once()

    # Verify the request passed to log_get_places_event
    log_call_args = mock_user_event_client.log_get_places_event.call_args[0][0]
    assert isinstance(log_call_args, GetPlacesRequest)
    assert log_call_args.tour_type == TourType.HISTORY
    assert log_call_args.latitude == 37.7749
    assert log_call_args.longitude == -122.4194
    # Now the user information should be properly extracted
    assert log_call_args.user is not None
    assert log_call_args.user.user_id == "test_user_123"
    assert log_call_args.user.username == "testuser"
    assert log_call_args.user.email == "test@example.com"
    assert "users" in log_call_args.user.groups


@patch("tensortours.lambda_handlers.get_places.get_google_places_client")
@patch("tensortours.lambda_handlers.get_places.get_user_event_table_client")
@patch("tensortours.lambda_handlers.get_places.get_tour_table_client")
@patch("tensortours.lambda_handlers.get_places.get_generation_queue")
def test_handler_with_anonymous_user(
    mock_get_generation_queue,
    mock_get_tour_table_client,
    mock_get_user_event_table_client,
    mock_get_google_places_client,
    sample_google_places_response,
):
    """Test the handler with an anonymous user (no user context)."""
    # Set up the mock Google Places client
    mock_google_client = MagicMock(spec=GooglePlacesClient)
    mock_google_client.search_nearby.return_value = sample_google_places_response
    mock_get_google_places_client.return_value = mock_google_client

    # Set up the mock user event table client with a spy to capture the actual event being logged
    mock_user_event_client = MagicMock(spec=UserEventTableClient)

    # Use a side effect to capture the event data
    event_data = {}

    def capture_event(request):
        # Simulate what happens in log_get_places_event
        user_id = request.user.user_id if request.user else "anonymous"
        event_data["user_id"] = user_id
        event_data["event_type"] = "get_places"
        event_data["request_data"] = request.model_dump_json()
        return None  # Return None to avoid the nonlocal issue

    mock_user_event_client.log_get_places_event.side_effect = capture_event
    mock_get_user_event_table_client.return_value = mock_user_event_client

    # Set up the mock tour table client
    mock_tour_table_client = MagicMock()
    mock_tour_table_client.get_item.return_value = None
    mock_get_tour_table_client.return_value = mock_tour_table_client

    # Set up the mock generation queue
    mock_queue = MagicMock()
    mock_get_generation_queue.return_value = mock_queue

    # Create a sample event with explicitly empty authorizer to test anonymous user case
    event = {
        "body": {
            "tour_type": TourType.CULTURE.value,
            "latitude": 37.7749,
            "longitude": -122.4194,
            "radius": 1000,
            "max_results": 20,
        },
        "requestContext": {"authorizer": {}, "requestId": "test-request-id-3"},  # Empty authorizer
    }

    # Call the handler
    response = handler(event, {})

    # Check that the response is correct
    assert response["statusCode"] == 200
    response_body = json.loads(response["body"])
    assert "places" in response_body
    assert response_body["is_authenticated"] is False

    # Verify that the user event was logged with "anonymous" user_id
    mock_user_event_client.log_get_places_event.assert_called_once()
    assert event_data["user_id"] == "anonymous"
    assert event_data["event_type"] == "get_places"
    assert "tour_type" in event_data["request_data"]
    assert "latitude" in event_data["request_data"]
    assert "longitude" in event_data["request_data"]


@patch("tensortours.lambda_handlers.get_places.get_google_places_client")
@patch("tensortours.lambda_handlers.get_places.get_user_event_table_client")
@patch("tensortours.lambda_handlers.get_places.get_tour_table_client")
@patch("tensortours.lambda_handlers.get_places.get_generation_queue")
def test_handler_error_handling(
    mock_get_generation_queue,
    mock_get_tour_table_client,
    mock_get_user_event_table_client,
    mock_get_google_places_client,
):
    """Test the handler when the Google Places API call fails."""
    # Set up the mock Google Places client to raise an exception
    mock_google_client = MagicMock(spec=GooglePlacesClient)
    mock_google_client.search_nearby.side_effect = Exception("API Error")
    mock_get_google_places_client.return_value = mock_google_client

    # Set up the mock user event table client
    mock_user_event_client = MagicMock(spec=UserEventTableClient)
    mock_get_user_event_table_client.return_value = mock_user_event_client

    # Set up the mock tour table client
    mock_tour_table_client = MagicMock()
    mock_get_tour_table_client.return_value = mock_tour_table_client

    # Set up the mock generation queue
    mock_queue = MagicMock()
    mock_get_generation_queue.return_value = mock_queue

    # Create a sample event
    event = {
        "body": {
            "tour_type": TourType.ARCHITECTURE.value,
            "latitude": 37.7749,
            "longitude": -122.4194,
            "radius": 1000,
            "max_results": 20,
        },
        "requestContext": {"requestId": "test-request-id-4"},
    }

    # Call the handler
    response = handler(event, {})

    # Check that the response is a 500 error
    assert response["statusCode"] == 500
    response_body = json.loads(response["body"])
    assert "error" in response_body
    assert "Failed to get places" in response_body["error"]

    # Verify that the Google Places client was called
    expected_place_types = TourTypeToGooglePlaceTypes.get_place_types(TourType.ARCHITECTURE)
    mock_google_client.search_nearby.assert_called_once_with(
        latitude=37.7749,
        longitude=-122.4194,
        radius=1000,
        include_types=expected_place_types,
        exclude_types=[],
        max_results=20,
    )

    # Verify that the user event was still logged even though the API call failed
    mock_user_event_client.log_get_places_event.assert_called_once()


@patch("tensortours.lambda_handlers.get_places.get_google_places_client")
@patch("tensortours.lambda_handlers.get_places.get_user_event_table_client")
@patch("tensortours.lambda_handlers.get_places.get_tour_table_client")
@patch("tensortours.lambda_handlers.get_places.get_generation_queue")
def test_handler_forwards_to_generation_queue(
    mock_get_generation_queue,
    mock_get_tour_table_client,
    mock_get_user_event_table_client,
    mock_get_google_places_client,
    sample_google_places_response,
):
    """Test that the handler forwards places to the generation queue if they don't exist in the tour table."""
    # Set up the mock Google Places client
    mock_google_client = MagicMock(spec=GooglePlacesClient)
    mock_google_client.search_nearby.return_value = sample_google_places_response
    mock_get_google_places_client.return_value = mock_google_client

    # Set up the mock user event table client
    mock_user_event_client = MagicMock(spec=UserEventTableClient)
    mock_get_user_event_table_client.return_value = mock_user_event_client

    # Set up the mock tour table client
    mock_tour_table_client = MagicMock()
    mock_get_tour_table_client.return_value = mock_tour_table_client

    # Set up the mock generation queue
    mock_queue = MagicMock()
    mock_get_generation_queue.return_value = mock_queue

    # Set up the mock tour table client to return None for get_item (place doesn't exist)
    mock_tour_table_client = MagicMock()
    mock_tour_table_client.get_item.return_value = None
    mock_get_tour_table_client.return_value = mock_tour_table_client

    # Set up the mock generation queue
    mock_queue = MagicMock()
    mock_get_generation_queue.return_value = mock_queue

    # Create a sample event with authenticated user context
    event = {
        "body": {
            "tour_type": TourType.HISTORY.value,
            "latitude": 37.7749,
            "longitude": -122.4194,
            "radius": 1000,
            "max_results": 20,
        },
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

    # Verify that the tour table client was called to check if the places exist
    assert mock_tour_table_client.get_item.call_count == 2  # Two places in the sample response

    # Verify that the queue's send_message method was called twice (once for each place)
    assert mock_queue.send_message.call_count == 2

    # Get the call arguments for each send_message call
    call_args_list = mock_queue.send_message.call_args_list

    # Verify that each message contains the expected place ID
    place_ids = []
    for call in call_args_list:
        message_body = call.kwargs["MessageBody"]
        message_data = json.loads(message_body)
        place_ids.append(message_data["place_id"])
        assert message_data["tour_type"] == TourType.HISTORY.value
        assert message_data["user_id"] == "test_user_123"  # Should have the authenticated user ID

    # Verify that both place IDs are included
    assert "test_place_id_1" in place_ids
    assert "test_place_id_2" in place_ids


@patch("tensortours.lambda_handlers.get_places.get_google_places_client")
@patch("tensortours.lambda_handlers.get_places.get_user_event_table_client")
@patch("tensortours.lambda_handlers.get_places.get_tour_table_client")
@patch("tensortours.lambda_handlers.get_places.get_generation_queue")
def test_handler_skips_existing_completed_places(
    mock_get_generation_queue,
    mock_get_tour_table_client,
    mock_get_user_event_table_client,
    mock_get_google_places_client,
    sample_google_places_response,
):
    """Test that the handler doesn't forward places to the generation queue if they already exist in the tour table with COMPLETED status."""
    # Set up the mock Google Places client
    mock_google_client = MagicMock(spec=GooglePlacesClient)
    mock_google_client.search_nearby.return_value = sample_google_places_response
    mock_get_google_places_client.return_value = mock_google_client

    # Set up the mock user event table client
    mock_user_event_client = MagicMock(spec=UserEventTableClient)
    mock_get_user_event_table_client.return_value = mock_user_event_client

    # Set up the mock tour table client
    mock_tour_table_client = MagicMock()
    mock_get_tour_table_client.return_value = mock_tour_table_client

    # Set up the mock generation queue
    mock_queue = MagicMock()
    mock_get_generation_queue.return_value = mock_queue

    # Create a place info object for the first place
    place_info = TTPlaceInfo(
        place_id="test_place_id_1",
        place_name="Test Museum",
        place_editorial_summary="A fascinating museum with historical artifacts.",
        place_address="123 Test St, Test City, TC 12345",
        place_primary_type="museum",
        place_types=["museum", "tourist_attraction"],
        place_location={"latitude": 37.7749, "longitude": -122.4194},
    )

    # Create a completed tour table item for the first place
    completed_item = TourTableItem(
        place_id="test_place_id_1",
        tour_type=TourType.HISTORY,
        place_info=place_info,
        status=GenerationStatus.COMPLETED,
        photos=None,
        script=None,
        audio=None,
    )

    # Set up the mock tour table client to return the completed item for the first place
    # and None for the second place
    def mock_get_item(place_id, tour_type):
        if place_id == "test_place_id_1" and tour_type == TourType.HISTORY:
            return completed_item
        return None

    mock_tour_table_client = MagicMock()
    mock_tour_table_client.get_item.side_effect = mock_get_item
    mock_get_tour_table_client.return_value = mock_tour_table_client

    # Set up the mock generation queue
    mock_queue = MagicMock()
    mock_get_generation_queue.return_value = mock_queue

    # Create a sample event with authenticated user context
    event = {
        "body": {
            "tour_type": TourType.HISTORY.value,
            "latitude": 37.7749,
            "longitude": -122.4194,
            "radius": 1000,
            "max_results": 20,
        },
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

    # Verify that the tour table client was called to check if the places exist
    assert mock_tour_table_client.get_item.call_count == 2  # Two places in the sample response

    # Verify that the queue's send_message method was called once (only for the second place)
    assert mock_queue.send_message.call_count == 1

    # Get the call arguments for the send_message call
    call_args = mock_queue.send_message.call_args

    # Verify that the message contains the expected place ID
    message_body = call_args.kwargs["MessageBody"]
    message_data = json.loads(message_body)
    assert (
        message_data["place_id"] == "test_place_id_2"
    )  # Only the second place should be forwarded
    assert message_data["tour_type"] == TourType.HISTORY.value
    assert message_data["user_id"] == "test_user_123"
