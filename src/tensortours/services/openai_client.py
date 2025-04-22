"""OpenAI client service for TensorTours backend."""

import logging
import os
from typing import List, Optional

import requests
from pydantic import BaseModel

from ..utils.aws import get_api_key_from_secret

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Environment variables
OPENAI_API_KEY_SECRET_NAME = os.environ.get("OPENAI_API_KEY_SECRET_NAME")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


class ChatMessage(BaseModel):
    """OpenAI Chat Message model."""

    role: str
    content: str


class OpenAIClient:
    """Client for interacting with OpenAI API."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the OpenAI client.

        Args:
            api_key: Optional API key. If not provided, will be retrieved from AWS Secrets Manager.
        """
        self.api_key = api_key or self._get_api_key()
        self.api_url = OPENAI_API_URL

    def _get_api_key(self) -> str:
        """Get OpenAI API key from AWS Secrets Manager."""
        if not OPENAI_API_KEY_SECRET_NAME:
            raise ValueError("OPENAI_API_KEY_SECRET_NAME environment variable not set")

        api_key = get_api_key_from_secret(OPENAI_API_KEY_SECRET_NAME, "OPENAI_API_KEY")
        if api_key is None:
            raise ValueError(
                f"Failed to retrieve OpenAI API key from secret {OPENAI_API_KEY_SECRET_NAME}"
            )
        return api_key

    def generate_completion(
        self,
        messages: List[ChatMessage],
        model: str = "gpt-4",
        temperature: float = 0.7,
        max_tokens: int = 800,
        top_p: float = 1.0,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
    ) -> str:
        """Generate a completion using OpenAI's chat API.

        Args:
            messages: List of messages to send to the API
            model: Model to use for completion
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum number of tokens to generate
            top_p: Nucleus sampling parameter
            frequency_penalty: Frequency penalty parameter
            presence_penalty: Presence penalty parameter

        Returns:
            Generated text from the API

        Raises:
            Exception: If the API request fails
        """
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}

        # Convert pydantic models to dictionaries
        message_dicts = [msg.model_dump() for msg in messages]

        payload = {
            "model": model,
            "messages": message_dicts,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
        }

        logger.info(f"Sending request to OpenAI API with model {model}")

        response = requests.post(
            self.api_url,
            headers=headers,
            json=payload,
        )

        if response.status_code != 200:
            error_message = f"OpenAI API error: {response.status_code} {response.text}"
            logger.error(error_message)
            raise Exception(error_message)

        # Extract the response
        response_data = response.json()
        generated_text: str = response_data["choices"][0]["message"]["content"].strip()

        logger.info(f"Successfully generated completion with {len(generated_text)} characters")

        return generated_text
