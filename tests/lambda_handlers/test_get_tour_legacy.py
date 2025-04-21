"""Unit tests for the get_tour Lambda handler."""

import json
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

from tensortours.lambda_handlers.get_tour import handler
from tensortours.models.tour import TourType, TTAudio, TTPlaceInfo, TTPlacePhotos, TTScript
from tensortours.services.tour_table import GenerationStatus, TourTableClient, TourTableItem


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
    # Set the table names for testing
    os.environ["TOUR_TABLE_NAME"] = "test-tour-table"
    os.environ["USER_EVENT_TABLE_NAME"] = "test-user-event-table"

    # Create the tour table
    tour_table = dynamodb.create_table(
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

    # Create the user event table
    dynamodb.create_table(
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

    # Return the tour table
    return tour_table


@pytest.fixture
def sample_place_info():
    """Create a sample place info for testing."""
    return TTPlaceInfo(
        place_id="test_place_id",
        place_name="Test Place",
        place_editorial_summary="A test place for unit testing",
        place_address="123 Test St, Test City, TS 12345",
        place_primary_type="test_type",
        place_types=["test_type", "another_type"],
        place_location={"lat": 37.7749, "lng": -122.4194},
    )


@pytest.fixture
def sample_place_photos():
    """Create a sample place photos for testing."""
    return TTPlacePhotos(
        photo_id="test_photo_id",
        place_id="test_place_id",
        cloudfront_url="https://example.com/photos/test.jpg",
        s3_url="https://s3.amazonaws.com/bucket/photos/test.jpg",
        attribution={"html": "Test Attribution", "source": "Test Source"},
        size_width=800,
        size_height=600,
    )


@pytest.fixture
def sample_script():
    """Create a sample script for testing."""
    return TTScript(
        script_id="test_script_id",
        place_id="test_place_id",
        place_name="Test Place",
        tour_type=TourType.ARCHITECTURE,
        model_info={"model": "gpt-4", "version": "1.0"},
        s3_url="https://s3.amazonaws.com/bucket/scripts/test.txt",
        cloudfront_url="https://example.com/scripts/test.txt",
    )


@pytest.fixture
def sample_audio():
    """Create a sample audio for testing."""
    return TTAudio(
        audio_id="test_audio_id",
        place_id="test_place_id",
        script_id="test_script_id",
        cloudfront_url="https://example.com/audio/test.mp3",
        s3_url="https://s3.amazonaws.com/bucket/audio/test.mp3",
        model_info={"model": "elevenlabs", "voice": "en-US-Neural2-F"},
    )


@pytest.fixture
def sample_tour_table_item(sample_place_info, sample_place_photos, sample_script, sample_audio):
    """Create a sample tour table item for testing."""
    return TourTableItem(
        place_id="test_place_id",
        tour_type=TourType.ARCHITECTURE,
        place_info=sample_place_info,
        status=GenerationStatus.COMPLETED,
        photos=[sample_place_photos],
        script=sample_script,
        audio=sample_audio,
        created_at=datetime(2025, 4, 20, 18, 17, 45, 602044),
    )


@pytest.fixture
def api_gateway_event():
    """Create a sample API Gateway event for testing."""
    return {
        "body": json.dumps({"place_id": "test_place_id", "tour_type": "architecture"}),
        "headers": {"Content-Type": "application/json"},
        "httpMethod": "POST",
        "isBase64Encoded": False,
        "path": "/tour",
        "pathParameters": None,
        "queryStringParameters": None,
        "requestContext": {
            "accountId": "123456789012",
            "resourceId": "abcdef",
            "stage": "test",
            "requestId": "test-request-id",
            "identity": {
                "cognitoIdentityPoolId": None,
                "accountId": None,
                "cognitoIdentityId": None,
                "caller": None,
                "apiKey": None,
                "sourceIp": "127.0.0.1",
                "cognitoAuthenticationType": None,
                "cognitoAuthenticationProvider": None,
                "userArn": None,
                "userAgent": "Custom User Agent String",
                "user": None,
            },
            "resourcePath": "/tour",
            "httpMethod": "POST",
            "apiId": "abcdef123456",
        },
        "resource": "/tour",
        "stageVariables": None,
    }


def test_get_tour_success(dynamodb_table, sample_tour_table_item, api_gateway_event):
    """Test getting a tour successfully."""
    # Add the tour to the DynamoDB table
    tour_table_client = TourTableClient()
    tour_table_client.put_item(sample_tour_table_item)

    # Parse the JSON string in the event body
    api_gateway_event["body"] = json.loads(api_gateway_event["body"])

    # Call the handler
    response = handler(api_gateway_event, {})

    # Verify the response
    assert response["statusCode"] == 200

    # Parse the response body
    response_body = json.loads(response["body"])

    # Verify the tour data
    assert "tour" in response_body
    tour = response_body["tour"]
    assert tour["place_id"] == sample_tour_table_item.place_id
    assert tour["tour_type"] == sample_tour_table_item.tour_type.value
    assert tour["place_info"]["place_name"] == sample_tour_table_item.place_info.place_name
    assert len(tour["photos"]) == len(sample_tour_table_item.photos)
    assert tour["photos"][0]["photo_id"] == sample_tour_table_item.photos[0].photo_id
    assert tour["script"]["script_id"] == sample_tour_table_item.script.script_id
    assert tour["audio"]["audio_id"] == sample_tour_table_item.audio.audio_id


def test_get_tour_not_found(dynamodb_table, api_gateway_event):
    """Test getting a tour that doesn't exist."""
    # Parse the JSON string in the event body
    api_gateway_event["body"] = json.loads(api_gateway_event["body"])

    # Call the handler without adding any tours to the table
    response = handler(api_gateway_event, {})

    # Verify the response
    assert response["statusCode"] == 404

    # Parse the response body
    response_body = json.loads(response["body"])

    # Verify the error message
    assert "error" in response_body
    assert response_body["error"] == "Tour not found"


@patch("tensortours.lambda_handlers.get_tour.get_user_event_table_client")
@patch("tensortours.lambda_handlers.get_tour.get_tour_table_client")
def test_get_tour_exception(mock_get_tour_client, mock_get_user_event_client, api_gateway_event):
    """Test handling an exception during tour retrieval."""
    # Mock the tour table client to raise an exception
    mock_tour_client = MagicMock()
    mock_tour_client.get_item.side_effect = Exception("Test exception")
    mock_get_tour_client.return_value = mock_tour_client

    # Mock the user event table client to avoid real DynamoDB calls
    mock_user_client = MagicMock()
    mock_get_user_event_client.return_value = mock_user_client

    # Parse the JSON string in the event body
    api_gateway_event["body"] = json.loads(api_gateway_event["body"])

    # Call the handler
    with pytest.raises(Exception) as excinfo:
        handler(api_gateway_event, {})

    # Verify the exception
    assert "Test exception" in str(excinfo.value)


def test_get_tour_invalid_request():
    """Test handling an invalid request."""
    # Create an invalid event with missing required fields
    invalid_event = {
        "body": json.dumps(
            {
                # Missing place_id and tour_type
            }
        ),
        "headers": {"Content-Type": "application/json"},
    }

    # Call the handler
    with pytest.raises(Exception) as excinfo:
        handler(invalid_event, {})

    # Verify the exception is related to validation
    assert (
        "validation error" in str(excinfo.value).lower() or "missing" in str(excinfo.value).lower()
    )
