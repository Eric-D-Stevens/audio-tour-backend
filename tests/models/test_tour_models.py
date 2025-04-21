"""Unit tests for Tour models using pytest."""
import pytest
from datetime import datetime
from typing import Dict, List

from tensortours.models.tour import (
    TourType,
    TTPlaceInfo,
    TTPlacePhotos,
    TTScript,
    TTAudio,
    TTour
)


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
        place_location={"lat": 37.7749, "lng": -122.4194}
    )


@pytest.fixture
def sample_photo():
    """Create a sample photo for testing."""
    return TTPlacePhotos(
        photo_id="test_photo_id",
        place_id="test_place_id",
        cloudfront_url="https://example.com/photo.jpg",
        s3_url="https://s3.example.com/photo.jpg",
        attribution={"author": "Test Author", "source": "Test Source"},
        size_width=800,
        size_height=600
    )


@pytest.fixture
def sample_script():
    """Create a sample script for testing."""
    return TTScript(
        script_id="test_script_id",
        place_id="test_place_id",
        place_name="Test Place",
        tour_type=TourType.ARCHITECTURE,
        model_info={"model": "test_model", "version": "1.0"},
        s3_url="https://s3.example.com/script.txt",
        cloudfront_url="https://example.com/script.txt"
    )


@pytest.fixture
def sample_audio():
    """Create a sample audio for testing."""
    return TTAudio(
        audio_id="test_audio_id",
        place_id="test_place_id",
        script_id="test_script_id",
        cloudfront_url="https://example.com/audio.mp3",
        s3_url="https://s3.example.com/audio.mp3",
        model_info={"model": "test_model", "version": "1.0"}
    )


@pytest.fixture
def sample_tour(sample_place_info, sample_photo, sample_script, sample_audio):
    """Create a sample tour for testing."""
    return TTour(
        place_id="test_place_id",
        tour_type=TourType.ARCHITECTURE,
        place_info=sample_place_info,
        photos=[sample_photo],
        script=sample_script,
        audio=sample_audio
    )


def test_tour_type_enum():
    """Test TourType enum values."""
    assert TourType.HISTORY.value == "history"
    assert TourType.CULTURE.value == "cultural"
    assert TourType.ARCHITECTURE.value == "architecture"
    assert TourType.ART.value == "art"
    assert TourType.NATURE.value == "nature"


def test_place_info_model(sample_place_info):
    """Test TTPlaceInfo model."""
    # Test the fixture
    assert sample_place_info.place_id == "test_place_id"
    assert sample_place_info.place_name == "Test Place"
    assert sample_place_info.place_editorial_summary == "A test place for unit testing"
    assert sample_place_info.place_address == "123 Test St, Test City, TS 12345"
    assert sample_place_info.place_primary_type == "test_type"
    assert sample_place_info.place_types == ["test_type", "another_type"]
    assert sample_place_info.place_location == {"lat": 37.7749, "lng": -122.4194}
    assert isinstance(sample_place_info.retrieved_at, datetime)


def test_place_photos_model(sample_photo):
    """Test TTPlacePhotos model."""
    # Test the fixture
    assert sample_photo.photo_id == "test_photo_id"
    assert sample_photo.place_id == "test_place_id"
    assert str(sample_photo.cloudfront_url) == "https://example.com/photo.jpg"
    assert str(sample_photo.s3_url) == "https://s3.example.com/photo.jpg"
    assert sample_photo.attribution == {"author": "Test Author", "source": "Test Source"}
    assert sample_photo.size_width == 800
    assert sample_photo.size_height == 600
    assert isinstance(sample_photo.retrieved_at, datetime)


def test_script_model(sample_script):
    """Test TTScript model."""
    # Test the fixture
    assert sample_script.script_id == "test_script_id"
    assert sample_script.place_id == "test_place_id"
    assert sample_script.place_name == "Test Place"
    assert sample_script.tour_type == TourType.ARCHITECTURE
    assert sample_script.model_info == {"model": "test_model", "version": "1.0"}
    assert str(sample_script.s3_url) == "https://s3.example.com/script.txt"
    assert str(sample_script.cloudfront_url) == "https://example.com/script.txt"
    assert isinstance(sample_script.generated_at, datetime)
    
    # Test with a different tour type
    history_script = TTScript(
        script_id="history_script_id",
        place_id="test_place_id",
        place_name="Test Place",
        tour_type=TourType.HISTORY,
        model_info={"model": "test_model", "version": "1.0"},
        s3_url="https://s3.example.com/script.txt",
        cloudfront_url="https://example.com/script.txt"
    )
    
    assert history_script.tour_type == TourType.HISTORY


def test_audio_model(sample_audio):
    """Test TTAudio model."""
    # Test the fixture
    assert sample_audio.audio_id == "test_audio_id"
    assert sample_audio.place_id == "test_place_id"
    assert sample_audio.script_id == "test_script_id"
    assert str(sample_audio.cloudfront_url) == "https://example.com/audio.mp3"
    assert str(sample_audio.s3_url) == "https://s3.example.com/audio.mp3"
    assert sample_audio.model_info == {"model": "test_model", "version": "1.0"}
    assert isinstance(sample_audio.generated_at, datetime)


def test_tour_model(sample_tour, sample_place_info, sample_photo, sample_script, sample_audio):
    """Test TTour model."""
    # Test the fixture
    assert sample_tour.place_id == "test_place_id"
    assert sample_tour.tour_type == TourType.ARCHITECTURE
    assert sample_tour.place_info.place_name == "Test Place"
    assert len(sample_tour.photos) == 1
    assert sample_tour.photos[0].photo_id == "test_photo_id"
    assert sample_tour.script.script_id == "test_script_id"
    assert sample_tour.audio.audio_id == "test_audio_id"
