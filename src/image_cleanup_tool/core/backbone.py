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
    get_final_classification_color_ratio,
)


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

    def check_cache(self) -> None:
        """
        Check which images are already in the cache.
        Calls on_cache_progress after each image and on_cache_complete at end.
        """
        scanned = 0
        known = 0
        self.uncached_images = []
        for path in self.image_paths:
            if self.cache.get(path) is not None:
                known += 1
            else:
                self.uncached_images.append(path)
            scanned += 1
            if self.on_cache_progress:
                self.on_cache_progress(scanned, known)
        if self.on_cache_complete:
            self.on_cache_complete(known, len(self.image_paths))



    async def run_analysis_async(
        self, max_concurrent: int = 10, requests_per_minute: int = 60, size: int = 512
    ) -> None:
        """
        Analyze uncached images concurrently using AsyncWorkerPool.
        Calls on_analysis_progress for each result and on_analysis_complete at end.
        """
        if not self.uncached_images:
            if self.on_analysis_complete:
                self.on_analysis_complete()
            return

        pool = AsyncWorkerPool(
            image_paths=self.uncached_images,
            max_concurrent=max_concurrent,
            requests_per_minute=requests_per_minute,
            size=size,
        )
        
        # Run the analysis
        results = await pool.analyze_all()
        
        # Process results and call callbacks
        total = len(self.uncached_images)
        analyzed = 0
        
        for path, analysis_result in results.items():
            analyzed += 1
            
            # Cache successful results
            if not isinstance(analysis_result.result, Exception):
                self.cache.set(path, analysis_result.result)
            
            # Call progress callback
            if self.on_analysis_progress:
                self.on_analysis_progress(path, analyzed, total, analysis_result.result)
        
        # Call completion callback
        if self.on_analysis_complete:
            self.on_analysis_complete()