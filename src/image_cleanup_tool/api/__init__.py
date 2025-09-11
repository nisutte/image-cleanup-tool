"""
API integrations for external services.

This module provides a unified interface for various AI APIs through client classes
and backbone functionality for image processing and analysis.
"""

from .base import APIClient, ImageProcessor
from .clients import ClaudeClient, OpenAIClient, GeminiClient, get_client
from .prompt import PROMPT_TEMPLATE

# Legacy function compatibility (deprecated - use client classes instead)
def load_and_encode_image(path: str, size: int = 512) -> str:
    """Load and encode an image (legacy function - use ImageProcessor instead)."""
    return ImageProcessor.load_and_encode_image(path, size)

def analyze_image_with_api(image_path: str, api_name: str, size: int = 512, **kwargs) -> dict:
    """Analyze image using specified API (legacy function - use client classes instead)."""
    client = get_client(api_name, **kwargs)
    result, _ = ImageProcessor.process_image_with_api(image_path, client, size)
    return result

__all__ = [
    # Main classes
    "APIClient",
    "ImageProcessor",
    "ClaudeClient",
    "OpenAIClient",
    "GeminiClient",
    "get_client",

    # Utilities
    "PROMPT_TEMPLATE",

    # Legacy functions (deprecated)
    "load_and_encode_image",
    "analyze_image_with_api"
] 