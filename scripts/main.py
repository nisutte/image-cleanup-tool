#!/usr/bin/env python3
"""
Main CLI entry point for image cleanup tool.
"""
import sys
import argparse
import time
import json
from pathlib import Path
from typing import Dict, Any, List
import logging

from image_cleanup_tool.core.scan_engine import ImageScanEngine
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
    parser.add_argument('--benchmark',
                      action='store_true',
                      help='Run benchmark mode: test APIs on multiple images and check determinism')
    parser.add_argument('--test-image',
                      help='Single image file to test (for benchmark mode)')
    parser.add_argument('--limit',
                      type=int,
                      default=5,
                      help='Limit number of images for benchmark mode (default: 5)')

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


def benchmark_single_image(image_path: Path, api_providers: list[str], size: int, rounds: int = 3) -> Dict[str, Any]:
    """Benchmark a single image across multiple APIs and rounds."""
    from image_cleanup_tool.api import ImageProcessor, get_client
    
    results = {}
    
    for api_provider in api_providers:
        logger.info(f"Benchmarking {api_provider} on {image_path.name} ({rounds} rounds)...")
        
        try:
            api_client = get_client(api_provider)
            b64 = ImageProcessor.load_and_encode_image(str(image_path), size)
            
            round_results = []
            total_time = 0
            
            for round_num in range(rounds):
                start_time = time.time()
                result, token_usage = api_client.analyze_image(b64)
                end_time = time.time()
                
                round_time = end_time - start_time
                total_time += round_time
                
                round_results.append({
                    'round': round_num + 1,
                    'time': round_time,
                    'result': result,
                    'tokens': token_usage
                })
                
                decision = result.get('decision', 'unknown')
                keep_pct = result.get('confidence_keep', 0.0) * 100
                delete_pct = result.get('confidence_delete', 0.0) * 100
                unsure_pct = result.get('confidence_unsure', 0.0) * 100
                logger.info(f"  Round {round_num + 1}: {round_time:.2f}s - {decision} (K:{keep_pct:.0f}% D:{delete_pct:.0f}% U:{unsure_pct:.0f}%)")
            
            avg_time = total_time / rounds
            
            # Check determinism
            decisions = [r['result'].get('decision') for r in round_results]
            is_deterministic = len(set(decisions)) == 1
            
            # Extract probabilities from first round (they should be consistent)
            first_result = round_results[0]['result'] if round_results else {}
            probabilities = {
                'keep': first_result.get('confidence_keep', 0.0),
                'delete': first_result.get('confidence_delete', 0.0),
                'unsure': first_result.get('confidence_unsure', 0.0)
            }
            
            results[api_provider] = {
                'avg_time': avg_time,
                'total_time': total_time,
                'rounds': round_results,
                'is_deterministic': is_deterministic,
                'decisions': decisions,
                'probabilities': probabilities,
                'tokens': round_results[0]['tokens'] if round_results else {}
            }
            
        except Exception as e:
            logger.error(f"Error benchmarking {api_provider}: {e}")
            results[api_provider] = {'error': str(e)}
    
    return results


def benchmark_multiple_images(root: Path, api_providers: list[str], size: int, limit: int) -> Dict[str, Any]:
    """Benchmark multiple images from a directory."""
    engine = ImageScanEngine(root)
    engine.scan_files()
    
    # Get first N image files
    image_files = engine.image_paths[:limit]
    
    if not image_files:
        logger.error("No image files found in directory")
        return {}
    
    logger.info(f"Benchmarking {len(image_files)} images with {len(api_providers)} APIs...")
    
    all_results = {}
    
    for i, image_path in enumerate(image_files, 1):
        logger.info(f"\n--- Image {i}/{len(image_files)}: {image_path.name} ---")
        all_results[str(image_path)] = benchmark_single_image(image_path, api_providers, size, rounds=3)
    
    return all_results


def print_benchmark_summary(results: Dict[str, Any]):
    """Print a summary of benchmark results."""
    print("\n" + "="*60)
    print("BENCHMARK SUMMARY")
    print("="*60)
    
    if not results:
        print("No results to display.")
        return
    
    # Calculate averages across all images
    api_stats = {}
    
    for image_path, image_results in results.items():
        for api_name, api_result in image_results.items():
            if 'error' in api_result:
                continue
                
            if api_name not in api_stats:
                api_stats[api_name] = {
                    'total_time': 0,
                    'count': 0,
                    'deterministic_count': 0,
                    'total_images': 0
                }
            
            api_stats[api_name]['total_time'] += api_result['total_time']
            api_stats[api_name]['count'] += len(api_result['rounds'])
            api_stats[api_name]['total_images'] += 1
            
            if api_result['is_deterministic']:
                api_stats[api_name]['deterministic_count'] += 1
    
    # Print API comparison
    print("\nAPI Performance Comparison:")
    print("-" * 40)
    
    for api_name, stats in api_stats.items():
        avg_time = stats['total_time'] / stats['count'] if stats['count'] > 0 else 0
        determinism_pct = (stats['deterministic_count'] / stats['total_images']) * 100 if stats['total_images'] > 0 else 0
        
        print(f"{api_name.upper():<10} | Avg: {avg_time:.2f}s | Deterministic: {determinism_pct:.1f}%")
    
    # Print detailed results for each image
    print("\nDetailed Results:")
    print("-" * 40)
    
    for image_path, image_results in results.items():
        print(f"\n{Path(image_path).name}:")
        for api_name, api_result in image_results.items():
            if 'error' in api_result:
                print(f"  {api_name}: ERROR - {api_result['error']}")
            else:
                decisions = api_result['decisions']
                decision_str = " → ".join(decisions) if len(set(decisions)) > 1 else decisions[0]
                probabilities = api_result.get('probabilities', {})
                keep_pct = probabilities.get('keep', 0.0) * 100
                delete_pct = probabilities.get('delete', 0.0) * 100
                unsure_pct = probabilities.get('unsure', 0.0) * 100
                print(f"  {api_name}: {api_result['avg_time']:.2f}s - {decision_str}")
                print(f"    Probabilities: Keep {keep_pct:.1f}% | Delete {delete_pct:.1f}% | Unsure {unsure_pct:.1f}%")


def benchmark_mode(root: Path, api_providers: list[str], size: int, test_image: str = None, limit: int = 5):
    """Run benchmark mode."""
    if test_image:
        # Test single image
        image_path = Path(test_image)
        if not image_path.exists():
            logger.error(f"Test image not found: {image_path}")
            return
        
        logger.info(f"Benchmarking single image: {image_path}")
        results = {str(image_path): benchmark_single_image(image_path, api_providers, size, rounds=3)}
    else:
        # Test multiple images
        results = benchmark_multiple_images(root, api_providers, size, limit)
    
    print_benchmark_summary(results)


def main():
    args = parse_args()
    configure_logging(logging.DEBUG if args.debug else logging.INFO, enable_rich=args.ui)

    root = Path(args.input)
    if not root.exists():
        logger.error(f"Error: Path '{root}' does not exist.")
        sys.exit(1)

    # Parse API providers
    api_providers = parse_api_providers(args.api)
    logger.info(f"Using API provider(s): {', '.join(api_providers)}")

    if args.benchmark:
        benchmark_mode(root, api_providers, args.size, args.test_image, args.limit)
    elif args.ui:
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
