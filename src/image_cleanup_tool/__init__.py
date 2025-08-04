"""
Image Cleanup Tool

A tool for scanning and analyzing personal photos using AI.
"""

__version__ = "0.1.0"
__author__ = "Nico Sutter"

from .core.backbone import ImageScanEngine
from .api.openai_api import analyze_image, load_and_encode_image

__all__ = ["ImageScanEngine", "analyze_image", "load_and_encode_image"] 