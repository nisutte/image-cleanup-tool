"""
API client implementations for various AI services.

This module provides concrete implementations of API clients for different AI services,
all inheriting from the base APIClient class for unified interface.
"""

import os
import base64
import json
from typing import Optional, Tuple, Dict

import anthropic
from openai import OpenAI
import google.generativeai as genai

from ..utils.log_utils import get_logger
from .backbone import APIClient
from .prompt import PROMPT_TEMPLATE

logger = get_logger(__name__)

SCHEMA_DATA = json.load(open(os.path.join(os.path.dirname(__file__), 'json_structure.json')))


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
        """Make API call to Claude with structured output."""
        try:
            json_schema = SCHEMA_DATA["schema"]

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
                ],
                tools=[
                    {
                        "name": "image_classification",
                        "input_schema": json_schema
                    }
                ],
                tool_choice={"type": "tool", "name": "image_classification"}
            )

            # Extract the tool call result
            tool_call = response.content[0]
            if tool_call.type == "tool_use":
                result_json = json.dumps(tool_call.input)
            else:
                # Fallback to text response if tool call fails
                result_json = response.content[0].text

            # Extract token usage
            usage = response.usage
            token_usage = {
                'input_tokens': usage.input_tokens,
                'output_tokens': usage.output_tokens,
                'total_tokens': usage.input_tokens + usage.output_tokens
            }

            return result_json, token_usage
        except Exception as err:
            logger.error("Claude API request failed: %s", err)
            raise RuntimeError(f"Claude API error: {err}")


class OpenAIClient(APIClient):
    """
    Client for OpenAI's GPT API.
    Estimated cost is around $0.85 per 10'000 images.
    """

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
        """Make API call to OpenAI with structured output."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                reasoning_effort="minimal",  # ↓ Reduce hidden reasoning tokens
                messages=[
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "text",
                                "text": PROMPT_TEMPLATE.split(".")[0]
                            }
                        ]
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": PROMPT_TEMPLATE.split(".")[1]
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}",
                                    "detail": "low"
                                }
                            }
                        ]
                    }
                ],
                # Use model-specific token parameter (chat.completions + this model expects max_completion_tokens)
                max_completion_tokens=256,
                response_format={
                    "type": "json_schema",
                    "json_schema": SCHEMA_DATA
                }
            )

            # Extract token usage
            usage = response.usage
            token_usage = {
                'input_tokens': getattr(usage, 'prompt_tokens', None),
                'output_tokens': getattr(usage, 'completion_tokens', None),
                'total_tokens': getattr(usage, 'total_tokens', None)
            }

            # When using JSON Schema mode, content may be empty and the parsed JSON is in `.parsed`
            message = response.choices[0].message

            return message.content, token_usage
        except Exception as err:
            logger.error("OpenAI API request failed: %s", err)
            raise RuntimeError(f"OpenAI API error: {err}")


class GeminiClient(APIClient):
    """
    Client for Google's Gemini API.
    Estimaged cost is around $0.525 per 10'000 images. (half for the 8 bit model)
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-1.5-flash-8b"):
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

    def _call_api(self, image_b64: str) -> Tuple[str, Dict[str, int]]:
        """Make API call to Gemini with structured output."""
        try:
            json_schema = SCHEMA_DATA["schema"]

            # Gemini doesn't support certain JSON schema fields, so remove them
            def remove_unsupported_fields(obj):
                if isinstance(obj, dict):
                    # Fields that Gemini doesn't support
                    unsupported_fields = {
                        'additionalProperties', 'minimum', 'maximum', 'exclusiveMinimum',
                        'exclusiveMaximum', 'multipleOf', 'minLength', 'maxLength',
                        'pattern', 'format', 'minItems', 'maxItems', 'uniqueItems',
                        'minProperties', 'maxProperties', 'enum', 'const', 'allOf',
                        'anyOf', 'oneOf', 'not', 'if', 'then', 'else', 'dependentSchemas',
                        'dependentRequired', 'propertyNames', 'contains', 'items'
                    }

                    # Remove unsupported fields from current level
                    obj = {k: v for k, v in obj.items() if k not in unsupported_fields}
                    # Recursively process nested objects
                    for k, v in obj.items():
                        if isinstance(v, (dict, list)):
                            obj[k] = remove_unsupported_fields(v)
                elif isinstance(obj, list):
                    # Process list items
                    obj = [remove_unsupported_fields(item) for item in obj]
                return obj

            json_schema = remove_unsupported_fields(json_schema)

            model = genai.GenerativeModel(
                self.model,
                generation_config={
                    "temperature": 0.1,
                    "top_p": 0.9,
                    "candidate_count": 1,
                    "max_output_tokens": 256,
                    "response_mime_type": "application/json",
                    "response_schema": json_schema,
                }
            )
            response = model.generate_content([
                PROMPT_TEMPLATE,
                {
                    "mime_type": "image/jpeg",
                    "data": base64.b64decode(image_b64)
                }
            ])

            # Response is already structured JSON due to response_schema
            response_text = response.text.strip()

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
        return OpenAIClient(rpm=2000, max_concurrent=100, **kwargs)
    elif api_name == "gemini":
        return GeminiClient(rpm=2000, max_concurrent=100, **kwargs)
    else:
        raise ValueError(f"Unsupported API: {api_name}")
