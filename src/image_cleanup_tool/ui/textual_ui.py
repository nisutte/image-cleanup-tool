#!/usr/bin/env python3
"""
ui_textual.py: Textual user interface for image-cleanup-tool.

Launches an interactive terminal UI to scan directories for images,
display counts and histograms, check cache status, and analyze uncached images.
"""

from pathlib import Path
from collections import Counter
from typing import Any
import time

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, ProgressBar, Static, Markdown, Switch
from textual.containers import Horizontal, Vertical, Grid
from textual import events

from ..core.backbone import ImageScanEngine


class ImageScannerApp(App):
    """Textual app for scanning images and displaying information in real-time."""

    CSS_PATH = "styles.tcss"

    def __init__(self, root: Path, **kwargs: Any) -> None:
        self.engine = ImageScanEngine(root)
        self.paused = False
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        # Main layout: top scan section (1/3 height), bottom interactive section (2/3 height)
        with Grid(id="layout"):
            # Scan overview (top third)
            with Vertical(id="scan_section"):
                yield ProgressBar(id="progress", show_eta=False)
                with Horizontal(id="tables"):
                    yield DataTable(id="ext_table")
                    yield DataTable(id="device_table")
                    yield DataTable(id="hist_table")
            # Cache and analysis controls + log
            with Vertical(id="interactive_section"):
                with Horizontal(id="cache_controls"):
                    yield ProgressBar(id="cache_progress", show_eta=False)
                    yield Switch(name="Analyze", id="analyze_toggle")
                # Analysis markdown log for colored output
                yield Markdown("", id="analysis_log")
        yield Footer()

    async def on_mount(self) -> None:
        # Bind engine callbacks
        self.engine.on_scan_progress = self._on_scan_progress
        self.engine.on_scan_complete = self._on_scan_complete
        self.engine.on_cache_progress = self._on_cache_progress
        self.engine.on_cache_complete = self._on_cache_complete
        self.engine.on_analysis_progress = self._on_analysis_log
        self.engine.on_analysis_complete = self._on_analysis_complete

        # Setup tables
        self.ext_table = self.query_one("#ext_table", DataTable)
        self.device_table = self.query_one("#device_table", DataTable)
        self.hist_table = self.query_one("#hist_table", DataTable)
        self.ext_table.add_columns("Extension", "Count")
        self.device_table.add_columns("Device", "Count")
        self.hist_table.add_columns("Year", "Bar", "Count")

        # Cache progress and analyze toggle
        cache_pb = self.query_one("#cache_progress", ProgressBar)
        cache_pb.visible = False
        toggle = self.query_one("#analyze_toggle", Switch)
        toggle.disabled = True

        # Analysis log (Markdown)
        self.analysis_log = self.query_one("#analysis_log", Markdown)
        # Buffer for appended lines
        self._analysis_lines: list[str] = []

        # Calculate total files, then start scanning
        worker = self.run_worker(self.engine.calculate_total, name="calculate_total", thread=True)
        await worker.wait()
        self.query_one("#progress", ProgressBar).update(total=self.engine.total_files)
        self.run_worker(self.engine.scan_files, name="scan_files", thread=True)

        # Configure layout: scan_section 1/3, interactive_section 2/3
        layout = self.query_one("#layout", Grid)
        layout.styles.grid_template_rows = "1fr 2fr"

    def _on_scan_progress(
        self,
        scanned: int,
        total: int,
        ext_counter: Counter,
        device_counter: Counter,
        date_ext_counter: dict[str, Counter],
        non_image: int,
    ) -> None:
        self.call_from_thread(
            self._update_scan_ui,
            scanned,
            ext_counter,
            device_counter,
            date_ext_counter,
            non_image,
        )

    def _update_scan_ui(
        self,
        scanned: int,
        ext_counter: Counter,
        device_counter: Counter,
        date_ext_counter: dict[str, Counter],
        non_image: int,
    ) -> None:
        pb = self.query_one("#progress", ProgressBar)
        pb.update(progress=scanned)

        self.ext_table.clear()
        for ext, cnt in sorted(ext_counter.items()):
            self.ext_table.add_row(ext, str(cnt))
        self.ext_table.add_row("Non-image files", str(non_image))
        self.ext_table.add_row("Total images", str(sum(ext_counter.values())))

        self.device_table.clear()
        for dev, cnt in sorted(device_counter.items(), key=lambda x: x[1], reverse=True):
            self.device_table.add_row(dev, str(cnt))

        self.hist_table.clear()
        totals = [sum(cnts.values()) for cnts in date_ext_counter.values()]
        max_total = max(totals) if totals else 0
        BAR_WIDTH = 30
        for year, cnts in sorted(date_ext_counter.items()):
            total_y = sum(cnts.values())
            length = int(total_y / max_total * BAR_WIDTH) if max_total else 0
            bar = "█" * length
            self.hist_table.add_row(year, bar, str(total_y))

    def _on_scan_complete(self) -> None:
        self.call_from_thread(self._scan_complete_ui)

    def _scan_complete_ui(self) -> None:
        """Called after scanning; notify and start cache verification."""
        self.notify("Scanning complete!", title="Done")
        cache_pb = self.query_one("#cache_progress", ProgressBar)
        cache_pb.visible = True
        cache_pb.update(total=len(self.engine.image_paths), progress=0)
        self.run_worker(self.engine.check_cache, name="check_cache", thread=True)

    def _on_cache_progress(self, scanned: int, known: int) -> None:
        self.call_from_thread(self._update_cache_progress, scanned, known)

    def _update_cache_progress(self, scanned: int, known: int) -> None:
        bar = self.query_one("#cache_progress", ProgressBar)
        bar.update(progress=scanned)

    def _on_cache_complete(self, known: int, total: int) -> None:
        self.call_from_thread(self._cache_complete_ui, known, total)

    def _cache_complete_ui(self, known: int, total: int) -> None:
        """Notify when cache checking is finished and enable analysis toggle."""
        self.notify(f"Cache complete: {known}/{total} known", title="Cache Done")
        toggle = self.query_one("#analyze_toggle", Switch)
        toggle.disabled = False
        uncached = total - known
        line = f"Cache complete: {known}/{total} known; {uncached} images to analyze."
        self._analysis_lines.append(line)
        self.analysis_log.update("\n".join(self._analysis_lines))

    def _on_analysis_log(self, path: Path, analyzed: int, total: int, result: Any) -> None:
        self.call_from_thread(self._update_analysis_log, path, analyzed, total, result)

    def _update_analysis_log(self, path: Path, analyzed: int, total: int, result: Any) -> None:
        """Append final_classification result for one image to the log, colored."""
        fc = result.get("final_classification", {})
        keep = fc.get("keep", 0)
        discard = fc.get("discard", 0)
        unsure = fc.get("unsure", 0)
        # Colorize each category
        colored = (
            f"[green]keep {keep}[/green], "
            f"[red]discard {discard}[/red], "
            f"[yellow]unsure {unsure}[/yellow]"
        )
        line = f"[{path.name}]: {' '.join(colored)}"
        self._analysis_lines.append(line)
        self.analysis_log.update("\n".join(self._analysis_lines))

    def _on_analysis_complete(self) -> None:
        """Called when all analysis is finished."""
        self.call_from_thread(self._analysis_complete_ui)

    def _analysis_complete_ui(self) -> None:
        line = "Analysis complete!"
        self._analysis_lines.append(line)
        self.analysis_log.update("\n".join(self._analysis_lines))
        self.notify("Analysis complete!", title="Done")


    async def on_switch_changed(self, event: Switch.Changed) -> None:
        """Toggle analyzing on or off based on the switch state."""
        if event.switch.id == "analyze_toggle":
            if event.value:
                # start analysis
                self.engine.paused = False
                # clear log buffer
                self._analysis_lines.clear()
                self.analysis_log.update("")
                self.run_worker(self.engine.run_analysis, name="analysis", thread=True)
            else:
                # pause analysis
                self.engine.paused = True

    async def on_key(self, event: events.Key) -> None:
        if event.key == "q":
            await self.action_quit()

    @staticmethod
    def run(root: Path) -> None:
        """Convenience method to launch the Textual app."""
        app = ImageScannerApp(root)
        # Call the base App.run to avoid recursion with this staticmethod
        App.run(app)