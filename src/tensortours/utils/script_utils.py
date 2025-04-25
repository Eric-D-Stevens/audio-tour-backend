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
    # Base system prompt
    base_system_prompt = """
    You are an expert tour guide creating an audio script for a specialized tour.
    Write an engaging, informative, and factual script about this specific site IN ENGLISH ONLY.
    
    Content Length Guidelines:
    - TARGET LENGTH: Aim for a 1-2 minute script (approximately 150-300 words) for most sites
    - FLEXIBILITY: For less significant locations with limited relevant information, it's acceptable to be briefer
    - QUALITY OVER QUANTITY: Never force content or pad the script - only include relevant, high-quality information
    - MAXIMUM LENGTH: Never exceed 5500 characters total
    
    Content Focus Guidelines:
    - ASSUME THE LISTENER IS ALREADY AT THE SITE and knows where they are
    - DO NOT provide general background about the surrounding location unless directly relevant to this site
    - FOCUS EXCLUSIVELY on aspects relevant to the specific tour type
    - Use a conversational, engaging tone as if speaking directly to the listener
    - Go directly into the details about the site without a general introduction about the broader area
    - End with a suggestion of what specifically to observe or experience at this exact location
    
    Everything you return will be read out loud, so don't include any additional formatting.
    
    IMPORTANT: ALWAYS WRITE THE SCRIPT IN ENGLISH regardless of the location's country or region.
    IMPORTANT: ALWAYS WRITE THE SCRIPT IN SPOKEN ENGLISH so that a text-to-speech engine can read it aloud.
    IMPORTANT: Prioritize quality information over length - it's better to be concise and relevant than lengthy and generic.
    """
    
    # Tour type-specific prompts
    tour_type_prompts = {
        TourType.HISTORY: """
        HISTORY TOUR FOCUS:
        - Focus on historical events, time periods, and significant people associated with this specific site
        - Emphasize key dates, historical context, and how this site has evolved over time
        - Include how this site specifically contributed to or was affected by important historical movements or events
        - Discuss any historical figures directly connected to this site and their specific actions here
        - Mention primary sources or evidence that reveal the site's historical significance
        - DO NOT extensively discuss the artistic or architectural elements unless they have specific historical significance
        - DO NOT provide general cultural significance unless it directly relates to a historical narrative
        - Favor historical accuracy and significance over general interest or cultural context
        """,
        
        TourType.ART: """
        ART TOUR FOCUS:
        - Focus on artistic elements, creators, and artistic significance of this specific site
        - Discuss specific art pieces, styles, techniques, and artistic movements represented at this site
        - Analyze visual elements, composition, color, and the artistic intent behind the work at this site
        - Mention artists or creators directly connected to this site and their specific contribution
        - Point out distinguishing artistic features visitors should look for at this exact location
        - Include relevant art historical context only as it pertains to the specific works at this site
        - DO NOT extensively discuss general history unless it directly influenced the artistic elements
        - DO NOT focus on architectural features unless they have specific artistic significance
        - Favor artistic analysis and appreciation over general historical or cultural context
        """,
        
        TourType.CULTURE: """
        CULTURE TOUR FOCUS:
        - Focus on cultural traditions, practices, and significance of this specific site
        - Discuss the site's role in local customs, rituals, or cultural identity
        - Explain cultural symbolism, meaning, and values represented at this site
        - Include information about how communities interact with or use this specific site
        - Mention cultural festivals, celebrations, or events that take place specifically at this site
        - Discuss the site's influence on literature, music, film, or other cultural expressions
        - DO NOT extensively discuss general history unless it directly shaped cultural practices
        - DO NOT focus on architectural features unless they have specific cultural significance
        - Favor cultural meaning and significance over general historical facts or artistic elements
        """,
        
        TourType.ARCHITECTURE: """
        ARCHITECTURE TOUR FOCUS:
        - Focus on architectural style, design elements, and structural significance of this specific site
        - Discuss building materials, construction techniques, and engineering innovations at this site
        - Explain architectural periods, influences, and the evolution of the structure if applicable
        - Include information about architects, designers, or builders directly involved with this site
        - Point out specific architectural features visitors should look for at this exact location
        - Mention any restorations, modifications, or preservation efforts specific to this structure
        - DO NOT extensively discuss general history unless it directly relates to the architectural design
        - DO NOT focus on cultural context unless it specifically influenced the architectural elements
        - Favor architectural analysis and significance over general historical or cultural context
        """,
        
        TourType.NATURE: """
        NATURE TOUR FOCUS:
        - Focus on natural elements, ecosystems, and environmental significance of this specific site
        - Discuss flora, fauna, geology, and natural processes observable at this exact location
        - Explain the ecological importance of this site and its relationship to the broader environment
        - Include information about conservation efforts, environmental challenges, or changes over time
        - Point out specific natural features or phenomena visitors should look for at this location
        - Consider seasonal aspects of the natural environment at this site if relevant
        - DO NOT extensively discuss human history unless it directly relates to the natural environment
        - DO NOT focus on cultural elements unless they have specific connection to the natural features
        - Favor ecological significance and natural history over general historical or cultural context
        """
    }
    
    # Create system prompt by combining base prompt and tour-specific content
    # This concatenates: 1) base prompt + 2) tour-specific prompt + 3) final instruction
    tour_specific_content = tour_type_prompts.get(tour_type, '')
    system_prompt = f"""{base_system_prompt}
    
    # Tour-specific guidelines for {tour_type.value} tours:
    {tour_specific_content}
    
    You are creating a {tour_type.value} tour script specifically.
    """

    # Create user prompt with specific instructions
    user_prompt = f"""
    Create a {tour_type.value.upper()} TOUR audio script for: {place_info.place_name}
    Location details: {place_info.place_address}
    Category: {', '.join(place_info.place_types)}
    Additional information: {place_info.place_editorial_summary}

    IMPORTANT REMINDERS:
    1. This is SPECIFICALLY for a {tour_type.value.upper()} tour - do not deviate into other tour types
    2. Assume the listener is already at the site and knows their general location
    3. Focus immediately on the {tour_type.value.lower()}-specific aspects of this site
    4. Do not provide general background about the surrounding area
    5. Be specific and detailed about {tour_type.value.lower()}-related features at this exact location
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
            max_tokens=6000, # poly limit
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

    # Define S3 key for the script using the new hierarchical structure
    script_key = f"{place_id}/script/script.txt"

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
