#!/usr/bin/env python3
"""
main.py: Command-line interface for image-cleanup-tool.

Runs a non-interactive scan to count images by extension and show a capture-date histogram.
Pass --ui to launch the interactive Textual UI.
"""

import sys
import argparse
from pathlib import Path

from backbone import ImageScanEngine

def parse_args():
    parser = argparse.ArgumentParser(
        description="Scan a directory for image files, display counts and optionally launch the interactive UI."
    )
    parser.add_argument(
        "input", help="Path to directory of images"
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Launch the interactive Textual UI instead of non-interactive CLI output",
    )
    return parser.parse_args()

def print_histogram(date_ext_counter):
    totals = [sum(cnts.values()) for cnts in date_ext_counter.values()]
    max_total = max(totals) if totals else 0
    BAR_WIDTH = 30
    for year, cnts in sorted(date_ext_counter.items()):
        total_y = sum(cnts.values())
        length = int(total_y / max_total * BAR_WIDTH) if max_total else 0
        bar = "█" * length
        print(f"{year:>4} | {bar} {total_y}")

def cli_run(root: Path):
    print(f"Scanning files under {root}...")
    engine = ImageScanEngine(root)
    engine.calculate_total()
    engine.scan_files()
    print("\nImage count by extension:")
    for ext, cnt in sorted(engine.ext_counter.items()):
        print(f"  {ext}: {cnt}")
    print(f"  Non-image files: {engine.non_image_count}")
    print("\nCapture date histogram:")
    print_histogram(engine.date_ext_counter)

    engine.check_cache()
    total = len(engine.image_paths)
    uncached = len(engine.uncached_images)
    cached = total - uncached
    print(f"\nCached images: {cached}/{total}")
    if uncached:
        print(f"{uncached} uncached images remain; press Enter to analyze one by one.")
        from openai_api import load_and_encode_image, analyze_image

        for path in engine.uncached_images:
            input(f"Press Enter to analyze {path.name} ({uncached - engine.uncached_images.index(path)} remaining)...")
            print(f"Analyzing {path}...")
            b64 = load_and_encode_image(str(path), 512)
            result = analyze_image(b64)
            print(f"Result: {result.get('final_classification')}")
            engine.cache.set(path, result)

def main():
    args = parse_args()
    root = Path(args.input)
    if not root.exists():
        print(f"Error: Path '{root}' does not exist.", file=sys.stderr)
        sys.exit(1)
    if args.ui:
        try:
            from ui_textual import ImageScannerApp
        except ImportError:
            print("Error: Textual UI dependencies are not installed.", file=sys.stderr)
            sys.exit(1)
        ImageScannerApp.run(root)
    else:
        cli_run(root)

if __name__ == "__main__":
    main()
