#!/usr/bin/env python3
"""
rich_ui.py: Rich-based user interface for image-cleanup-tool.

Launches an interactive terminal UI to scan directories for images,
display progress bars, and show analysis results in real-time.
"""

import asyncio


import time
import threading
from queue import Queue, Empty
from pathlib import Path
from collections import Counter
from typing import Any, List

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.prompt import Prompt
from rich.table import Table

from ..core.backbone import ImageScanEngine
from ..utils.log_utils import get_logger

logger = get_logger(__name__)


class RichImageScannerUI:
    """Rich-based UI for scanning images and displaying information in real-time."""

    def __init__(self, root: Path, api_providers: list[str], size: int = 512):
        self.engine = ImageScanEngine(root)
        self.api_providers = api_providers if isinstance(api_providers, list) else [api_providers]
        self.size = size
        self.console = Console()
        self.analysis_results: List[str] = []
        self.scan_complete = False
        self.cache_complete = False
        self.analysis_started = False
        self.live_display = None
        self.layout = None
        self.current_api_index = 0
        self.status_text = Text(f"Initializing with {size}x{size} images and {len(self.api_providers)} API(s): {', '.join(self.api_providers)}", style="blue")
        # Thread-safe UI event queue for updates from background threads
        self.ui_events: Queue = Queue()

    def _create_layout(self) -> Layout:
        """Create the main layout structure."""
        layout = Layout()
        
        # Top section for progress bars (6 lines)
        # Bottom section for results (3 lines)
        layout.split_column(
            Layout(name="progress_section", size=6),
            Layout(name="results_section", size=3)
        )
        
        return layout

    def _create_progress_section(self) -> Panel:
        """Create the progress section with all progress bars."""
        # Create a table to hold all progress bars
        table = Table(show_header=False, box=None, padding=0)
        table.add_column("Progress", width=80)
        # Status line at the top
        table.add_row(self.status_text)
        
        # Scan progress bar
        scan_progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]Scanning files..."),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console
        )
        
        # Cache progress bar
        cache_progress = Progress(
            TextColumn("[bold green]Cache status: "),
            BarColumn(complete_style="green", finished_style="green"),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            console=self.console
        )
        
        # Analysis progress bar
        analysis_progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold yellow]Analyzing images..."),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=self.console
        )
        
        # Initially hide cache and analysis progress
        cache_progress.visible = False
        analysis_progress.visible = False
        
        self.scan_progress = scan_progress
        self.cache_progress = cache_progress
        self.analysis_progress = analysis_progress
        
        # Add progress bars to table
        table.add_row(scan_progress)
        table.add_row(cache_progress)
        table.add_row(analysis_progress)
        
        return Panel(
            table,
            title="[bold]Progress",
            border_style="blue"
        )

    def _create_results_section(self) -> Panel:
        """Create the results section for analysis descriptions."""
        self.results_text = Text("Waiting for analysis results...", style="dim")
        
        return Panel(
            self.results_text,
            title="[bold]Analysis Results",
            border_style="green",
            width=120,
        )

    def _update_results_display(self, new_result: str):
        """Update the results display with new analysis result."""
        self.analysis_results.append(new_result)

        # Keep only the last 3 results
        if len(self.analysis_results) > 3:
            self.analysis_results = self.analysis_results[-3:]

        # Mutate the existing Text object to avoid replacing renderables
        display_text = "\n\n".join(self.analysis_results)
        self.results_text.plain = display_text

    def _on_scan_progress(self, scanned: int, total: int, ext_counter: Counter,
                         device_counter: Counter, date_ext_counter: dict, non_image: int):
        """Handle scan progress updates."""
        if not self.scan_complete:
            self.scan_progress.update(self.scan_task_id, completed=scanned, total=total)
            # Live display will auto-refresh, no need for manual refresh

    def _on_scan_complete(self):
        """Handle scan completion."""
        self.scan_complete = True
        self.scan_progress.update(self.scan_task_id, completed=self.engine.total_files)
        self.status_text.plain = "✓ File scanning complete!"
        self.status_text.style = "green"
        # Live display will auto-refresh, no need for manual refresh

    def _on_cache_progress(self, scanned: int, known: int):
        """Handle cache progress updates."""
        if not self.cache_complete:
            total = len(self.engine.image_paths)
            self.cache_progress.update(self.cache_task_id, completed=known, total=total)
            # Live display will auto-refresh, no need for manual refresh

    def _on_cache_complete(self, known: int, total: int):
        """Handle cache completion for current API."""
        current_api = self.api_providers[self.current_api_index] if self.current_api_index < len(self.api_providers) else "unknown"
        self.cache_progress.update(self.cache_task_id, completed=known, total=total)

        uncached = total - known
        self.status_text.plain = f"✓ Cache check complete for {current_api}: {known}/{total} known"
        self.status_text.style = "green"
        self.cache_complete = True

        if uncached > 0:
            # Start analysis automatically for current API
            self._start_analysis_auto()
        else:
            # Check if we have more APIs to process
            if self.current_api_index < len(self.api_providers) - 1:
                self.current_api_index += 1
                self._start_next_api_processing()
            else:
                self.status_text.plain = "✓ All images analyzed with all APIs!"
                self.status_text.style = "green"

        # Live display will auto-refresh, no need for manual refresh

    def _start_next_api_processing(self):
        """Start processing the next API provider."""
        if self.current_api_index < len(self.api_providers):
            next_api = self.api_providers[self.current_api_index]
            self.status_text.plain = f"Starting cache check for {next_api}..."
            self.status_text.style = "blue"
            self.cache_complete = False

            # Show cache progress bar
            self.cache_progress.visible = True
            self.cache_task_id = self.cache_progress.add_task(
                f"Checking cache for {next_api}...",
                total=len(self.engine.image_paths)
            )
            self.engine.check_cache(next_api, self.size)

    def _on_analysis_progress(self, path: Path, analyzed: int, total: int, result: Any):
        """Handle analysis progress updates."""
        if not self.analysis_started:
            return

        # Enqueue updates to be processed on the main thread
        description = None
        if isinstance(result, dict) and "description" in result:
            description = result.get("description", "")
        self.ui_events.put(("analysis_progress", analyzed, total, description))

    def _start_analysis_auto(self):
        """Start the analysis process automatically for current API."""
        current_api = self.api_providers[self.current_api_index]
        self.analysis_started = True
        uncached_count = len(self.engine.uncached_images)

        if uncached_count == 0:
            return

        # Show analysis progress bar
        self.analysis_progress.visible = True
        self.analysis_task_id = self.analysis_progress.add_task(
            f"Analyzing images with {current_api}...",
            total=uncached_count
        )

        # Start analysis in background thread
        analysis_thread = threading.Thread(target=self._run_analysis_sync, args=(current_api,))
        analysis_thread.daemon = True
        analysis_thread.start()

        # Store the thread for waiting
        self.analysis_thread = analysis_thread

    def _on_analysis_complete(self):
        """Handle analysis completion for current API."""
        # Enqueue completion to be handled on the main thread
        self.ui_events.put(("analysis_complete",))

    def _run_analysis_sync(self, api_provider: str):
        """Run analysis synchronously in a separate thread for a specific API."""
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Run the async analysis for this specific API
            loop.run_until_complete(
                self.engine.run_analysis_async(
                    max_concurrent=5,
                    requests_per_minute=30,
                    size=self.size,
                    api_providers=[api_provider]
                )
            )
        except Exception as e:
            self.console.print(f"[red]Analysis error for {api_provider}: {e}[/red]")

    def _drain_ui_events(self) -> None:
        """Process all queued UI events on the main thread."""
        while True:
            try:
                event = self.ui_events.get_nowait()
            except Empty:
                break

            if not event:
                continue

            kind = event[0]
            if kind == "analysis_progress":
                analyzed, total, description = event[1], event[2], event[3]
                if hasattr(self, 'analysis_task_id'):
                    self.analysis_progress.update(self.analysis_task_id, completed=analyzed, total=total)
                if description:
                    self._update_results_display(description)
            elif kind == "analysis_complete":
                if hasattr(self, 'analysis_task_id'):
                    task = self.analysis_progress.get_task(self.analysis_task_id)
                    self.analysis_progress.update(self.analysis_task_id, completed=task.total)
                self.analysis_started = False

                if self.current_api_index < len(self.api_providers) - 1:
                    self.current_api_index += 1
                    self.status_text.plain = f"✓ Analysis complete for previous API. Starting next API..."
                    self.status_text.style = "green"
                    self._start_next_api_processing()
                else:
                    self.status_text.plain = "✓ All analysis complete for all APIs!"
                    self.status_text.style = "green"
                    self._update_results_display("[bold green]All images analyzed with all APIs![/bold green]")

    def _run_ui(self):
        """Run the Rich-based UI."""
        # Bind engine callbacks
        self.engine.on_scan_progress = self._on_scan_progress
        self.engine.on_scan_complete = self._on_scan_complete
        self.engine.on_cache_progress = self._on_cache_progress
        self.engine.on_cache_complete = self._on_cache_complete
        self.engine.on_analysis_progress = self._on_analysis_progress
        self.engine.on_analysis_complete = self._on_analysis_complete

        try:
            # Create the layout
            self.layout = self._create_layout()
            
            # Create progress section
            progress_panel = self._create_progress_section()
            self.layout["progress_section"].update(progress_panel)
            
            # Create results section
            results_panel = self._create_results_section()
            self.layout["results_section"].update(results_panel)
            
            # Start the live display with the full layout
            with Live(
                self.layout, 
                refresh_per_second=4, 
                screen=True
            ) as live:
                self.live_display = live
                
                # Calculate total files first
                self.console.print("[bold blue]Calculating total files...[/bold blue]")
                self.engine.calculate_total()
                
                # Start scan progress
                self.scan_task_id = self.scan_progress.add_task(
                    "Scanning files...",
                    total=self.engine.total_files
                )
                
                # Start scanning
                self.engine.scan_files()
                
                # After scan, start cache check for first API
                if self.scan_complete:
                    self._start_next_api_processing()
                    
                    # Process events while cache/analysis progress
                    while True:
                        self._drain_ui_events()
                        analysis_alive = hasattr(self, 'analysis_thread') and self.analysis_thread.is_alive()
                        all_done = (not analysis_alive) and (self.current_api_index >= len(self.api_providers) - 1) and self.cache_complete and not self.analysis_started
                        if all_done:
                            break
                        time.sleep(0.05)

                # No need for final refresh - Live display will auto-refresh
                
                # Pause to show final results
                self.console.print("\n[bold green]✓ All operations complete![/bold green]")
                self.console.print("[dim]Press Enter to exit...[/dim]")
                input()
                
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")

    @staticmethod
    def run(root: Path, api_providers: list[str], size: int = 512) -> None:
        """Convenience method to launch the Rich app."""
        ui = RichImageScannerUI(root, api_providers, size)
        ui._run_ui() 