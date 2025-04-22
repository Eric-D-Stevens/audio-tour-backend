"""Unit tests for API models using pytest."""

from datetime import datetime

import pytest

from tensortours.models.api import (
    BaseRequest,
    CognitoUser,
    GenerateTourRequest,
    GenerateTourResponse,
    GetPlacesRequest,
    GetPlacesResponse,
    GetPregeneratedTourRequest,
    GetPregeneratedTourResponse,
)
from tensortours.models.tour import TourType, TTAudio, TTour, TTPlaceInfo, TTPlacePhotos, TTScript


@pytest.fixture
def sample_cognito_claims():
    """Create sample Cognito claims for testing."""
    return {
        "sub": "12345678-1234-1234-1234-123456789012",
        "cognito:username": "testuser",
        "email": "test@example.com",
        "cognito:groups": "premium,beta-tester",
    }


@pytest.fixture
def sample_request_context(sample_cognito_claims):
    """Create a sample API Gateway request context with Cognito authorizer."""
    return {"requestId": "request-123", "authorizer": {"claims": sample_cognito_claims}}


@pytest.fixture
def sample_lambda_event(sample_request_context):
    """Create a sample Lambda event with request context."""
    return {
        "httpMethod": "GET",
        "path": "/places",
        "queryStringParameters": {"lat": "37.7749", "lng": "-122.4194", "tour_type": "history"},
        "requestContext": sample_request_context,
    }


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
        retrieved_at=datetime.now(),
    )


@pytest.fixture
def sample_tour(sample_place_info):
    """Create a sample tour for testing."""
    # Create sample photo
    photo = TTPlacePhotos(
        photo_id="test_photo_id",
        place_id="test_place_id",
        cloudfront_url="https://example.com/photo.jpg",
        s3_url="https://s3.example.com/photo.jpg",
        attribution={"author": "Test Author", "source": "Test Source"},
        size_width=800,
        size_height=600,
        retrieved_at=datetime.now(),
    )

    # Create sample script
    script = TTScript(
        script_id="test_script_id",
        place_id="test_place_id",
        place_name="Test Place",
        tour_type=TourType.ARCHITECTURE,
        model_info={"model": "test_model", "version": "1.0"},
        s3_url="https://s3.example.com/script.txt",
        cloudfront_url="https://example.com/script.txt",
        generated_at=datetime.now(),
    )

    # Create sample audio
    audio = TTAudio(
        place_id="test_place_id",
        script_id="test_script_id",
        cloudfront_url="https://example.com/audio.mp3",
        s3_url="https://s3.example.com/audio.mp3",
        model_info={"model": "test_model", "version": "1.0"},
        generated_at=datetime.now(),
    )

    # Create sample tour
    return TTour(
        place_id="test_place_id",
        tour_type=TourType.ARCHITECTURE,
        place_info=sample_place_info,
        photos=[photo],
        script=script,
        audio=audio,
    )


def test_get_places_request():
    """Test GetPlacesRequest model."""
    # Test valid request
    request = GetPlacesRequest(
        tour_type=TourType.HISTORY,
        latitude=37.7749,
        longitude=-122.4194,
        radius=1000,
        max_results=10,
    )

    assert request.tour_type == TourType.HISTORY
    assert request.latitude == 37.7749
    assert request.longitude == -122.4194
    assert request.radius == 1000
    assert request.max_results == 10

    # Test with default values
    request = GetPlacesRequest(
        tour_type=TourType.CULTURE,
        latitude=37.7749,
        longitude=-122.4194,
    )

    assert request.tour_type == TourType.CULTURE
    assert request.latitude == 37.7749
    assert request.longitude == -122.4194
    assert request.radius == 1000  # Default value
    assert request.max_results == 20  # Default value


def test_get_places_response(sample_place_info):
    """Test GetPlacesResponse model."""
    # Test valid response
    response = GetPlacesResponse(places=[sample_place_info], total_count=1)

    assert len(response.places) == 1
    assert response.places[0].place_id == "test_place_id"
    assert response.total_count == 1
    assert response.is_authenticated is False  # Default value

    # Test with authentication flag
    response = GetPlacesResponse(places=[sample_place_info], total_count=1, is_authenticated=True)
    assert response.is_authenticated is True


def test_get_pregenerated_tour_request():
    """Test GetPregeneratedTourRequest model."""
    # Test valid request
    request = GetPregeneratedTourRequest(place_id="test_place_id", tour_type=TourType.ARCHITECTURE)

    assert request.place_id == "test_place_id"
    assert request.tour_type == TourType.ARCHITECTURE


def test_get_pregenerated_tour_response(sample_tour):
    """Test GetPregeneratedTourResponse model."""
    # Test valid response
    response = GetPregeneratedTourResponse(tour=sample_tour)

    assert response.tour.place_id == "test_place_id"
    assert response.tour.tour_type == TourType.ARCHITECTURE
    assert len(response.tour.photos) == 1
    assert response.is_authenticated is False  # Default value

    # Test with authentication flag
    response = GetPregeneratedTourResponse(tour=sample_tour, is_authenticated=True)
    assert response.is_authenticated is True


def test_generate_tour_request():
    """Test GenerateTourRequest model."""
    # Test valid request
    request = GenerateTourRequest(
        place_id="test_place_id", tour_type=TourType.NATURE, language_code="en"
    )

    assert request.place_id == "test_place_id"
    assert request.tour_type == TourType.NATURE
    assert request.language_code == "en"

    # Test with default values
    request = GenerateTourRequest(place_id="test_place_id", tour_type=TourType.NATURE)

    assert request.language_code == "en"  # Default value


def test_generate_tour_response(sample_tour):
    """Test GenerateTourResponse model."""
    # Test valid response
    response = GenerateTourResponse(tour=sample_tour)

    assert response.tour.place_id == "test_place_id"
    assert response.tour.tour_type == TourType.ARCHITECTURE
    assert response.is_authenticated is False  # Default value

    # Test with authentication flag
    response = GenerateTourResponse(tour=sample_tour, is_authenticated=True)
    assert response.is_authenticated is True


def test_cognito_user(sample_cognito_claims):
    """Test CognitoUser model."""
    # Test direct creation
    user = CognitoUser(
        user_id="12345678-1234-1234-1234-123456789012",
        username="testuser",
        email="test@example.com",
        groups=["premium", "beta-tester"],
    )

    assert user.user_id == "12345678-1234-1234-1234-123456789012"
    assert user.username == "testuser"
    assert user.email == "test@example.com"
    assert "premium" in user.groups
    assert "beta-tester" in user.groups

    # Test creation from request context
    context = {"authorizer": {"claims": sample_cognito_claims}}
    user_from_context = CognitoUser.from_request_context(context)

    assert user_from_context is not None
    assert user_from_context.user_id == "12345678-1234-1234-1234-123456789012"
    assert user_from_context.username == "testuser"
    assert user_from_context.email == "test@example.com"
    assert len(user_from_context.groups) == 2
    assert "premium" in user_from_context.groups
    assert "beta-tester" in user_from_context.groups

    # Test with invalid context
    assert CognitoUser.from_request_context({}) is None
    assert CognitoUser.from_request_context({"authorizer": {}}) is None


def test_base_request_with_user(sample_lambda_event):
    """Test BaseRequest model with user information."""
    # Test with request context
    request = BaseRequest(**sample_lambda_event)

    assert request.user is not None
    assert request.user.user_id == "12345678-1234-1234-1234-123456789012"
    assert request.user.username == "testuser"
    assert request.request_id == "request-123"
    assert request.timestamp is not None

    # Test without request context
    request = BaseRequest()
    assert request.user is None
    assert request.request_id is None


def test_get_places_request_with_user(sample_lambda_event):
    """Test GetPlacesRequest with user information."""
    # Add required fields to the event
    event = sample_lambda_event.copy()
    event["queryStringParameters"]["tour_type"] = "history"
    event["queryStringParameters"]["latitude"] = 37.7749
    event["queryStringParameters"]["longitude"] = -122.4194

    # Create request from event
    request = GetPlacesRequest(
        **event["queryStringParameters"], requestContext=event["requestContext"]
    )

    assert request.tour_type == TourType.HISTORY
    assert request.latitude == 37.7749
    assert request.longitude == -122.4194
    assert request.user is not None
    assert request.user.user_id == "12345678-1234-1234-1234-123456789012"
