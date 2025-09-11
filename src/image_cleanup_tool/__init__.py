"""
Image Cleanup Tool

A tool for scanning and analyzing personal photos using AI.
"""

__version__ = "0.1.0"
__author__ = "Nico Sutter"

# Allow loading slightly truncated/corrupt images across the package
try:
    from PIL import ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True
except Exception:
    pass

from .core.scan_engine import ImageScanEngine
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


def main():
    """Entry point for the image-cleanup command."""
    import sys
    from pathlib import Path
    
    # Add scripts directory to path
    scripts_dir = Path(__file__).parent.parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    
    # Import and run main
    from main import main as cli_main
    cli_main()


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