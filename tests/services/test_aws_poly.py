"""Unit tests for AWS Polly client using pytest and moto."""

import io
import os
from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from tensortours.services.aws_poly import AWSPollyClient


@pytest.fixture(scope="function")
def aws_credentials():
    """Mocked AWS Credentials for boto3."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture(scope="function")
def s3(aws_credentials):
    """S3 resource."""
    with mock_aws():
        yield boto3.resource("s3", region_name="us-east-1")


@pytest.fixture(scope="function")
def s3_bucket(s3):
    """S3 bucket."""
    # Create the bucket
    bucket_name = "test-audio-bucket"
    s3.create_bucket(Bucket=bucket_name)
    return bucket_name


@pytest.fixture
def mock_polly_response():
    """Mock response from AWS Polly synthesize_speech."""
    # Create a mock audio stream
    audio_content = b"mock audio content"
    audio_stream = io.BytesIO(audio_content)

    # Create a mock response
    return {"AudioStream": audio_stream, "ContentType": "audio/mpeg", "RequestCharacters": 10}


@pytest.fixture
def aws_polly_client():
    """AWS Polly client."""
    return AWSPollyClient(voice_id="Amy", engine="neural")


def test_synthesize_speech_to_s3(aws_polly_client, s3_bucket, mock_polly_response):
    """Test synthesizing speech and writing to S3."""
    # Mock the Polly client's synthesize_speech method
    with patch.object(
        aws_polly_client.client, "synthesize_speech", return_value=mock_polly_response
    ):
        # Call the method under test
        result = aws_polly_client.synthesize_speech_to_s3(
            text="Hello, world!",
            bucket=s3_bucket,
            key="test/audio.mp3",
            output_format="mp3",
            sample_rate="22050",
            metadata={"test_key": "test_value"},
        )

        # Verify the result
        assert result["s3_uri"] == f"s3://{s3_bucket}/test/audio.mp3"
        assert result["content_type"] == "audio/mpeg"

        # Verify the file was uploaded to S3
        s3_client = boto3.client("s3", region_name="us-east-1")
        response = s3_client.head_object(Bucket=s3_bucket, Key="test/audio.mp3")

        # Check metadata
        assert response["Metadata"]["test_key"] == "test_value"

        # Check content type
        assert response["ContentType"] == "audio/mpeg"


def test_synthesize_speech_to_s3_with_defaults(aws_polly_client, s3_bucket, mock_polly_response):
    """Test synthesizing speech with default parameters."""
    # Mock the Polly client's synthesize_speech method
    with patch.object(
        aws_polly_client.client, "synthesize_speech", return_value=mock_polly_response
    ):
        # Call the method with minimal parameters
        result = aws_polly_client.synthesize_speech_to_s3(
            text="Test with defaults", bucket=s3_bucket, key="test/defaults.mp3"
        )

        # Verify the result
        assert result["s3_uri"] == f"s3://{s3_bucket}/test/defaults.mp3"
        assert result["content_type"] == "audio/mpeg"


def test_synthesize_speech_to_s3_client_error(aws_polly_client, s3_bucket):
    """Test handling of ClientError during synthesis."""
    # Mock the Polly client to raise a ClientError
    # Use a properly typed error response for ClientError
    with patch.object(
        aws_polly_client.client,
        "synthesize_speech",
        side_effect=ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "SynthesizeSpeech",
        ),
    ):
        # Call the method and expect an exception
        with pytest.raises(ClientError) as excinfo:
            aws_polly_client.synthesize_speech_to_s3(
                text="Error test", bucket=s3_bucket, key="test/error.mp3"
            )

        # Verify the error
        assert "ThrottlingException" in str(excinfo.value)
        assert "Rate exceeded" in str(excinfo.value)


def test_synthesize_speech_to_s3_with_custom_content_type(
    aws_polly_client, s3_bucket, mock_polly_response
):
    """Test synthesizing speech with a custom content type."""
    # Mock the Polly client's synthesize_speech method
    with patch.object(
        aws_polly_client.client, "synthesize_speech", return_value=mock_polly_response
    ):
        # Call the method with a custom content type
        result = aws_polly_client.synthesize_speech_to_s3(
            text="Custom content type test",
            bucket=s3_bucket,
            key="test/custom.mp3",
            content_type="application/custom",
        )

        # Verify the result
        assert result["content_type"] == "application/custom"

        # Verify the file was uploaded with the custom content type
        s3_client = boto3.client("s3", region_name="us-east-1")
        response = s3_client.head_object(Bucket=s3_bucket, Key="test/custom.mp3")
        assert response["ContentType"] == "application/custom"
