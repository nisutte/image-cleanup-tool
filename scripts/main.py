#!/usr/bin/env python3
"""
Main CLI entry point for image cleanup tool.
"""
import sys
import argparse
from pathlib import Path
import logging

from image_cleanup_tool.core.backbone import ImageScanEngine
from image_cleanup_tool.utils.log_utils import get_logger, configure_logging

logger = get_logger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description='Image cleanup and analysis tool')
    parser.add_argument('input', help='Directory to scan for images')
    parser.add_argument('--api',
                      default='gemini',
                      help='API provider(s) to use for analysis. Can be: openai, claude, gemini, all, or comma-separated list (default: gemini)')
    parser.add_argument('--size',
                      type=int,
                      default=512,
                      choices=[256, 512, 768, 1024],
                      help='Image size for analysis (default: 512)')
    parser.add_argument('--ui',
                      action='store_true',
                      help='Launch the interactive Rich UI instead of CLI output')

    parser.add_argument('--debug',
                      action='store_true',
                      help='Enable debug mode')
    return parser.parse_args()


def parse_api_providers(api_arg: str) -> list[str]:
    """Parse API provider argument and return list of providers."""
    available_apis = ['openai', 'claude', 'gemini']

    if api_arg.lower() == 'all':
        return available_apis

    # Split by comma and strip whitespace
    providers = [p.strip().lower() for p in api_arg.split(',')]

    # Validate providers
    invalid_providers = [p for p in providers if p not in available_apis]
    if invalid_providers:
        print(f"Error: Invalid API provider(s): {', '.join(invalid_providers)}", file=sys.stderr)
        print(f"Available providers: {', '.join(available_apis)}", file=sys.stderr)
        sys.exit(1)

    return providers


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

def cli_run(root: Path, api_providers: list[str], size: int):
    logger.info(f"Scanning files under {root}...")
    logger.info(f"Using image size: {size}x{size}")
    engine = ImageScanEngine(root)
    engine.calculate_total()
    engine.scan_files()
    logger.info("\nImage count by extension:")
    for ext, cnt in sorted(engine.ext_counter.items()):
        logger.info(f"  {ext}: {cnt}")
    print(f"  Non-image files: {engine.non_image_count}")
    logger.info("\nCapture date histogram:")
    print_histogram(engine.date_ext_counter)

    # Process each API provider
    for api_provider in api_providers:
        logger.info(f"\n=== Processing with {api_provider.upper()} ===")

        engine.check_cache(api_provider, size)
        total = len(engine.image_paths)
        uncached = len(engine.uncached_images)
        cached = total - uncached
        logger.info(f"Cached images: {cached}/{total}")

        if uncached:
            from image_cleanup_tool.api import ImageProcessor, get_client

            # Create API client for analysis
            api_client = get_client(api_provider)

            for path in engine.uncached_images:
                logger.info(f"Analyzing {path} with {api_provider}...")
                b64 = ImageProcessor.load_and_encode_image(str(path), size)
                result, token_usage = api_client.analyze_image(b64)
                logger.info(f"Result: {result.get('decision')}")
                if token_usage:
                    print(f"Input and Output Tokens used: {token_usage.get('input_tokens', 'N/A')} and {token_usage.get('output_tokens', 'N/A')}")
                engine.cache.set(path, result, api_provider, size)


def main():
    args = parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO)

    root = Path(args.input)
    if not root.exists():
        logger.error(f"Error: Path '{root}' does not exist.")
        sys.exit(1)

    # Parse API providers
    api_providers = parse_api_providers(args.api)
    logger.info(f"Using API provider(s): {', '.join(api_providers)}")

    if args.ui:
        try:
            from image_cleanup_tool.ui import RichImageScannerUI
            RichImageScannerUI.run(root, api_providers, args.size)
        except ImportError:
            logger.error("Error: Rich UI dependencies are not installed.")
            sys.exit(1)
    else:
        cli_run(root, api_providers, args.size)

if __name__ == "__main__":
    main()
