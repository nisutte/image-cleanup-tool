#!/usr/bin/env python3
"""
Move images into buckets based on cached analysis decisions.

Buckets (under a parent run folder):
- to_delete/
- unsure/
- low_keep/
- documents/

Uses the cache produced by src/image_cleanup_tool/core/image_cache.py
and executes shell `mv` (dry-run by default, require --yes to execute).
"""

import argparse
import sys
from pathlib import Path

# Add src to path to import core modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from image_cleanup_tool.core.file_operations import (
    execute_cleanup_phase_1,
    execute_cleanup_phase_2,
)


DEFAULT_CACHE = Path('.image_analysis_cache.json')
DEFAULT_MODEL_KEY = 'gemini_512'
DEFAULT_RUN_NAME = 'image_cleanup_moves'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Move images into buckets based on cached analysis decisions.'
    )
    parser.add_argument('--cache', type=Path, default=DEFAULT_CACHE,
                        help='Path to cache JSON (default: .image_analysis_cache.json)')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--model-key', default=DEFAULT_MODEL_KEY,
                       help='Model+size key, e.g. gemini_512 (default: gemini_512)')
    group.add_argument('--model', help='Model name, e.g. gemini')
    parser.add_argument('--size', type=int, default=512,
                        help='Image size used in analysis when using --model (default: 512)')
    parser.add_argument('--output-dir', type=Path, default=Path('.'),
                        help='Directory where the parent run folder will be created (default: cwd)')
    parser.add_argument('--run-name', default=DEFAULT_RUN_NAME,
                        help='Name of the parent folder that will contain the buckets')

    parser.add_argument('--thresh-delete', type=float, default=0.60,
                        help='Minimum confidence_delete to move into to_delete (default: 0.70)')
    parser.add_argument('--thresh-unsure', type=float, default=0.50,
                        help='Minimum confidence_unsure to move into unsure (default: 0.50). Also used if decision==unsure')
    parser.add_argument('--thresh-low-keep', type=float, default=0.75,
                        help='If keep and confidence_keep below this, move to low_keep (default: 0.75)')

    parser.add_argument('--preserve-tree', action='store_true',
                        help='Preserve source relative directory tree inside each bucket (default: off)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit number of files to move (default: no limit)')
    parser.add_argument('--on-collision', choices=['rename', 'skip', 'overwrite'], default='skip',
                        help='What to do when destination file exists (default: skip)')
    parser.add_argument('--finalize', action='store_true',
                        help='Finalize step: for files still in to_delete/, move ORIGINALS to final_deletion and remove the copies if both exist')
    parser.add_argument('--yes', action='store_true',
                        help='Actually execute copy/move operations')
    parser.add_argument('--verbose', action='store_true', help='Verbose logging')

    args = parser.parse_args()

    if args.model and not args.model_key:
        args.model_key = f"{args.model}_{args.size}"

    return args




def main() -> None:
    args = parse_args()

    if not args.cache.is_file():
        raise SystemExit(f"Cache not found: {args.cache}")

    run_base = (args.output_dir / args.run_name).resolve()
    run_base.mkdir(parents=True, exist_ok=True)

    # Finalize mode: move originals still present in review buckets and remove their copies
    if args.finalize:
        success = execute_cleanup_phase_2(run_base, execute=args.yes, verbose=args.verbose)
        if not success:
            return
        return

    # Staging mode: copy files into buckets, write manifest, and update cache with copied_path
    success = execute_cleanup_phase_1(
        cache_path=args.cache,
        model_key=args.model_key,
        run_base=run_base,
        thresh_delete=args.thresh_delete,
        thresh_unsure=args.thresh_unsure,
        thresh_low_keep=args.thresh_low_keep,
        preserve_tree=args.preserve_tree,
        on_collision=args.on_collision,
        limit=args.limit,
        execute=args.yes,
        verbose=args.verbose
    )
    
    if not success:
        return



if __name__ == '__main__':
    main()


