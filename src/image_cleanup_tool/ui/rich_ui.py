#!/usr/bin/env python3
"""
rich_ui.py: Rich-based user interface for image-cleanup-tool.

Launches an interactive terminal UI to scan directories for images,
display progress bars, and show analysis results in real-time.
"""

import asyncio
import time
from pathlib import Path
from collections import Counter
from turtle import window_width
from typing import Any, List

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
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
        self.analysis_started = False
        self.live_display = None
        self.layout = None
        self.current_api_index = 0
        # Counters for decisions shown in the stats panel
        self.decision_counts: Counter = Counter()
        self.total_analyzed = 0
        self.stats_text = Text("Waiting for stats...", style="dim")
        self.status_text = Text(f"Initializing with {size}x{size} images and {len(self.api_providers)} API(s): {', '.join(self.api_providers)}", style="blue")

    def _create_layout(self) -> Layout:
        """Create the main layout structure."""
        layout = Layout()
        layout.split_column(
            Layout(name="progress_section", size=7),
            Layout(name="stats_section", size=4),
            Layout(name="results_section", size=3)
        )
        return layout

    def _create_progress_section(self) -> Panel:
        """Create the progress section with all progress bars."""
        # Create a table to hold all progress bars
        table = Table(show_header=False, box=None, padding=0)
        table.add_column("Progress", width=None)
        # Status line at the top
        table.add_row(self.status_text)
        
        # Scan progress bar
        scan_progress = Progress(
            SpinnerColumn("line"),
            TextColumn("[bold blue]Scanning files..."),
            BarColumn(bar_width=None),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console
        )
        
        # Cache status progress bar (how many are already cached)
        cache_progress = Progress(
            SpinnerColumn("flip"),
            TextColumn("[bold green]Cache status: "),
            BarColumn(complete_style="green", finished_style="green", bar_width=None),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            console=self.console
        )
        
        # Cache check progress bar (how many files checked against cache)
        cache_check_progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]Checking cache..."),
            BarColumn(bar_width=None),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            console=self.console
        )

        # Analysis progress bar
        analysis_progress = Progress(
            SpinnerColumn("dots8"),
            TextColumn("[bold yellow]Analyzing images..."),
            BarColumn(bar_width=None),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=self.console
        )
        
        # Initially hide cache and analysis progress
        cache_progress.visible = False
        cache_check_progress.visible = False
        analysis_progress.visible = False
        
        self.scan_progress = scan_progress
        self.cache_progress = cache_progress
        self.cache_check_progress = cache_check_progress
        self.analysis_progress = analysis_progress
        
        # Add progress bars to table
        table.add_row(scan_progress)
        table.add_row(cache_check_progress)
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
        )

    def _create_stats_section(self) -> Panel:
        """Create the statistics panel showing keep/unsure/delete percentages."""
        # self.stats_text is a Text renderable that will be mutated/updated
        return Panel(
            self.stats_text,
            title="[bold]Analysis Summary",
            border_style="magenta"
        )

    def _update_stats_panel(self) -> None:
        """Rebuild the stats bar and update the layout panel if displayed."""
        total = self.total_analyzed
        # Build a simple horizontal bar of fixed width showing proportions
        bar_width = self.console.width - 4

        if total <= 0:
            # Empty bar and zeros
            bar = Text(" " * bar_width, style="dim")
            pct_keep = pct_unsure = pct_delete = 0
        else:
            pct_keep = self.decision_counts.get("keep", 0) / total
            pct_unsure = self.decision_counts.get("unsure", 0) / total
            pct_delete = self.decision_counts.get("delete", 0) / total

            keep_len = int(round(pct_keep * bar_width))
            unsure_len = int(round(pct_unsure * bar_width))
            delete_len = min(bar_width - keep_len - unsure_len, int(round(pct_delete * bar_width)))

            # Adjust to exactly bar_width
            filled = keep_len + unsure_len + delete_len
            if filled < bar_width:
                # add remaining to unsure for visibility
                unsure_len += (bar_width - filled)

            bar = Text()
            if keep_len > 0:
                bar.append("█" * keep_len, style="bold green")
            if unsure_len > 0:
                bar.append("█" * unsure_len, style="bold yellow")
            if delete_len > 0:
                bar.append("█" * delete_len, style="bold red")

        # Build label line with percentages
        label = Text()
        label.append(f" Keep {pct_keep*100:>5.1f}%", style="green")
        label.append(f"   Unsure {pct_unsure*100:>5.1f}%", style="yellow")
        label.append(f"   Delete {pct_delete*100:>5.1f}%", style="red")

        # Combine bar and labels into a single Text with a newline
        combined = Text.assemble(bar, Text("\n"), label)

        # Update stats_text and, if layout exists, update the displayed panel
        self.stats_text = combined
        try:
            if self.layout:
                # Attempt to update the stats panel in the live layout. If the
                # section hasn't been created yet or an error occurs, ignore it
                # as the Live display will refresh in the next cycle.
                self.layout["stats_section"].update(self._create_stats_section())
        except Exception:
            # Be resilient to update-time errors; Live will refresh next cycle
            pass

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

    def _on_cache_progress(self, known: int):
        """Handle cache progress updates."""
        total = len(self.engine.image_paths)
        self.cache_progress.update(self.cache_task_id, completed=known, total=total)

    def _on_cache_check_progress(self, checked: int):
        """Handle cache check progress (files examined)."""
        if hasattr(self, 'cache_check_task_id'):
            self.cache_check_progress.update(self.cache_check_task_id, completed=checked, total=len(self.engine.image_paths))

    def _on_cache_complete(self, known: int):
        """Handle cache completion for current API."""
        if hasattr(self, 'cache_task_id'):
            self.cache_progress.update(self.cache_task_id, completed=known, total=len(self.engine.image_paths))


    def _on_analysis_progress(self, path: Path, analyzed: int, total: int, result: Any):
        """Handle analysis progress updates."""
        if not self.analysis_started:
            return

        if hasattr(self, 'analysis_task_id'):
            self.analysis_progress.update(self.analysis_task_id, completed=analyzed, total=total)

        display_text = ""
        if isinstance(result, Exception):
            display_text = f"Error - {str(result)[:50]}..."
        elif isinstance(result, dict):
            # Extract decision and confidence
            decision = result.get("decision", "unknown")
            confidences = {
                "keep": result.get("confidence_keep", 0),
                "unsure": result.get("confidence_unsure", 0),
                "delete": result.get("confidence_delete", 0)
            }
            confidence = confidences.get(decision, 0)
            
            display_text = f"[{decision.upper()} {confidence*100:.0f}%] "
            reason = result.get("reason", "")
            if len(reason) > 80:
                reason = reason[:80] + "..."
            display_text += reason or "No reason provided"
        else:
            display_text = str(result)[:100] or "Analysis completed"

        # Update results display
        self._update_results_display(display_text)

        # Update decision counters for stats panel
        if isinstance(result, dict):
            if decision in ("keep", "unsure", "delete"):
                self.decision_counts[decision] += 1
                self.total_analyzed += 1
                # Rebuild stats bar
                self._update_stats_panel()

    def _on_analysis_complete(self):
        """Handle analysis completion for current API."""
        # This callback is called by the engine when analysis completes
        # We don't need to do anything here since we handle completion in _run_analysis_for_api
        pass

    async def _process_all_apis(self):
        """Process cache check and analysis for all API providers sequentially."""
        for api_index, api_provider in enumerate(self.api_providers):
            self.current_api_index = api_index

            # Start cache check for this API
            self.status_text.plain = f"Starting cache check for {api_provider}..."
            self.status_text.style = "blue"

            # Show cache status and cache check progress bars
            self.cache_progress.visible = True
            self.cache_check_progress.visible = True
            self.cache_task_id = self.cache_progress.add_task(
                f"Checking cache for {api_provider}...",
                total=len(self.engine.image_paths)
            )
            self.cache_check_task_id = self.cache_check_progress.add_task(
                f"Cache check for {api_provider}...",
                total=len(self.engine.image_paths)
            )

            # Run cache check (this will trigger progress updates via callbacks)
            self.engine.check_cache(api_provider, self.size)

            # Hide cache check progress once complete
            self.cache_check_progress.visible = False

            # Debug info
            uncached_count = len(self.engine.uncached_images)
            logger.info(f"[dim]Debug: Found {uncached_count} uncached images for {api_provider}[/dim]")

            # If there are uncached images, start analysis
            if len(self.engine.uncached_images) > 0:
                self.analysis_progress.visible = True
                await self._run_analysis_for_api(api_provider)
            else:
                self.status_text.plain = f"✓ All images already cached for {api_provider}"
                self.status_text.style = "green"
                # Ensure the cache status bar shows 100% completion
                self.cache_progress.update(self.cache_task_id, completed=len(self.engine.image_paths), total=len(self.engine.image_paths))
                # Hide cache status bar since there's nothing to analyze
                self.cache_progress.visible = False
                # Small delay to ensure UI updates are visible
                await asyncio.sleep(0.5)

    async def _run_analysis_for_api(self, api_provider: str):
        """Run analysis for a specific API and update UI accordingly."""
        self.analysis_started = True
        uncached_count = len(self.engine.uncached_images)

        # Show analysis progress bar
        self.analysis_task_id = self.analysis_progress.add_task(
            f"Analyzing images with {api_provider}...",
            total=uncached_count
        )

        try:
            # Run the async analysis for this specific API
            await self.engine.run_analysis_async(
                size=self.size,
                api_providers=[api_provider],
            )
            
            # Mark analysis as complete
            self.analysis_started = False
            self.status_text.plain = f"✓ Analysis complete for {api_provider}"
            self.status_text.style = "green"
            
        except Exception as e:
            logger.info(f"[red]Analysis error for {api_provider}: {e}[/red]")
            import traceback
            logger.info(f"[red]Traceback: {traceback.format_exc()}[/red]")
            self.analysis_started = False


    async def _run_ui(self):
        """Run the Rich-based UI."""
        # Bind engine callbacks
        self.engine.on_scan_progress = self._on_scan_progress
        self.engine.on_scan_complete = self._on_scan_complete
        self.engine.on_cache_progress = self._on_cache_progress
        self.engine.on_cache_complete = self._on_cache_complete
        self.engine.on_cache_check_progress = self._on_cache_check_progress
        self.engine.on_analysis_progress = self._on_analysis_progress
        self.engine.on_analysis_complete = self._on_analysis_complete

        try:
            # Create the layout
            self.layout = self._create_layout()
            
            # Create progress section
            progress_panel = self._create_progress_section()
            self.layout["progress_section"].update(progress_panel)
            
            # Create stats section
            stats_panel = self._create_stats_section()
            self.layout["stats_section"].update(stats_panel)

            # Create results section
            results_panel = self._create_results_section()
            self.layout["results_section"].update(results_panel)
            
            # Start the live display with the full layout
            with Live(
                self.layout, 
                refresh_per_second=20,  # Reduce refresh rate to prevent flickering
                screen=False  # Don't use full screen mode to see output
            ) as live:
                self.live_display = live
                
                # Calculate total files first
                logger.info("[bold blue]Calculating total files...[/bold blue]")
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
                    await self._process_all_apis()
                else:
                    logger.info("[red]Scan did not complete properly[/red]")

            # Show completion message and exit (outside Live context)
            logger.info("\n[bold green]✓ All operations complete![/bold green]")
                
        except Exception as e:
            logger.info(f"[red]Error: {e}[/red]")

    @staticmethod
    def run(root: Path, api_providers: list[str], size: int = 512) -> None:
        """Convenience method to launch the Rich app."""
        ui = RichImageScannerUI(root, api_providers, size)
        asyncio.run(ui._run_ui()) 