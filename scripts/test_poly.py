#!/usr/bin/env python
"""
Test script for AWS Polly client.
This script demonstrates how to use the AWSPollyClient to synthesize speech and save it to a file.
"""

import os
import sys
import logging
from pathlib import Path

# Add the project root to the Python path so we can import the tensortours package
sys.path.insert(0, str(Path(__file__).parent.parent))

from tensortours.services.aws_poly import AWSPollyClient

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Main function to test the AWS Polly client."""
    # Create output directory if it doesn't exist
    output_dir = Path("./output")
    output_dir.mkdir(exist_ok=True)

    # Sample text to synthesize
    sample_text = (
        "Welcome to your audio tour! Today, we'll be exploring some of the most "
        "fascinating historical landmarks in this area. As we walk through these "
        "streets, you'll hear stories about the people and events that shaped this "
        "place. Let's begin our journey through time."
    )

    # Test different engines and voices
    test_configurations = [
        {"engine": "neural", "voice_id": "Joanna", "file_name": "neural_joanna.mp3"},
        {"engine": "neural", "voice_id": "Matthew", "file_name": "neural_matthew.mp3"},
        {"engine": "standard", "voice_id": "Joanna", "file_name": "standard_joanna.mp3"},
    ]

    # Try to add generative engine if available (might not be available in all regions)
    try:
        test_configurations.append(
            {"engine": "generative", "voice_id": "Joanna", "file_name": "generative_joanna.mp3"}
        )
    except Exception as e:
        logger.warning(f"Skipping generative engine test: {e}")

    # Test each configuration
    for config in test_configurations:
        try:
            logger.info(f"Testing {config['engine']} engine with {config['voice_id']} voice")

            # Initialize the client with the specified engine and voice
            client = AWSPollyClient(voice_id=config["voice_id"], engine=config["engine"])

            # Synthesize speech
            result = client.synthesize_speech(
                text=sample_text, output_format="mp3", sample_rate="22050"
            )

            # Save the audio to a file
            output_path = output_dir / config["file_name"]
            with open(output_path, "wb") as f:
                f.write(result["audio_content"])

            logger.info(f"Successfully saved audio to {output_path}")
            logger.info(f"Content type: {result['content_type']}")
            logger.info(f"Characters processed: {result['request_characters']}")

        except Exception as e:
            logger.error(
                f"Error testing {config['engine']} engine with {config['voice_id']} voice: {e}"
            )

    # List available voices for neural engine
    try:
        logger.info("Listing available voices for neural engine")
        client = AWSPollyClient(engine="neural")
        voices = client.list_available_voices()

        logger.info(f"Found {len(voices['voices'])} voices for neural engine:")
        for i, voice in enumerate(voices["voices"][:5], 1):  # Show first 5 voices
            logger.info(
                f"  {i}. {voice.get('Id')} ({voice.get('LanguageCode')}) - {voice.get('Gender')}"
            )

        if len(voices["voices"]) > 5:
            logger.info(f"  ... and {len(voices['voices']) - 5} more voices")

    except Exception as e:
        logger.error(f"Error listing voices: {e}")


if __name__ == "__main__":
    main()
