"""Unit tests for Tour table service using pytest and moto."""

import os
from datetime import datetime

import boto3
import pytest
from moto import mock_aws

from tensortours.models.tour import TourType, TTAudio, TTour, TTPlaceInfo, TTPlacePhotos, TTScript
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

    # Return the table
    return table


@pytest.fixture(scope="function")
def tour_table_client(dynamodb_table):
    """Tour table client."""
    return TourTableClient()


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
        script=sample_script,  # Note: changed from scripts to script
        audio=sample_audio,
        created_at=datetime(2025, 4, 20, 18, 17, 45, 602044),
    )


def test_put_and_get_item(tour_table_client, sample_tour_table_item):
    """Test putting and getting an item from the table."""
    # Put the item in the table
    tour_table_client.put_item(sample_tour_table_item)

    # Get the item from the table
    retrieved_item = tour_table_client.get_item(
        place_id=sample_tour_table_item.place_id, tour_type=sample_tour_table_item.tour_type
    )

    # Verify the item was retrieved correctly
    assert retrieved_item is not None
    assert retrieved_item.place_id == sample_tour_table_item.place_id
    assert retrieved_item.tour_type == sample_tour_table_item.tour_type
    assert retrieved_item.place_info.place_name == sample_tour_table_item.place_info.place_name
    assert retrieved_item.status == sample_tour_table_item.status
    assert len(retrieved_item.photos) == len(sample_tour_table_item.photos)
    assert retrieved_item.photos[0].photo_id == sample_tour_table_item.photos[0].photo_id
    assert retrieved_item.script.script_id == sample_tour_table_item.script.script_id
    assert retrieved_item.audio.script_id == sample_tour_table_item.audio.script_id


def test_get_nonexistent_item(tour_table_client):
    """Test getting a nonexistent item from the table."""
    # Get a nonexistent item
    retrieved_item = tour_table_client.get_item(
        place_id="nonexistent_place_id", tour_type=TourType.ARCHITECTURE
    )

    # Verify the item is None
    assert retrieved_item is None


def test_delete_item(tour_table_client, sample_tour_table_item):
    """Test deleting an item from the table."""
    # Put the item in the table
    tour_table_client.put_item(sample_tour_table_item)

    # Delete the item
    tour_table_client.delete_item(
        place_id=sample_tour_table_item.place_id, tour_type=sample_tour_table_item.tour_type
    )

    # Try to get the deleted item
    retrieved_item = tour_table_client.get_item(
        place_id=sample_tour_table_item.place_id, tour_type=sample_tour_table_item.tour_type
    )

    # Verify the item is None
    assert retrieved_item is None


def test_convert_to_tour(tour_table_client, sample_tour_table_item):
    """Test converting a TourTableItem to a TTour."""
    # Put the item in the table
    tour_table_client.put_item(sample_tour_table_item)

    # Get the item from the table
    retrieved_item = tour_table_client.get_item(
        place_id=sample_tour_table_item.place_id, tour_type=sample_tour_table_item.tour_type
    )

    # Convert to TTour
    tour = TTour(
        place_id=retrieved_item.place_id,
        tour_type=retrieved_item.tour_type,
        place_info=retrieved_item.place_info,
        photos=retrieved_item.photos,
        script=retrieved_item.script,
        audio=retrieved_item.audio,
    )

    # Verify the tour was created correctly
    assert tour.place_id == sample_tour_table_item.place_id
    assert tour.tour_type == sample_tour_table_item.tour_type
    assert tour.place_info.place_name == sample_tour_table_item.place_info.place_name
    assert len(tour.photos) == len(sample_tour_table_item.photos)
    assert tour.photos[0].photo_id == sample_tour_table_item.photos[0].photo_id
    assert tour.script.script_id == sample_tour_table_item.script.script_id
    assert tour.audio.script_id == sample_tour_table_item.audio.script_id
