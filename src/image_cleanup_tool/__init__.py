"""
Image Cleanup Tool

A tool for scanning and analyzing personal photos using AI.
"""

__version__ = "0.1.0"
__author__ = "Nico Sutter"

from .core.backbone import ImageScanEngine
from .api import (
    APIClient,
    ImageProcessor,
    ClaudeClient,
    OpenAIClient,
    GeminiClient,
    get_client,
    load_and_encode_image,  # Legacy compatibility
    analyze_image_with_api   # Legacy compatibility
)
from .core.workers import AsyncWorkerPool, analyze_images_async

__all__ = [
    "ImageScanEngine",
    "APIClient",
    "ImageProcessor",
    "ClaudeClient",
    "OpenAIClient",
    "GeminiClient",
    "get_client",
    "load_and_encode_image",  # Legacy compatibility
    "analyze_image_with_api", # Legacy compatibility
    "AsyncWorkerPool",
    "analyze_images_async"
] 