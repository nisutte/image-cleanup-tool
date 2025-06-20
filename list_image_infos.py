#!/usr/bin/env python3
"""
list_image_infos.py: Recursively scan a directory (or single file) for images, count them by extension,
and display a histogram of capture dates in the terminal.

Supported image formats: JPEG, PNG, HEIC/HEIF.
"""

import argparse
import sys
import os

from collections import Counter
from datetime import datetime

from pathlib import Path
from typing import Iterator

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

from PIL import Image

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.columns import Columns

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.heic', '.heif'}
EXT_COLORS = {
    '.jpg': 'blue', '.jpeg': 'blue',
    '.png': 'cyan',
    '.heic': 'green',    '.heif': 'green',
}
EXIF_TAG_DATETIME = 36867
EXIF_TAG_MAKE = 271
EXIF_TAG_MODEL = 272


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


def parse_args():
    parser = argparse.ArgumentParser(
        description="Scan a directory for image files, summarize counts and capture-date histogram"
    )
    parser.add_argument(
        "input",
        help="Path to directory or single image file to scan",
    )
    return parser.parse_args()


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


def main():
    args = parse_args()
    console = Console()
    root = Path(args.input)
    if not root.exists():
        console.print(f"[red]Error:[/] Path '{root}' does not exist.")
        sys.exit(1)

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description} {task.completed} files"),
        console=console,
    ) as discover:
        task_discover = discover.add_task("Discovering files...", total=None)
        total_files = 0
        for _ in iter_files(root):
            total_files += 1
            discover.advance(task_discover)

    ext_counter: Counter[str] = Counter()
    non_image_count = 0
    date_ext_counter: dict[str, Counter[str]] = {}
    device_counter: Counter[str] = Counter()

    progress = Progress(
        SpinnerColumn(),
        TextColumn("Scanning files..."),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )
    task = progress.add_task("scan", total=total_files)

    with progress:
        for path in iter_files(root):
            ext = path.suffix.lower()
            if ext in IMAGE_EXTS:
                ext_counter[ext] += 1
                dt = get_capture_datetime(path)
                year = str(dt.year)
                date_ext_counter.setdefault(year, Counter())[ext] += 1
                dev = get_device(path)
                device_counter[dev] += 1
            else:
                non_image_count += 1
            progress.advance(task)

    summary = Table(title="Image Counts by Extension")
    summary.add_column("Extension", style="cyan", justify="left")
    summary.add_column("Count", style="yellow", justify="right")
    for ext, cnt in sorted(ext_counter.items()):
        color = EXT_COLORS.get(ext, 'white')
        summary.add_row(f"[{color}]{ext}[/{color}]", str(cnt))
    summary.add_row("[bold white]Non-image files[/]", str(non_image_count))
    summary.add_row("[bold white]Total images[/]", str(sum(ext_counter.values())))
    device_table = Table(title="Image Counts by Device")
    device_table.add_column("Device", style="magenta", justify="left")
    device_table.add_column("Count", style="yellow", justify="right")
    for dev, cnt in sorted(device_counter.items(), key=lambda x: x[1], reverse=True):
        device_table.add_row(dev, str(cnt))
    console.print()
    console.print(Columns([summary, device_table]))

    if date_ext_counter:
        console.print()
        totals = [sum(cnts.values()) for cnts in date_ext_counter.values()]
        max_total = max(totals) if totals else 0
        hist = Table(title="Capture Date Histogram:", show_header=False)
        hist.add_column("Year", style="green", width=8)
        hist.add_column("Bar")
        hist.add_column("Count", style="yellow", justify="right")
        BAR_WIDTH = 40
        for year, cnts in sorted(date_ext_counter.items()):
            total_y = sum(cnts.values())
            length_total = int(total_y / max_total * BAR_WIDTH) if max_total else 0
            bar_segments: list[str] = []
            if total_y:
                for ext, cnt in sorted(cnts.items()):
                    seg_len = int(cnt / total_y * length_total)
                    color = EXT_COLORS.get(ext, 'white')
                    if seg_len:
                        bar_segments.append(f"[{color}]" + "█" * seg_len + f"[/{color}]")
            bar = "".join(bar_segments)
            hist.add_row(year, bar, str(total_y))
        console.print(hist)


if __name__ == "__main__":
    main()
