"""
image_cache.py - persistent per-image analysis cache based on metadata fingerprint.

Provides utilities to compute a stable hash for an image using EXIF metadata
(creation timestamp, device make/model, lens model, dimensions, GPS) and cache
analysis results (including file path) in a JSON-backed dict to avoid
reprocessing images.

Example:
    cache = ImageCache()
    result = cache.get(path)
    if result is None:
        result = analyze_image(path)
        cache.set(path, result)
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any
import time

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass
from ..utils.log_utils import get_logger

logger = get_logger(__name__)

# Default cache file in working directory
DEFAULT_CACHE_FILE = Path('.image_analysis_cache.json')

# Current cache version - increment this when analysis logic changes
CACHE_VERSION = "1.0"

# Cache entry structure
class CacheEntry:
    """Structure for cache entries with metadata."""
    def __init__(self, path: str, result: str, version: str = CACHE_VERSION, 
                 timestamp: float = None, model: str = None):
        self.path = path
        self.result = result
        self.version = version
        self.timestamp = timestamp or time.time()
        self.model = model or "gpt-4.1-nano"  # Default model
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "result": self.result,
            "version": self.version,
            "timestamp": self.timestamp,
            "model": self.model
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CacheEntry':
        return cls(
            path=data.get("path", ""),
            result=data.get("result", ""),
            version=data.get("version", "0.0"),
            timestamp=data.get("timestamp", time.time()),
            model=data.get("model", "gpt-4.1-nano")
        )


def load_cache(cache_file: Path = DEFAULT_CACHE_FILE) -> Dict[str, Any]:
    """Load the cache from disk (JSON), or return empty dict on failure."""
    if cache_file.is_file():
        try:
            data = json.loads(cache_file.read_text(encoding='utf-8'))
            # Handle both new format (with metadata) and legacy format
            if isinstance(data, dict) and "version" in data:
                # New format with metadata
                return data
            else:
                # Legacy format - convert to new format
                logger.info("Converting legacy cache format to new format")
                converted = {"version": CACHE_VERSION, "entries": {}}
                for key, value in data.items():
                    if isinstance(value, dict) and "result" in value:
                        # Already in new format
                        converted["entries"][key] = value
                    else:
                        # Legacy format - wrap in new structure
                        converted["entries"][key] = CacheEntry(
                            path="",  # Legacy entries don't have path
                            result=value,
                            version="0.0"  # Legacy version
                        ).to_dict()
                return converted
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
    return {"version": CACHE_VERSION, "entries": {}}


def save_cache(cache: Dict[str, Any], cache_file: Path = DEFAULT_CACHE_FILE) -> None:
    """Persist the cache dict to disk as JSON."""
    cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding='utf-8')


def _convert_gps(info: dict) -> Tuple[Optional[float], Optional[float]]:
    """Convert EXIF GPSInfo dict to (latitude, longitude) in decimal degrees."""
    def _to_deg(value):
        # value may be ((num, den),...) or simple floats
        try:
            d, m, s = value
            if isinstance(d, tuple):
                d = d[0] / d[1]
            if isinstance(m, tuple):
                m = m[0] / m[1]
            if isinstance(s, tuple):
                s = s[0] / s[1]
            return d + (m / 60.0) + (s / 3600.0)
        except Exception:
            return None

    lat = lon = None
    try:
        gps_lat = info.get(2)
        gps_lat_ref = info.get(1)
        gps_lon = info.get(4)
        gps_lon_ref = info.get(3)
        if gps_lat and gps_lat_ref and gps_lon and gps_lon_ref:
            lat = _to_deg(gps_lat)
            if gps_lat_ref.upper() == 'S':
                lat = -lat if lat is not None else None
            lon = _to_deg(gps_lon)
            if gps_lon_ref.upper() == 'W':
                lon = -lon if lon is not None else None
    except Exception:
        pass
    return lat, lon


def compute_image_hash(path: Path) -> str:
    """Compute a deterministic hash for an image based on EXIF and basic metadata."""
    ts = make = brightness = ''
    lat = lon = None
    size = 0
    width = height = 0
    try:
        with Image.open(path) as img:
            # Basic metadata (dimensions + file size)
            width, height = img.size
            size = path.stat().st_size
            # Raw EXIF and map tag IDs to names
            raw = img._getexif() or {}
            named = {TAGS.get(tid, tid): val for tid, val in raw.items()}
            dto = named.get('DateTimeOriginal')
            if isinstance(dto, str):
                ts = dto
            else:
                try:
                    ts = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
                except Exception:
                    ts = ''

            make = named.get('Make', '') or ''

            # BrightnessValue if available
            bv = named.get('BrightnessValue')
            if isinstance(bv, tuple) and len(bv) == 2:
                try:
                    brightness = str(bv[0] / bv[1])
                except Exception:
                    brightness = ''
            elif bv is not None:
                brightness = str(bv)

            # GPSInfo if present
            gps_info = named.get('GPSInfo')
            if isinstance(gps_info, dict):
                lat, lon = _convert_gps(gps_info)
    except Exception:
        logger.debug("Error opening or parsing EXIF for %s", path, exc_info=True)

    # Build fingerprint string (omit model/lens, add file size & brightness)
    parts = [ts, make, str(width), str(height), str(size), brightness, str(lat), str(lon)]
    fingerprint = '|'.join(parts)
    logger.info("Fingerprint parts for %s: %r", path, parts)
    # Return SHA256 hex digest
    return hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()


class ImageCache:
    """Persistent cache for image analysis results by image fingerprint with versioning and cleanup."""

    def __init__(self, cache_file: Path = DEFAULT_CACHE_FILE, model: str = "gpt-4.1-nano"):
        self.cache_file = cache_file
        self.model = model
        self._cache = load_cache(cache_file)
        
        # Ensure cache has proper structure
        if "entries" not in self._cache:
            self._cache = {"version": CACHE_VERSION, "entries": {}}
        
        # Check if cache version is outdated
        if self._cache.get("version") != CACHE_VERSION:
            logger.info(f"Cache version mismatch. Expected {CACHE_VERSION}, got {self._cache.get('version', 'unknown')}")
            self._invalidate_outdated_entries()

    def get(self, path: Path) -> Optional[str]:
        """Return cached analysis result for image, or None if not present.
        Only returns results from current version and model."""
        key = compute_image_hash(path)
        entry_data = self._cache.get("entries", {}).get(key)
        
        if entry_data is None:
            return None
        
        # Handle both new CacheEntry format and legacy dict format
        if isinstance(entry_data, dict):
            entry = CacheEntry.from_dict(entry_data)
        else:
            # Legacy format
            return entry_data
        
        # Check if entry is valid (current version and model)
        if entry.version != CACHE_VERSION or entry.model != self.model:
            logger.debug(f"Cache entry outdated for {path.name}: version={entry.version}, model={entry.model}")
            return None
        
        return entry.result

    def set(self, path: Path, result: str) -> None:
        """Store the file path and analysis result for image, and persist cache to disk."""
        key = compute_image_hash(path)
        entry = CacheEntry(
            path=str(path),
            result=result,
            version=CACHE_VERSION,
            model=self.model
        )
        
        if "entries" not in self._cache:
            self._cache["entries"] = {}
        
        self._cache["entries"][key] = entry.to_dict()
        save_cache(self._cache, self.cache_file)

    def _invalidate_outdated_entries(self) -> None:
        """Remove entries that don't match current version or model."""
        if "entries" not in self._cache:
            return
        
        original_count = len(self._cache["entries"])
        valid_entries = {}
        
        for key, entry_data in self._cache["entries"].items():
            if isinstance(entry_data, dict):
                entry = CacheEntry.from_dict(entry_data)
                if entry.version == CACHE_VERSION and entry.model == self.model:
                    valid_entries[key] = entry_data
            else:
                # Legacy entry - remove it
                continue
        
        self._cache["entries"] = valid_entries
        self._cache["version"] = CACHE_VERSION
        
        removed_count = original_count - len(valid_entries)
        if removed_count > 0:
            logger.info(f"Invalidated {removed_count} outdated cache entries")
            save_cache(self._cache, self.cache_file)

    def cleanup(self, max_age_days: int = 30, max_entries: int = 10000) -> int:
        """
        Clean up old cache entries.
        
        Args:
            max_age_days: Remove entries older than this many days
            max_entries: Maximum number of entries to keep (removes oldest first)
            
        Returns:
            Number of entries removed
        """
        if "entries" not in self._cache:
            return 0
        
        entries = self._cache["entries"]
        original_count = len(entries)
        
        # Remove entries older than max_age_days
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        valid_entries = {}
        
        for key, entry_data in entries.items():
            if isinstance(entry_data, dict):
                entry = CacheEntry.from_dict(entry_data)
                if entry.timestamp >= cutoff_time:
                    valid_entries[key] = entry_data
            else:
                # Legacy entry - remove it
                continue
        
        # If still too many entries, remove oldest ones
        if len(valid_entries) > max_entries:
            # Sort by timestamp and keep only the newest max_entries
            sorted_entries = sorted(
                valid_entries.items(),
                key=lambda x: CacheEntry.from_dict(x[1]).timestamp,
                reverse=True
            )
            valid_entries = dict(sorted_entries[:max_entries])
        
        self._cache["entries"] = valid_entries
        removed_count = original_count - len(valid_entries)
        
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} cache entries")
            save_cache(self._cache, self.cache_file)
        
        return removed_count

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if "entries" not in self._cache:
            return {"total_entries": 0, "size_bytes": 0, "oldest_entry": None, "newest_entry": None}
        
        entries = self._cache["entries"]
        if not entries:
            return {"total_entries": 0, "size_bytes": 0, "oldest_entry": None, "newest_entry": None}
        
        timestamps = []
        for entry_data in entries.values():
            if isinstance(entry_data, dict):
                entry = CacheEntry.from_dict(entry_data)
                timestamps.append(entry.timestamp)
        
        if timestamps:
            oldest = min(timestamps)
            newest = max(timestamps)
        else:
            oldest = newest = None
        
        return {
            "total_entries": len(entries),
            "size_bytes": len(json.dumps(self._cache)),
            "oldest_entry": datetime.fromtimestamp(oldest).isoformat() if oldest else None,
            "newest_entry": datetime.fromtimestamp(newest).isoformat() if newest else None,
            "cache_version": self._cache.get("version", "unknown")
        }
