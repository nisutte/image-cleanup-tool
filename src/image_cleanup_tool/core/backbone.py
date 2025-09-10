#!/usr/bin/env python3
"""
backbone.py: Core scanning and analysis logic for image-cleanup-tool.

Provides ImageScanEngine that can scan a directory for images, count by extension,
device, and capture date, check a persistent analysis cache, and run analysis on uncached images.
Optional callbacks can be attached to monitor progress and completion of each stage.
"""

import time
from pathlib import Path
from collections import Counter
from typing import Callable, Dict, Any, Optional
import asyncio

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

from .image_cache import ImageCache
from .workers import AsyncWorkerPool
from ..utils.utils import (
    iter_files,
    IMAGE_EXTS,
    get_capture_datetime,
    get_device,
)
from ..utils.log_utils import get_logger

logger = get_logger(__name__)


class ImageScanEngine:
    """
    Core engine for scanning images, checking cache, and analyzing uncached images.
    Callbacks can be attached to monitor progress and completion events.
    """

    def __init__(self, root: Path):
        self.root = root
        self.ext_counter: Counter[str] = Counter()
        self.device_counter: Counter[str] = Counter()
        self.date_ext_counter: Dict[str, Counter[str]] = {}
        self.non_image_count: int = 0
        self.total_files: int = 0
        self.scanned_count: int = 0
        self.image_paths: list[Path] = []
        self.uncached_images: list[Path] = []
        self.cache = ImageCache()
        self.paused: bool = False
        self.on_scan_progress: Optional[
            Callable[[int, int, Counter, Counter, Dict[str, Counter], int], None]
        ] = None
        self.on_scan_complete: Optional[Callable[[], None]] = None
        self.on_cache_progress: Optional[Callable[[int, int], None]] = None
        self.on_cache_complete: Optional[Callable[[int, int], None]] = None
        # on_analysis_progress(path, analyzed_count, total_count, result)
        self.on_analysis_progress: Optional[Callable[[Path, int, int, Any], None]] = None
        self.on_analysis_complete: Optional[Callable[[], None]] = None
        self._processed_paths: set[Path] = set()

    def calculate_total(self) -> None:
        """Count total files under the root directory."""
        count = 0
        for _ in iter_files(self.root):
            count += 1
        self.total_files = count

    def scan_files(self) -> None:
        """
        Scan files under root, update counts and image path list.
        Calls on_scan_progress periodically and on_scan_complete at end.
        """
        for path in iter_files(self.root):
            ext = path.suffix.lower()
            if ext in IMAGE_EXTS:
                self.image_paths.append(path)
                self.ext_counter[ext] += 1
                dt = get_capture_datetime(path)
                year = str(dt.year)
                self.date_ext_counter.setdefault(year, Counter())[ext] += 1
                dev = get_device(path)
                self.device_counter[dev] += 1
            else:
                self.non_image_count += 1
            self.scanned_count += 1
            if self.on_scan_progress and self.scanned_count % 24 == 0:
                self.on_scan_progress(
                    self.scanned_count,
                    self.total_files,
                    self.ext_counter,
                    self.device_counter,
                    self.date_ext_counter,
                    self.non_image_count,
                )
        if self.on_scan_progress:
            self.on_scan_progress(
                self.scanned_count,
                self.total_files,
                self.ext_counter,
                self.device_counter,
                self.date_ext_counter,
                self.non_image_count,
            )
        if self.on_scan_complete:
            self.on_scan_complete()

    def check_cache(self, api_provider: str, size: int = 512) -> None:
        """
        Check which images are already in the cache.
        Calls on_cache_progress after each image and on_cache_complete at end.
        """
        known = 0
        self.uncached_images = []
        for i, path in enumerate(self.image_paths):
            if self.cache.get(path, api_provider, size) is not None:
                known += 1
            else:
                self.uncached_images.append(path)
            # Call progress callback periodically (every 10 images or at the end)
            if self.on_cache_progress and (i % 10 == 0 or i == len(self.image_paths) - 1):
                self.on_cache_progress(known)
        if self.on_cache_complete:
            self.on_cache_complete(known)


    async def run_analysis_async(
        self, size: int = 512,
        api_providers: list[str] = None,
        skip_cache_check: bool = False
    ) -> None:
        if api_providers is None:
            api_providers = ["gemini"]
        """
        Analyze uncached images concurrently using AsyncWorkerPool for multiple APIs.
        Calls on_analysis_progress for each result and on_analysis_complete at end.
        """
        if not self.uncached_images:
            if self.on_analysis_complete:
                self.on_analysis_complete()
            return

        # Process each API provider
        for api_provider in api_providers:
            # Reset processed paths for each API
            self._processed_paths = set()

            # Only check cache if not skipped (for UI usage where cache was already checked)
            if not skip_cache_check:
                self.check_cache(api_provider, size)

            if not self.uncached_images:
                continue

            try:
                pool = AsyncWorkerPool(
                    image_paths=self.uncached_images,
                    api_name=api_provider,
                    size=size
                )
            except Exception as e:
                logger.error(f"Failed to create AsyncWorkerPool: {e}")
                continue

            # Instead of waiting for all results, process them as they complete
            total = len(self.uncached_images)
            analyzed = 0

            # Create tasks for all images
            tasks = [asyncio.create_task(pool._analyze_single_image(path)) for path in self.uncached_images]
            
            # Wait for all tasks to complete and process results
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process all results from the pool
            for path, result_obj in pool.results.items():
                analyzed += 1
                result = result_obj.result

                # Cache successful results
                if not isinstance(result, Exception):
                    self.cache.set(path, result, api_provider, size)
                
                if isinstance(result, Exception):
                    logger.error(f"Failed to analyze {path.name}: {result}")
                    continue

                # Update cache progress since we just cached a new result
                if self.on_cache_progress:
                    cached_count = sum(1 for path in self.image_paths if self.cache.get(path, api_provider, size) is not None)
                    self.on_cache_progress(cached_count)

                # Call progress callback
                if self.on_analysis_progress:
                    self.on_analysis_progress(path, analyzed, total, result)

        # Call completion callback
        if self.on_analysis_complete:
            self.on_analysis_complete()