"""
API client implementations for various AI services.

This module provides concrete implementations of API clients for different AI services,
all inheriting from the base APIClient class for unified interface.
"""

import os
import base64
from typing import Optional

import anthropic
from openai import OpenAI
import google.generativeai as genai

from ..utils.log_utils import get_logger
from .backbone import APIClient
from .prompt import PROMPT_TEMPLATE

logger = get_logger(__name__)


class ClaudeClient(APIClient):
    """Client for Anthropic's Claude API."""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-haiku-20240307"):
        """Initialize Claude client.

        Args:
            api_key: Anthropic API key. If None, uses ANTHROPIC_API_KEY env var.
            model: Model name to use (default: claude-3-haiku-20240307)
        """
        self.model = model
        super().__init__(api_key)

    def _validate_api_key(self) -> None:
        """Validate Anthropic API key."""
        key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        self.api_key = key
        self.client = anthropic.Anthropic(api_key=key)

    def _get_model_name(self) -> str:
        """Return Claude model name."""
        return self.model

    def _call_api(self, image_b64: str) -> str:
        """Make API call to Claude."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=400,
                temperature=0.1,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": PROMPT_TEMPLATE
                            },
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_b64
                                }
                            }
                        ]
                    }
                ]
            )
            return response.content[0].text
        except Exception as err:
            logger.error("Claude API request failed: %s", err)
            raise RuntimeError(f"Claude API error: {err}")


class OpenAIClient(APIClient):
    """Client for OpenAI's GPT API."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key. If None, uses OPENAI_API_KEY env var.
            model: Model name to use (default: gpt-4o-mini)
        """
        self.model = model
        super().__init__(api_key)

    def _validate_api_key(self) -> None:
        """Validate OpenAI API key."""
        key = self.api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        self.api_key = key
        self.client = OpenAI(api_key=key)

    def _get_model_name(self) -> str:
        """Return OpenAI model name."""
        return self.model

    def _call_api(self, image_b64: str) -> str:
        """Make API call to OpenAI."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": PROMPT_TEMPLATE
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}",
                                    "detail": "low"
                                }
                            }
                        ],
                    }
                ],
                max_tokens=2000,
            )
            return response.choices[0].message.content
        except Exception as err:
            logger.error("OpenAI API request failed: %s", err)
            raise RuntimeError(f"OpenAI API error: {err}")


class GeminiClient(APIClient):
    """Client for Google's Gemini API."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-1.5-flash"):
        """Initialize Gemini client.

        Args:
            api_key: Google API key. If None, uses GOOGLE_API_KEY env var.
            model: Model name to use (default: gemini-1.5-flash)
        """
        self.model = model
        super().__init__(api_key)

    def _validate_api_key(self) -> None:
        """Validate Google API key."""
        key = self.api_key or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")
        self.api_key = key
        genai.configure(api_key=key)

    def _get_model_name(self) -> str:
        """Return Gemini model name."""
        return self.model

    def _call_api(self, image_b64: str) -> str:
        """Make API call to Gemini."""
        try:
            model = genai.GenerativeModel(self.model)

            response = model.generate_content([
                PROMPT_TEMPLATE,
                {
                    "mime_type": "image/jpeg",
                    "data": base64.b64decode(image_b64)
                }
            ])

            return response.text
        except Exception as err:
            logger.error("Gemini API request failed: %s", err)
            raise RuntimeError(f"Gemini API error: {err}")


def get_client(api_name: str, **kwargs) -> APIClient:
    """Factory function to create API client instances.

    Args:
        api_name: Name of the API ('claude', 'openai', 'gemini')
        **kwargs: Additional arguments passed to the client constructor

    Returns:
        Configured API client instance

    """
    api_name = api_name.lower()
    if api_name == "claude":
        return ClaudeClient(**kwargs)
    elif api_name == "openai":
        return OpenAIClient(**kwargs)
    elif api_name == "gemini":
        return GeminiClient(**kwargs)
    else:
        raise ValueError(f"Unsupported API: {api_name}")
