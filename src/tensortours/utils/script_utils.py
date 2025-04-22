"""Script generation utilities for TensorTours backend."""

import logging
import os
import uuid
from typing import Dict

from ..models.tour import TourType, TTPlaceInfo, TTScript
from ..services.openai_client import ChatMessage
from .aws import upload_to_s3
from .general_utils import get_openai_client

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Environment variables
CONTENT_BUCKET = os.environ.get("CONTENT_BUCKET")
CLOUDFRONT_DOMAIN = os.environ.get("CLOUDFRONT_DOMAIN")


def create_tour_script_prompt(place_info: TTPlaceInfo, tour_type: TourType) -> Dict[str, str]:
    """Create prompts for generating a tour script.

    Args:
        place_info: Place information
        tour_type: Type of tour

    Returns:
        Dictionary with system_prompt and user_prompt
    """
    system_prompt = f"""
    You are an expert tour guide creating an audio script for {tour_type.value} tours.
    Write an engaging, informative, and factual script about this place IN ENGLISH ONLY.
    The script should be 2-3 minutes when read aloud (approximately 300-400 words).
    Focus on the most interesting aspects relevant to a {tour_type.value} tour.
    Use a conversational, engaging tone as if speaking directly to the listener.
    Start with a brief introduction to the place and then share the most interesting facts or stories.
    End with a suggestion of what to observe or experience at the location.
    Everything you return will be read out loud, so don't include any additional formatting.
    IMPORTANT: ALWAYS WRITE THE SCRIPT IN ENGLISH regardless of the location's country or region.
    IMPORTANT: ALWAYS WRITE THE SCRIPT IN ENGLISH regardless of the language of the rest of this prompt.
    IMPORTANT: ALWAYS WRITE THE SCRIPT IN SPOKEN ENGLISH so that a text-to-speech engine can read it aloud.
    """

    user_prompt = f"""
    Create an audio tour script for: {place_info.place_name}
    Address: {place_info.place_address}
    Category: {', '.join(place_info.place_types)}
    Additional information: {place_info.place_editorial_summary}

    This is for a {tour_type.value} focused tour.
    Make sure the script is appropriate for a {tour_type.value} tour.
    """

    return {"system_prompt": system_prompt, "user_prompt": user_prompt}


def generate_tour_script(place_info: TTPlaceInfo, tour_type: TourType) -> str:
    """Generate a tour script using OpenAI.

    Args:
        place_info: Place information
        tour_type: Type of tour

    Returns:
        Generated script text

    Raises:
        Exception: If script generation fails
    """
    # Get the cached OpenAI client
    client = get_openai_client()

    # Create prompts
    prompts = create_tour_script_prompt(place_info, tour_type)

    # Create messages
    messages = [
        ChatMessage(role="system", content=prompts["system_prompt"]),
        ChatMessage(role="user", content=prompts["user_prompt"]),
    ]

    # Generate completion
    try:
        script_text = client.generate_completion(
            messages=messages,
            model="gpt-4o",
            temperature=0.7,
            max_tokens=10000,
        )
        return script_text
    except Exception as e:
        logger.error(f"Error generating script: {str(e)}")
        raise


def save_script_to_s3(
    script_text: str, place_id: str, place_name: str, tour_type: TourType
) -> TTScript:
    """Save a script to S3 and return a TTScript object.

    Args:
        script_text: Script text to save
        place_id: Place ID
        place_name: Place name
        tour_type: Tour type

    Returns:
        TTScript object with S3 and CloudFront URLs

    Raises:
        ValueError: If required environment variables are not set
    """
    # Generate a unique script ID
    script_id = str(uuid.uuid4())

    # Define S3 key for the script using the requested format
    script_key = f"scripts/{place_id}_{tour_type.value}_script.txt"

    # Check environment variables
    if not CONTENT_BUCKET:
        raise ValueError("CONTENT_BUCKET environment variable not set")

    if not CLOUDFRONT_DOMAIN:
        raise ValueError("CLOUDFRONT_DOMAIN environment variable not set")

    # Upload the script to S3
    upload_to_s3(
        bucket_name=CONTENT_BUCKET,
        key=script_key,
        data=script_text,
        content_type="text/plain",
    )

    # Create CloudFront and S3 URLs
    cloudfront_url = f"https://{CLOUDFRONT_DOMAIN}/{script_key}"
    s3_url = f"s3://{CONTENT_BUCKET}/{script_key}"

    # Create TTScript object
    script = TTScript(
        script_id=script_id,
        place_id=place_id,
        place_name=place_name,
        tour_type=tour_type,
        model_info={"model": "gpt-4", "version": "1.0"},
        s3_url=s3_url,
        cloudfront_url=cloudfront_url,
    )

    return script
