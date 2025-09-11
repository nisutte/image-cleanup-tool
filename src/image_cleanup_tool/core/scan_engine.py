#!/usr/bin/env python3
"""
scan_engine.py: Core scanning and analysis logic for image-cleanup-tool.

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
        self.on_cache_progress: Optional[Callable[[int], None]] = None
        self.on_cache_complete: Optional[Callable[[int], None]] = None
        self.on_cache_check_progress: Optional[Callable[[int], None]] = None
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
            if (i % 10 == 0 or i == len(self.image_paths) - 1):
                if self.on_cache_progress:
                    self.on_cache_progress(known)
                if self.on_cache_check_progress:
                    self.on_cache_check_progress(i + 1)
        if self.on_cache_complete:
            self.on_cache_complete(known)


    async def _process_single(self, pool, path: Path, api_provider: str, size: int, total: int):
        try:
            result = await pool._analyze_single_image(path)
        except Exception as e:
            result = e

        if not isinstance(result, Exception):
            try:
                self.cache.set(path, result, api_provider, size)
            except Exception as e:
                logger.error("Cache set failed for %s: %s", path, e)

        # Progress update
        if self.on_cache_progress:
            cached_count = sum(
                1 for p in self.image_paths
                if self.cache.get(p, api_provider, size) is not None
            )
            self.on_cache_progress(cached_count)

        if self.on_analysis_progress:
            done = sum(
                1 for p in self.uncached_images
                if self.cache.get(p, api_provider, size) is not None
            )
            self.on_analysis_progress(path, done, total, result)


    async def run_analysis_async(self, size: int = 512, api_providers: list[str] = None) -> None:
        if api_providers is None:
            api_providers = ["gemini"]

        if not self.uncached_images:
            if self.on_analysis_complete:
                self.on_analysis_complete()
            return

        for api_provider in api_providers:
            self._processed_paths.clear()
            try:
                pool = AsyncWorkerPool(self.uncached_images, api_provider, size)
            except Exception as e:
                logger.error("Failed to create AsyncWorkerPool: %s", e)
                continue

            total = len(self.uncached_images)

            async with asyncio.TaskGroup() as tg:
                for path in self.uncached_images:
                    tg.create_task(self._process_single(pool, path, api_provider, size, total))
                    # no need to keep dicts, TaskGroup auto tracks
