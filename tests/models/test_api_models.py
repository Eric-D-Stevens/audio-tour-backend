"""Unit tests for API models using pytest."""

from datetime import datetime

import pytest

from tensortours.models.api import (
    GenerateTourRequest,
    GenerateTourResponse,
    GetPlacesRequest,
    GetPlacesResponse,
    GetPregeneratedTourRequest,
    GetPregeneratedTourResponse,
)
from tensortours.models.tour import TourType, TTAudio, TTour, TTPlaceInfo, TTPlacePhotos, TTScript


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
        audio_id="test_audio_id",
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
