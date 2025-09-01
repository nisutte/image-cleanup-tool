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
    def __init__(self, path: str, result: str = None, version: str = CACHE_VERSION,
                 models: Dict[str, Dict[str, Any]] = None, model: str = None, size: int = 512):
        self.path = path
        self.version = version
        self.models = models or {}
        if result is not None:
            if model is None:
                raise ValueError("model must be provided when setting a result")
            # Store results under model + size key
            model_key = f"{model}_{size}"
            self.models[model_key] = {
                "result": result,
                "timestamp": time.time(),
                "size": size
            }
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "version": self.version,
            "models": self.models
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CacheEntry':
        # Handle both new format (with models) and legacy format
        if "models" in data:
            return cls(
                path=data.get("path", ""),
                version=data.get("version", "0.0"),
                models=data["models"]
            )
        else:
            # Legacy format - require model to be specified
            raise ValueError("Legacy cache entries require explicit model specification")


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

    def get(self, path: Path, model: str, size: int = 512) -> Optional[str]:
        """Return cached analysis result for image, model, and size, or None if not present.
        Only returns results from current version.

        Args:
            path: Path to the image file
            model: Name of the model/API to retrieve results for (required)
            size: Image size used for analysis (default: 512)
        """
        if not model:
            raise ValueError("model parameter is required")

        key = compute_image_hash(path)
        entry_data = self._cache.get("entries", {}).get(key)

        if entry_data is None:
            return None

        # Handle both new CacheEntry format and legacy dict format
        if isinstance(entry_data, dict):
            entry = CacheEntry.from_dict(entry_data)
        else:
            # Legacy format - no longer supported without model
            return None

        # Check if entry is valid (current version)
        if entry.version != CACHE_VERSION:
            logger.debug(f"Cache entry outdated for {path.name}: version={entry.version}")
            return None

        # Look for result with specific size
        model_key = f"{model}_{size}"
        result_data = entry.models.get(model_key)
        if result_data:
            return result_data.get("result")

        # Fallback: try legacy format without size
        return entry.models.get(model, {}).get("result")

    def set(self, path: Path, result: str, model: str, size: int = 512) -> None:
        """Store the file path and analysis result for image under specified model and size, and persist cache to disk.

        Args:
            path: Path to the image file
            result: Analysis result to store
            model: Name of the model/API that generated the result (required)
            size: Image size used for analysis (default: 512)
        """
        if not model:
            raise ValueError("model parameter is required")

        key = compute_image_hash(path)

        # Get existing entry or create new one
        entry_data = self._cache.get("entries", {}).get(key)
        if entry_data is not None and isinstance(entry_data, dict):
            entry = CacheEntry.from_dict(entry_data)
        else:
            entry = CacheEntry(path=str(path))

        # Update the model entry with size-specific key
        model_key = f"{model}_{size}"
        entry.models[model_key] = {
            "result": result,
            "timestamp": time.time(),
            "size": size
        }

        if "entries" not in self._cache:
            self._cache["entries"] = {}

        self._cache["entries"][key] = entry.to_dict()
        save_cache(self._cache, self.cache_file)

    def _invalidate_outdated_entries(self) -> None:
        """Remove entries that don't match current version."""
        if "entries" not in self._cache:
            return
        
        original_count = len(self._cache["entries"])
        valid_entries = {}
        
        for key, entry_data in self._cache["entries"].items():
            if isinstance(entry_data, dict):
                entry = CacheEntry.from_dict(entry_data)
                if entry.version == CACHE_VERSION:
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
        
        # Remove model entries older than max_age_days
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        valid_entries = {}
        
        for key, entry_data in entries.items():
            if isinstance(entry_data, dict):
                entry = CacheEntry.from_dict(entry_data)
                # Filter models by timestamp
                valid_models = {
                    model: data for model, data in entry.models.items()
                    if data.get("timestamp", 0) >= cutoff_time
                }
                if valid_models:
                    entry.models = valid_models
                    valid_entries[key] = entry.to_dict()
            else:
                # Legacy entry - remove it
                continue
        
        # If still too many entries, remove oldest ones
        if len(valid_entries) > max_entries:
            # Get all model timestamps across all entries
            all_timestamps = []
            for entry_data in valid_entries.values():
                entry = CacheEntry.from_dict(entry_data)
                for model_data in entry.models.values():
                    all_timestamps.append((entry_data, model_data.get("timestamp", 0)))
            
            # Sort by timestamp and keep only the newest max_entries
            all_timestamps.sort(key=lambda x: x[1], reverse=True)
            
            # Rebuild the cache with only the newest entries
            new_entries = {}
            for entry_data, _ in all_timestamps[:max_entries]:
                entry = CacheEntry.from_dict(entry_data)
                if entry.path not in new_entries:
                    new_entries[entry.path] = entry_data
                else:
                    # Merge models from duplicate entries
                    existing_entry = CacheEntry.from_dict(new_entries[entry.path])
                    existing_entry.models.update(entry.models)
                    new_entries[entry.path] = existing_entry.to_dict()
            
            valid_entries = new_entries
        
        self._cache["entries"] = valid_entries
        removed_count = original_count - len(valid_entries)
        
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} cache entries")
            save_cache(self._cache, self.cache_file)
        
        return removed_count

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if "entries" not in self._cache:
            return {"total_entries": 0, "total_models": 0, "size_bytes": 0, "oldest_entry": None, "newest_entry": None}
        
        entries = self._cache["entries"]
        if not entries:
            return {"total_entries": 0, "total_models": 0, "size_bytes": 0, "oldest_entry": None, "newest_entry": None}
        
        timestamps = []
        total_models = 0
        
        for entry_data in entries.values():
            if isinstance(entry_data, dict):
                entry = CacheEntry.from_dict(entry_data)
                total_models += len(entry.models)
                for model_data in entry.models.values():
                    timestamps.append(model_data.get("timestamp", 0))
        
        if timestamps:
            oldest = min(timestamps)
            newest = max(timestamps)
        else:
            oldest = newest = None
        
        return {
            "total_entries": len(entries),
            "total_models": total_models,
            "size_bytes": len(json.dumps(self._cache)),
            "oldest_entry": datetime.fromtimestamp(oldest).isoformat() if oldest else None,
            "newest_entry": datetime.fromtimestamp(newest).isoformat() if newest else None,
            "cache_version": self._cache.get("version", "unknown")
        }
