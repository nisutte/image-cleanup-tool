#!/usr/bin/env python3
"""
Main CLI entry point for image cleanup tool.
"""
import sys
import argparse
from pathlib import Path

from image_cleanup_tool.core.backbone import ImageScanEngine


def parse_args():
    parser = argparse.ArgumentParser(description='Image cleanup and analysis tool')
    parser.add_argument('input', help='Directory to scan for images')
    parser.add_argument('--api', 
                      choices=['openai', 'claude', 'gemini'],
                      default='gemini',
                      help='API provider to use for analysis (default: gemini)')
    parser.add_argument('--ui',
                      action='store_true',
                      help='Launch the interactive Rich UI instead of CLI output')
    return parser.parse_args()


def print_histogram(date_ext_counter):
    """Print histogram of images by year."""
    totals = [sum(cnts.values()) for cnts in date_ext_counter.values()]
    max_total = max(totals) if totals else 0
    BAR_WIDTH = 30
    for year, cnts in sorted(date_ext_counter.items()):
        total_y = sum(cnts.values())
        length = int(total_y / max_total * BAR_WIDTH) if max_total else 0
        bar = "█" * length
        print(f"{year:>4} | {bar} {total_y}")

def cli_run(root: Path, api_provider: str):
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

    engine.check_cache(api_provider)
    total = len(engine.image_paths)
    uncached = len(engine.uncached_images)
    cached = total - uncached
    print(f"\nCached images: {cached}/{total}")
    if uncached:
        print(f"{uncached} uncached images remain; press Enter to analyze one by one.")
        from image_cleanup_tool.api import ImageProcessor, get_client

        # Create API client for analysis
        api_client = get_client(api_provider)

        for path in engine.uncached_images:
            input(f"Press Enter to analyze {path.name} ({uncached - engine.uncached_images.index(path)} remaining)...")
            print(f"Analyzing {path}...")
            b64 = ImageProcessor.load_and_encode_image(str(path), 512)
            result, token_usage = api_client.analyze_image(b64)
            print(f"Result: {result.get('final_classification')}")
            if token_usage:
                print(f"Tokens used: {token_usage.get('total_tokens', 'N/A')}")
            engine.cache.set(path, result, api_provider)


def main():
    args = parse_args()
    root = Path(args.input)
    if not root.exists():
        print(f"Error: Path '{root}' does not exist.", file=sys.stderr)
        sys.exit(1)
    
    if args.ui:
        try:
            from image_cleanup_tool.ui import RichImageScannerUI
            RichImageScannerUI.run(root, args.api)
        except ImportError:
            print("Error: Rich UI dependencies are not installed.", file=sys.stderr)
            sys.exit(1)
    else:
        cli_run(root, args.api)

if __name__ == "__main__":
    main()
