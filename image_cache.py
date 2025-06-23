"""
image_cache.py - persistent per-image analysis cache based on metadata fingerprint.

Provides utilities to compute a stable hash for an image using EXIF metadata
(creation timestamp, device make/model, lens model, dimensions, GPS) and cache
analysis results in a JSON-backed dict to avoid reprocessing images.

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
from datetime import datetime
from typing import Dict, Optional, Tuple

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass
from log_utils import get_logger

logger = get_logger(__name__)

# Default cache file in working directory
DEFAULT_CACHE_FILE = Path('.image_analysis_cache.json')


def load_cache(cache_file: Path = DEFAULT_CACHE_FILE) -> Dict[str, str]:
    """Load the cache from disk (JSON), or return empty dict on failure."""
    if cache_file.is_file():
        try:
            return json.loads(cache_file.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}


def save_cache(cache: Dict[str, str], cache_file: Path = DEFAULT_CACHE_FILE) -> None:
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
    """Simple persistent cache for image analysis results by image fingerprint."""

    def __init__(self, cache_file: Path = DEFAULT_CACHE_FILE):
        self.cache_file = cache_file
        self._cache = load_cache(cache_file)

    def get(self, path: Path) -> Optional[str]:
        """Return cached result string for image, or None if not present."""
        key = compute_image_hash(path)
        return self._cache.get(key)

    def set(self, path: Path, result: str) -> None:
        """Store the result string for the image and persist cache to disk."""
        key = compute_image_hash(path)
        self._cache[key] = result
        save_cache(self._cache, self.cache_file)
