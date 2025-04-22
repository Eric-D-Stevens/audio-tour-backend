"""Lambda handler for AWS Polly audio generation.

This module provides a Lambda handler that generates audio using AWS Polly and stores it in S3.
It's designed to be triggered directly with an invoke call and raises exceptions
when errors occur, allowing the caller to handle concurrency limits.
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict

from tensortours.services.aws_poly import AWSPollyClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for generating audio using AWS Polly and storing it in S3.

    This handler is designed to be triggered directly with an invoke call.
    It processes the input text and Polly configuration to generate audio and store it in S3.
    Exceptions are raised and should be handled by the caller.

    Args:
        event (Dict[str, Any]): Lambda event containing:
            - text (str): The text to synthesize
            - voice_id (str, optional): The voice ID to use (default from client)
            - engine (str, optional): The engine type to use (default from client)
            - output_format (str, optional): The audio format (default: "mp3")
            - sample_rate (str, optional): The sample rate (default: "22050")
            - bucket (str, optional): S3 bucket to store the audio (default: from env var AUDIO_BUCKET)
            - key (str, optional): S3 key for the audio file (default: auto-generated)
            - metadata (Dict, optional): Additional metadata to attach to the S3 object
        context (Any): Lambda context object

    Returns:
        Dict[str, Any]: Response containing:
            - s3_uri (str): The S3 URI of the uploaded audio file (s3://bucket/key)
            - content_type (str): MIME type of the audio

    Raises:
        ValueError: If required parameters are missing or invalid
        ClientError: If AWS service errors occur, including throttling and concurrency limits
        Exception: For unexpected errors
    """
    # Log the request
    request_id = (
        context.aws_request_id if context and hasattr(context, "aws_request_id") else "unknown"
    )
    logger.info(f"Processing Polly audio generation request: {request_id}")

    # Extract parameters from the event
    text = event.get("text")
    if not text:
        raise ValueError("Missing required parameter: text")

    # Extract optional parameters
    voice_id = event.get("voice_id")
    engine = event.get("engine")
    output_format = event.get("output_format", "mp3")
    sample_rate = event.get("sample_rate", "22050")

    # Get S3 bucket and key parameters
    bucket = event.get("bucket", os.environ.get("AUDIO_BUCKET"))
    if not bucket:
        raise ValueError(
            "Missing required parameter: bucket (either in event or as AUDIO_BUCKET env var)"
        )

    # Generate a unique key if not provided
    key = event.get("key")
    if not key:
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        key = f"audio/{timestamp}-{unique_id}.{output_format}"

    # Get optional metadata
    metadata = event.get("metadata", {})

    # Add request_id to metadata
    if metadata is None:
        metadata = {}
    metadata["request_id"] = request_id

    # Initialize the Polly client
    # If voice_id or engine are provided in the event, they'll override the defaults
    client_voice_id = voice_id if voice_id else "Amy"
    client_engine = engine if engine else "generative"

    polly_client = AWSPollyClient(voice_id=client_voice_id, engine=client_engine)

    # Generate the audio and write directly to S3
    result = polly_client.synthesize_speech_to_s3(
        text=text,
        bucket=bucket,
        key=key,
        output_format=output_format,
        sample_rate=sample_rate,
        voice_id=voice_id,  # This will be None if not provided in the event
        engine=engine,  # This will be None if not provided in the event
        metadata=metadata,
    )

    logger.info(
        f"Successfully generated audio for request: {request_id}, " f"s3_uri: {result['s3_uri']}"
    )

    return result
