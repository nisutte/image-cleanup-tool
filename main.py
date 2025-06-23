#!/usr/bin/env python3
"""
main.py: Recursively scan a directory (or single file) for images, count them by extension,
and display a histogram of capture dates in the terminal.

Supported image formats: JPEG, PNG, HEIC/HEIF.
"""

import argparse
import sys

from collections import Counter

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

from image_cache import ImageCache

from typing import Any
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, ProgressBar, Button, Static
from textual.containers import Horizontal, Vertical
from textual import events

from utils import *
 
class ImageScannerApp(App):
    """Textual app for scanning images and displaying information in real-time."""

    CSS = """
    Screen {
        align: center middle;
        padding: 1;
    }
    #scan_section, #cache_section, #analysis_section {
        border: solid gray;
        width: 100%;
        padding: 1;
        margin: 1 0;
    }
    #scan_section ProgressBar {
        width: 100%;
        margin: 1 0;
    }
    #tables {
        height: auto;
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
    #cache_section Static, #analysis_section Static {
        height: auto;
    }
    #analysis_section ProgressBar {
        width: 100%;
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
        self.image_paths: list[Path] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        # Section 1: Scanning overview
        with Vertical(id="scan_section"):
            yield ProgressBar(id="progress")
            with Horizontal(id="tables"):
                yield DataTable(id="ext_table")
                yield DataTable(id="device_table")
                yield DataTable(id="hist_table")
        # Section 2: Cache actions
        with Vertical(id="cache_section"):
            yield Static("", id="cache_bar")
            yield Button("Check Cache", id="check_cache_btn")
        # Section 3: Analysis placeholder
        with Vertical(id="analysis_section"):
            yield Button("Cleanup", id="cleanup_btn")
            yield ProgressBar(id="analysis_progress")
            yield Static("", id="analysis_label")
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
        # Hide cache bar initially and disable cache button
        cache_bar = self.query_one("#cache_bar", Static)
        cache_bar.visible = False
        cache_btn = self.query_one("#check_cache_btn", Button)
        cache_btn.disabled = True
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
                self.image_paths.append(path)
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
        # Final UI update and start cache verification
        self.call_from_thread(self._update_ui)
        self.call_from_thread(self._scan_complete)

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
    
    def _scan_complete(self) -> None:
        """Called after initial scan; notify and start cache verification."""
        self.notify("Scanning complete!", title="Done")
        # Enable cache check button now that scan is done
        cache_btn = self.query_one("#check_cache_btn", Button)
        cache_btn.disabled = False

    def _check_cache(self) -> None:
        """Worker to check which images have prior analysis in cache."""
        cache = ImageCache()
        scanned = 0
        known = 0
        for path in self.image_paths:
            if cache.get(path) is not None:
                known += 1
            scanned += 1
            self.call_from_thread(self._update_cache_bar, scanned, known)
        self.call_from_thread(self._cache_complete, known)

    def _update_cache_bar(self, scanned: int, known: int) -> None:
        """Update the cache status bar with colored segments."""
        bar = self.query_one("#cache_bar", Static)
        total = len(self.image_paths)
        # Determine segment sizes
        BAR_WIDTH = 40
        known_width = int((known / total) * BAR_WIDTH) if total else 0
        uncached = scanned - known
        uncached_width = int((uncached / total) * BAR_WIDTH) if total else 0
        remaining_width = BAR_WIDTH - known_width - uncached_width
        # Build colored bar
        bar_markup = (
            "[green]" + "█" * known_width + "[/green]"
            + "[red]" + "█" * uncached_width + "[/red]"
            + "[yellow]" + "█" * remaining_width + "[/yellow]"
        )
        # Update with bar and counts
        bar.update(
            f"{bar_markup}  Cached: {known}/{total}, "
            f"Uncached: {uncached}, Remaining: {total - scanned}"
        )

    def _cache_complete(self, known: int) -> None:
        """Notify when cache checking is finished."""
        total_images = len(self.image_paths)
        self.notify(f"Cache check complete: {known}/{total_images} known", title="Cache Done")
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses for cache check and cleanup."""
        btn_id = event.button.id
        if btn_id == "check_cache_btn":
            cache_bar = self.query_one("#cache_bar", Static)
            cache_bar.visible = True
            self._update_cache_bar(0, 0)
            self.run_worker(self._check_cache, name="check_cache", thread=True)

    async def on_key(self, event: events.Key) -> None:
        if event.key == "q":
            await self.action_quit()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Scan a directory for image files, get summarization and start the cleanup when ready"
    )
    parser.add_argument(
        "input",
        help="Path to directory of images",
    )
    return parser.parse_args()








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
