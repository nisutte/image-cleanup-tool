"""
Backbone functionality for image processing and analysis.

This module provides the core functionality for loading, encoding, and analyzing images
using various AI APIs through a unified interface.
"""

import json
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod

from ..utils.log_utils import get_logger
from ..core.image_encoder import crop_and_resize_to_b64

logger = get_logger(__name__)


class APIClient(ABC):
    """Abstract base class for API clients."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the API client.

        Args:
            api_key: API key for the service. If None, will try to get from environment.
        """
        self.api_key = api_key
        self._validate_api_key()

    @abstractmethod
    def _validate_api_key(self) -> None:
        """Validate that the API key is available and properly configured."""
        pass

    @abstractmethod
    def _get_model_name(self) -> str:
        """Return the model name to use for this API."""
        pass

    @abstractmethod
    def _call_api(self, image_b64: str) -> str:
        """Make the actual API call and return the response text.

        Args:
            image_b64: Base64-encoded image data

        Returns:
            Raw response text from the API
        """
        pass

    def analyze_image(self, image_b64: str) -> Dict[str, Any]:
        """Analyze an image using this API client.

        Args:
            image_b64: Base64-encoded image data

        Returns:
            Parsed JSON response from the API

        Raises:
            RuntimeError: If API call fails
            ValueError: If response cannot be parsed as JSON
        """
        try:
            response_text = self._call_api(image_b64)
            return json.loads(response_text)
        except json.JSONDecodeError:
            logger.error("Failed to parse JSON response: %s", response_text)
            raise ValueError(f"Invalid JSON response: {response_text}")


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
    def process_image_with_api(image_path: str, api_client: APIClient, size: int = 512) -> Dict[str, Any]:
        """Complete pipeline: load image, encode it, and analyze with API.

        Args:
            image_path: Path to the image file
            api_client: Configured API client instance
            size: Target size for the square crop (default: 512)

        Returns:
            Analysis result from the API
        """
        logger.debug("Processing image: %s", image_path)
        image_b64 = ImageProcessor.load_and_encode_image(image_path, size)
        return api_client.analyze_image(image_b64)
