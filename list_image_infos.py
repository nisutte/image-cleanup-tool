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

from typing import Any
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, ProgressBar, Button
from textual.containers import Horizontal
from textual import events
 
class ImageScannerApp(App):
    """Textual app for scanning images and displaying information in real-time."""

    CSS = """
    Screen {
        align: center middle;
        padding: 1;
    }
    #tables {
        height: 1fr;
        width: 100%;
    }
    #ext_table {
        width: 2fr;
    }
    #device_table {
        width: 3fr;
    }
    #hist_table {
        width: 4fr;
    }
    ProgressBar {
        width: 60%;
        margin: 1 0;
    }
    """

    def __init__(self, root: Path, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.root = root
        self.ext_counter: Counter[str] = Counter()
        self.device_counter: Counter[str] = Counter()
        self.date_ext_counter: dict[str, Counter[str]] = {}
        self.non_image_count: int = 0
        self.total_files: int = 0
        self.scanned_count: int = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield ProgressBar(id="progress")
        with Horizontal(id="tables"):
            yield DataTable(id="ext_table")
            yield DataTable(id="device_table")
            yield DataTable(id="hist_table")
        yield Button("Cleanup", id="cleanup_btn")
        yield Footer()

    async def on_mount(self) -> None:
        self.ext_table = self.query_one("#ext_table", DataTable)
        self.device_table = self.query_one("#device_table", DataTable)
        self.hist_table = self.query_one("#hist_table", DataTable)
        self.ext_table.add_columns("Extension", "Count")
        self.device_table.add_columns("Device", "Count")
        self.hist_table.add_columns("Year", "Bar", "Count")

        # Calculate total files in background thread
        worker = self.run_worker(self._calculate_total, name="calculate_total", thread=True)
        await worker.wait()
        # Configure progress bar with total file count
        pb = self.query_one("#progress", ProgressBar)
        pb.update(total=self.total_files)
        # Start scanning files in background thread
        self.run_worker(self._scan_files, name="scan_files", thread=True)

    def _calculate_total(self) -> None:
        count = 0
        for _ in iter_files(self.root):
            count += 1
        self.total_files = count

    def _scan_files(self) -> None:
        for path in iter_files(self.root):
            ext = path.suffix.lower()
            if ext in IMAGE_EXTS:
                self.ext_counter[ext] += 1
                dt = get_capture_datetime(path)
                year = str(dt.year)
                self.date_ext_counter.setdefault(year, Counter())[ext] += 1
                dev = get_device(path)
                self.device_counter[dev] += 1
            else:
                self.non_image_count += 1
            self.scanned_count += 1
            if self.scanned_count % 24 == 0:
                self.call_from_thread(self._update_ui)
        self.call_from_thread(self._update_ui)
        self.call_from_thread(self.notify, "Scanning complete!", title="Done")

    def _update_ui(self) -> None:
        pb = self.query_one("#progress", ProgressBar)
        pb.update(progress=self.scanned_count)

        self.ext_table.clear()
        for ext, cnt in sorted(self.ext_counter.items()):
            self.ext_table.add_row(ext, str(cnt))
        self.ext_table.add_row("Non-image files", str(self.non_image_count))
        self.ext_table.add_row("Total 50 images", str(sum(self.ext_counter.values())))

        self.device_table.clear()
        for dev, cnt in sorted(self.device_counter.items(), key=lambda x: x[1], reverse=True):
            self.device_table.add_row(dev, str(cnt))

        self.hist_table.clear()
        totals = [sum(cnts.values()) for cnts in self.date_ext_counter.values()]
        max_total = max(totals) if totals else 0
        BAR_WIDTH = 30
        for year, cnts in sorted(self.date_ext_counter.items()):
            total_y = sum(cnts.values())
            length_total = int(total_y / max_total * BAR_WIDTH) if max_total else 0
            bar = "".join("█" for _ in range(length_total))
            self.hist_table.add_row(year, bar, str(total_y))

    async def on_key(self, event: events.Key) -> None:
        if event.key == "q":
            await self.action_quit()

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.heic', '.heif'}
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
    root = Path(args.input)
    if not root.exists():
        print(f"Error: Path '{root}' does not exist.", file=sys.stderr)
        sys.exit(1)
    ImageScannerApp(root).run()
    return



if __name__ == "__main__":
    main()
