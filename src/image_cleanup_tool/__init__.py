"""
Image Cleanup Tool

A tool for scanning and analyzing personal photos using AI.
"""

__version__ = "0.1.0"
__author__ = "Nico Sutter"

from .core.backbone import ImageScanEngine
from .api.openai_api import analyze_image as openai_analyze_image, load_and_encode_image as openai_load_and_encode_image
from .api.claude_api import analyze_image as claude_analyze_image, load_and_encode_image as claude_load_and_encode_image
from .core.workers import AsyncWorkerPool, analyze_images_async

__all__ = [
    "ImageScanEngine", 
    "openai_analyze_image", 
    "openai_load_and_encode_image",
    "claude_analyze_image",
    "claude_load_and_encode_image",
    "AsyncWorkerPool",
    "analyze_images_async"
] 