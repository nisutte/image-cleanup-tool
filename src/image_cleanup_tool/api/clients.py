"""
API client implementations for various AI services.

This module provides concrete implementations of API clients for different AI services,
all inheriting from the base APIClient class for unified interface.
"""

import os
import base64
from typing import Optional, Tuple, Dict

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

    def _call_api(self, image_b64: str) -> Tuple[str, Dict[str, int]]:
        """Make API call to Claude."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=256,
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

            # Extract token usage
            usage = response.usage
            token_usage = {
                'input_tokens': usage.input_tokens,
                'output_tokens': usage.output_tokens,
                'total_tokens': usage.input_tokens + usage.output_tokens
            }

            return response.content[0].text, token_usage
        except Exception as err:
            logger.error("Claude API request failed: %s", err)
            raise RuntimeError(f"Claude API error: {err}")


class OpenAIClient(APIClient):
    """Client for OpenAI's GPT API."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-5-nano"):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key. If None, uses OPENAI_API_KEY env var.
            model: Model name to use (default: gpt-5-nano)
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

    def _call_api(self, image_b64: str) -> Tuple[str, Dict[str, int]]:
        """Make API call to OpenAI."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                reasoning_effort="minimal",  # ↓ Reduce hidden reasoning tokens
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
                max_completion_tokens=256,
            )

            # Extract token usage
            usage = response.usage
            token_usage = {
                'input_tokens': usage.prompt_tokens,
                'output_tokens': usage.completion_tokens,
                'total_tokens': usage.total_tokens
            }

            return response.choices[0].message.content, token_usage
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
        key = self.api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        self.api_key = key
        genai.configure(api_key=key)

    def _get_model_name(self) -> str:
        """Return Gemini model name."""
        return self.model

    def _call_api(self, image_b64: str) -> Tuple[str, Dict[str, int]]:
        """Make API call to Gemini."""
        try:
            model = genai.GenerativeModel(
                self.model,
                generation_config={
                    "temperature": 0.0,
                    "top_p": 0.1,
                    "top_k": 1,
                    "candidate_count": 1,
                    "max_output_tokens": 256,
                    "response_mime_type": "application/json",
                }
            )
            response = model.generate_content([
                PROMPT_TEMPLATE,
                {
                    "mime_type": "image/jpeg",
                    "data": base64.b64decode(image_b64)
                }
            ])

            # Clean up Gemini's markdown-formatted response
            response_text = response.text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith('```json'):
                response_text = response_text[7:]  # Remove ```json
            elif response_text.startswith('```'):
                response_text = response_text[3:]  # Remove ```

            if response_text.endswith('```'):
                response_text = response_text[:-3]  # Remove ```

            response_text = response_text.strip()

            # Gemini doesn't provide token usage, so we'll estimate based on text length
            # Rough estimation: ~4 characters per token for English text
            input_tokens = len(PROMPT_TEMPLATE) // 4
            output_tokens = len(response_text) // 4

            token_usage = {
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': input_tokens + output_tokens
            }

            return response_text, token_usage
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
