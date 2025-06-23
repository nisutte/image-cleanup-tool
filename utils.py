import os
from datetime import datetime
from pathlib import Path
from typing import Iterator
from PIL import Image

EXIF_TAG_DATETIME = 36867
EXIF_TAG_MAKE = 271
EXIF_TAG_MODEL = 272
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.heic', '.heif'}


def iter_files(root: Path) -> Iterator[Path]:
    """
    Recursively yield file paths under `root` using os.scandir for speed.
    """
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        yield Path(entry.path)
        except PermissionError:
            continue


def get_capture_datetime(path: Path) -> datetime:
    """
    Return the capture datetime of an image by reading EXIF DateTimeOriginal,
    falling back to the file's modification time on error or missing data.
    """
    try:
        img = Image.open(path)
        exif = img.getexif()
        dto = exif.get(EXIF_TAG_DATETIME)
        if isinstance(dto, str):
            return datetime.strptime(dto, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    mtime = path.stat().st_mtime
    return datetime.fromtimestamp(mtime)


def get_device(path: Path) -> str:
    try:
        img = Image.open(path)
        exif = img.getexif()
        make = exif.get(EXIF_TAG_MAKE)
        model = exif.get(EXIF_TAG_MODEL)
        parts = []
        if make:
            parts.append(str(make))
        if model:
            parts.append(str(model))
        if parts:
            return " ".join(parts)
    except Exception:
        pass
    return "Unknown"
