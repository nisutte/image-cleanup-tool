"""
Base functionality for image processing and analysis.

This module provides the core functionality for loading, encoding, and analyzing images
using various AI APIs through a unified interface.
"""

import json
from typing import Dict, Any, Optional, Tuple
from abc import ABC, abstractmethod

from ..utils.log_utils import get_logger
from ..core.image_encoder import crop_and_resize_to_b64

logger = get_logger(__name__)


class APIClient(ABC):
    """Abstract base class for API clients."""

    def __init__(self, api_key: Optional[str] = None, max_concurrent: int = 10, rpm: int = 60):
        """Initialize the API client.

        Args:
            api_key: API key for the service. If None, will try to get from environment.
            max_concurrent: Maximum number of concurrent requests.
            rpm: Requests per minute.
        """
        self.api_key = api_key
        self._validate_api_key()
        self.max_concurrent = max_concurrent
        self.rpm = rpm

    @abstractmethod
    def _validate_api_key(self) -> None:
        """Validate that the API key is available and properly configured."""
        pass

    @abstractmethod
    def _get_model_name(self) -> str:
        """Return the model name to use for this API."""
        pass

    @abstractmethod
    def _call_api(self, image_b64: str) -> Tuple[str, Dict[str, int]]:
        """Make the actual API call and return the response text and token usage.

        Args:
            image_b64: Base64-encoded image data

        Returns:
            Tuple of (response_text, token_usage_dict)
            token_usage_dict should contain keys like 'input_tokens', 'output_tokens', 'total_tokens'
        """
        pass

    def analyze_image(self, image_b64: str) -> Tuple[Dict[str, Any], Dict[str, int]]:
        """Analyze an image using this API client.

        Args:
            image_b64: Base64-encoded image data

        Returns:
            Tuple of (parsed_json_response, token_usage_dict)
            token_usage_dict contains keys like 'input_tokens', 'output_tokens', 'total_tokens'

        Raises:
            RuntimeError: If API call fails
            ValueError: If response cannot be parsed as JSON
        """
        try:
            response_text, token_usage = self._call_api(image_b64)
            if isinstance(response_text, str):
                parsed_response = json.loads(response_text)
            else:
                parsed_response = response_text
            return parsed_response, token_usage
        except json.JSONDecodeError:
            logger.error("Failed to parse JSON response: %s", response_text)
            raise ValueError(f"Invalid JSON response: {response_text}")
        except Exception as err:
            # Map API errors to a standardized 'unsure' result so it can be cached
            message = str(err)
            fallback = {
                "decision": "unsure",
                "confidence_keep": 0.0,
                "confidence_unsure": 1.0,
                "confidence_delete": 0.0,
                "primary_category": "error",
                "reason": (message[:100] if isinstance(message, str) else "API error")
            }
            logger.warning("API error mapped to unsure/error result: %s", message)
            return fallback, {}


class ImageProcessor:
    """Handles image loading and encoding operations."""

    @staticmethod
    def load_and_encode_image(path: str, size: int = 512) -> str:
        """Load an image, crop and resize it, and return base64-encoded data.

        Args:
            path: Path to the image file
            size: Target size for the square crop (default: 512)

        Returns:
            Base64-encoded JPEG image data
        """
        encoded = crop_and_resize_to_b64(path, [size])
        return encoded.get(str(size), "")

    @staticmethod
    def process_image_with_api(image_path: str, api_client: APIClient, size: int = 512) -> Tuple[Dict[str, Any], Dict[str, int]]:
        """Complete pipeline: load image, encode it, and analyze with API.

        Args:
            image_path: Path to the image file
            api_client: Configured API client instance
            size: Target size for the square crop (default: 512)

        Returns:
            Tuple of (analysis_result, token_usage_dict)
        """
        logger.debug("Processing image: %s", image_path)
        image_b64 = ImageProcessor.load_and_encode_image(image_path, size)
        return api_client.analyze_image(image_b64)
