"""AWS Polly client for TensorTours backend."""

import logging
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError
from mypy_boto3_polly.client import PollyClient
from mypy_boto3_polly.type_defs import SynthesizeSpeechOutputTypeDef
from mypy_boto3_s3.client import S3Client

logger = logging.getLogger(__name__)


class AWSPollyClient:
    """Client for interacting with Amazon Polly text-to-speech service."""

    # Engine types supported by Amazon Polly
    ENGINE_STANDARD = "standard"
    ENGINE_NEURAL = "neural"
    ENGINE_GENERATIVE = "generative"

    def __init__(self, voice_id: str = "Joanna", engine: str = "neural"):
        """
        Initialize the AWS Polly client.

        Args:
            voice_id (str): The voice ID to use for synthesis (default: "Joanna")
            engine (str): The engine type to use - "standard", "neural", or "generative"
                          (default: "neural")
        """
        self.voice_id = voice_id
        self.engine = engine

        # Validate engine type
        if engine not in [self.ENGINE_STANDARD, self.ENGINE_NEURAL, self.ENGINE_GENERATIVE]:
            raise ValueError(
                f"Invalid engine type: {engine}. Must be one of: "
                f"{self.ENGINE_STANDARD}, {self.ENGINE_NEURAL}, or {self.ENGINE_GENERATIVE}"
            )

        # Initialize the Polly client
        self.client: PollyClient = boto3.client("polly")

        # Initialize the S3 client
        self.s3_client: S3Client = boto3.client("s3")

    def synthesize_speech(
        self,
        text: str,
        output_format: str = "mp3",
        sample_rate: str = "22050",
        voice_id: Optional[str] = None,
        engine: Optional[str] = None,
    ) -> Dict:
        """
        Synthesize speech from text using Amazon Polly.

        Args:
            text (str): The text to synthesize
            output_format (str): The format of the output audio - "mp3", "ogg_vorbis", or "pcm"
                                (default: "mp3")
            sample_rate (str): The sample rate of the audio - e.g., "8000", "16000", "22050"
                              (default: "22050")
            voice_id (str, optional): Override the default voice ID
            engine (str, optional): Override the default engine type

        Returns:
            dict: A dictionary containing:
                - "audio_content": The binary audio data
                - "content_type": The MIME type of the audio
                - "request_characters": Number of characters processed
        """
        # Use instance defaults if not specified
        voice_id = voice_id or self.voice_id
        engine = engine or self.engine

        # Set content type based on output format
        content_types = {"mp3": "audio/mpeg", "ogg_vorbis": "audio/ogg", "pcm": "audio/pcm"}
        content_type = content_types.get(output_format, "application/octet-stream")

        try:
            # Prepare the synthesis request
            params = {
                "Engine": engine,
                "OutputFormat": output_format,
                "SampleRate": sample_rate,
                "Text": text,
                "VoiceId": voice_id,
            }

            # Add TextType parameter for standard engine
            if engine == self.ENGINE_STANDARD:
                params["TextType"] = "text"

            # Make the API call
            # Use type ignore for the synthesize_speech call since we've already validated the parameters
            # but mypy is being strict about literal types
            response: SynthesizeSpeechOutputTypeDef = self.client.synthesize_speech(**params)  # type: ignore

            # Extract and return the audio content
            audio_content = response["AudioStream"].read() if "AudioStream" in response else None

            # Return a structured response
            return {
                "audio_content": audio_content,
                "content_type": content_type,
                "request_characters": len(text),
            }

        except ClientError as e:
            # Log the error and re-raise
            logger.exception(f"Error in Polly synthesis: {str(e)}")
            raise

    def list_available_voices(self, engine: Optional[str] = None) -> Dict:
        """
        List available voices for the specified engine.

        Args:
            engine (str, optional): Engine type to filter voices by
                                   If None, uses the client's default engine

        Returns:
            dict: Dictionary with voice information
        """
        engine = engine or self.engine

        try:
            # Use type ignore for the describe_voices call
            voices_result = None
            if engine in [self.ENGINE_STANDARD, self.ENGINE_NEURAL, self.ENGINE_GENERATIVE]:
                voices_result = self.client.describe_voices(Engine=engine)  # type: ignore
            else:
                voices_result = self.client.describe_voices()

            # Return a structured response
            return {"voices": voices_result.get("Voices", [])}

        except ClientError as e:
            logger.exception(f"Error listing Polly voices: {str(e)}")
            raise

    def synthesize_speech_to_s3(
        self,
        text: str,
        bucket: str,
        key: str,
        output_format: str = "mp3",
        sample_rate: str = "22050",
        voice_id: Optional[str] = None,
        engine: Optional[str] = None,
        content_type: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """
        Synthesize speech from text using Amazon Polly and write directly to an S3 bucket.

        Args:
            text (str): The text to synthesize
            bucket (str): The S3 bucket name
            key (str): The S3 object key (path within the bucket)
            output_format (str): The format of the output audio - "mp3", "ogg_vorbis", or "pcm"
                                (default: "mp3")
            sample_rate (str): The sample rate of the audio - e.g., "8000", "16000", "22050"
                              (default: "22050")
            voice_id (str, optional): Override the default voice ID
            engine (str, optional): Override the default engine type
            content_type (str, optional): Override the auto-detected content type
            metadata (Dict, optional): Additional metadata to attach to the S3 object

        Returns:
            dict: A dictionary containing:
                - "s3_uri": The S3 URI of the uploaded audio file (s3://bucket/key)
                - "content_type": The MIME type of the audio
        """
        # Use instance defaults if not specified
        voice_id = voice_id or self.voice_id
        engine = engine or self.engine

        # Set content type based on output format if not provided
        if not content_type:
            content_types = {"mp3": "audio/mpeg"}
            content_type = content_types.get(output_format, "application/octet-stream")

        try:
            # Prepare the synthesis request
            params = {
                "Engine": engine,
                "OutputFormat": output_format,
                "SampleRate": sample_rate,
                "Text": text,
                "VoiceId": voice_id,
            }

            # Add TextType parameter for standard engine
            if engine == self.ENGINE_STANDARD:
                params["TextType"] = "text"

            # Make the API call to get the audio stream
            response: SynthesizeSpeechOutputTypeDef = self.client.synthesize_speech(**params)  # type: ignore

            # Get the audio stream from the response
            audio_stream = response["AudioStream"]

            # Upload the audio stream directly to S3
            # Prepare the extra arguments for the upload
            extra_args: Dict[str, Any] = {"ContentType": content_type}
            if metadata:
                extra_args["Metadata"] = metadata

            # Upload the file using the S3 client
            self.s3_client.upload_fileobj(
                Fileobj=audio_stream, Bucket=bucket, Key=key, ExtraArgs=extra_args
            )

            # Return a structured response
            return {
                "s3_uri": f"s3://{bucket}/{key}",
                "content_type": content_type,
            }

        except ClientError as e:
            # Log the error and re-raise
            logger.exception(f"Error in Polly synthesis or S3 upload: {str(e)}")
            raise
