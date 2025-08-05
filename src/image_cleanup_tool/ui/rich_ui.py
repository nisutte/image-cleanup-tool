#!/usr/bin/env python3
"""
rich_ui.py: Rich-based user interface for image-cleanup-tool.

Launches an interactive terminal UI to scan directories for images,
display progress bars, and show analysis results in real-time.
"""

import asyncio


import time
import threading
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

    def __init__(self, root: Path):
        self.engine = ImageScanEngine(root)
        self.console = Console()
        self.analysis_results: List[str] = []
        self.scan_complete = False
        self.cache_complete = False
        self.analysis_started = False
        self.live_display = None
        self.layout = None
        self.status_text = Text("Initializing...", style="blue")

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
        
        # Update the display - join with double newlines for better spacing
        display_text = "\n\n".join(self.analysis_results)
        self.results_text = Text(display_text)
        
        # Update the results section in the layout
        if self.live_display and self.layout:
            # Create a new results panel with updated text
            results_panel = Panel(
                self.results_text,
                title="[bold]Analysis Results",
                border_style="green",
                width=120
            )
            
            # Update only the results section in the layout
            self.layout["results_section"].update(results_panel)
            self.live_display.update(self.layout)

    def _on_scan_progress(self, scanned: int, total: int, ext_counter: Counter, 
                         device_counter: Counter, date_ext_counter: dict, non_image: int):
        """Handle scan progress updates."""
        if not self.scan_complete:
            self.scan_progress.update(self.scan_task_id, completed=scanned, total=total)
            # Force refresh the display
            if self.live_display:
                self.live_display.refresh()

    def _on_scan_complete(self):
        """Handle scan completion."""
        self.scan_complete = True
        self.scan_progress.update(self.scan_task_id, completed=self.engine.total_files)
        self.status_text = Text("✓ File scanning complete!", style="green")
        # Force refresh the display
        if self.live_display:
            self.live_display.refresh()

    def _on_cache_progress(self, scanned: int, known: int):
        """Handle cache progress updates."""
        if not self.cache_complete:
            total = len(self.engine.image_paths)
            self.cache_progress.update(self.cache_task_id, completed=known, total=total)
            # Force refresh the display
            if self.live_display:
                self.live_display.refresh()

    def _on_cache_complete(self, known: int, total: int):
        """Handle cache completion."""
        self.cache_complete = True
        self.cache_progress.update(self.cache_task_id, completed=known, total=total)
        
        uncached = total - known
        self.status_text = Text(f"✓ Cache check complete: {known}/{total} known", style="green")
        
        if uncached > 0:
            # Start analysis automatically
            self._start_analysis_auto()
        else:
            self.status_text = Text("✓ All images already analyzed!", style="green")
        
        # Force refresh the display
        if self.live_display:
            self.live_display.refresh()

    def _on_analysis_progress(self, path: Path, analyzed: int, total: int, result: Any):
        """Handle analysis progress updates."""
        if not self.analysis_started:
            return
            
        # Update progress bar
        self.analysis_progress.update(self.analysis_task_id, completed=analyzed, total=total)
        self.cache_progress.update(self.cache_task_id, completed=analyzed, total=total)
        
        # Update results display
        if isinstance(result, dict) and "description" in result:
            self._update_results_display(result.get("description", ""))
        
        # Force refresh the display
        if self.live_display:
            self.live_display.refresh()

    def _start_analysis_auto(self):
        """Start the analysis process automatically."""
        self.analysis_started = True
        uncached_count = len(self.engine.uncached_images)
        
        if uncached_count == 0:
            return
        
        # Show analysis progress bar
        self.analysis_progress.visible = True
        self.analysis_task_id = self.analysis_progress.add_task(
            "Analyzing images...",
            total=uncached_count
        )
        
        # Start analysis in background thread
        analysis_thread = threading.Thread(target=self._run_analysis_sync)
        analysis_thread.daemon = True
        analysis_thread.start()
        
        # Store the thread for waiting
        self.analysis_thread = analysis_thread

    def _on_analysis_complete(self):
        """Handle analysis completion."""
        self.analysis_progress.update(self.analysis_task_id, completed=self.analysis_progress.tasks[0].total)
        self.status_text = Text("✓ Analysis complete!", style="green")
        self._update_results_display("[bold green]All images analyzed![/bold green]")
        
        # Force refresh the display
        if self.live_display:
            self.live_display.refresh()

    def _run_analysis_sync(self):
        """Run analysis synchronously in a separate thread."""
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run the async analysis
            loop.run_until_complete(
                self.engine.run_analysis_async(
                    max_concurrent=5,
                    requests_per_minute=30,
                    size=512
                )
            )
        except Exception as e:
            self.console.print(f"[red]Analysis error: {e}[/red]")

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
                refresh_per_second=10, 
                screen=False
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
                
                # After scan, start cache check
                if self.scan_complete:
                    # Show cache progress bar
                    self.cache_progress.visible = True
                    self.cache_task_id = self.cache_progress.add_task(
                        "Checking cache...",
                        total=len(self.engine.image_paths)
                    )
                    self.engine.check_cache()
                    
                    # Wait for cache completion
                    while not self.cache_complete:
                        time.sleep(0.1)
                    
                    # Wait for analysis to complete if it was started
                    if hasattr(self, 'analysis_thread') and self.analysis_thread.is_alive():
                        self.analysis_thread.join()
                
                # Final refresh to show completion
                self.live_display.refresh()
                
                # Pause to show final results
                self.console.print("\n[bold green]✓ All operations complete![/bold green]")
                self.console.print("[dim]Press Enter to exit...[/dim]")
                input()
                
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")

    @staticmethod
    def run(root: Path) -> None:
        """Convenience method to launch the Rich app."""
        ui = RichImageScannerUI(root)
        ui._run_ui() 