#!/usr/bin/env python3
"""
file_operations.py: Core file operations for image cleanup.

Provides functions for moving images into buckets based on cached analysis decisions.
Used by both the CLI script and Rich UI.
"""

import json
import shlex
import subprocess
from pathlib import Path
from typing import Dict, Any, Iterable, List, Optional, Tuple


def load_entries(cache_path: Path) -> Iterable[Tuple[str, Dict[str, Any]]]:
    """Load entries from cache file."""
    data = json.loads(cache_path.read_text(encoding='utf-8'))
    entries = data.get('entries', {})
    for key, entry in entries.items():
        yield key, entry


def select_bucket(entry: Dict[str, Any], model_key: str, thresh_delete: float,
                  thresh_unsure: float, thresh_low_keep: float) -> Optional[str]:
    """Select bucket for an entry based on analysis results."""
    models = entry.get('models', {})
    model = models.get(model_key)
    if not model:
        return None
    result = model.get('result') or {}

    primary_category = result.get('primary_category')
    if primary_category == 'document':
        return 'documents'

    decision = (result.get('decision') or '').lower()
    c_keep = float(result.get('confidence_keep') or 0.0)
    c_unsure = float(result.get('confidence_unsure') or 0.0)
    c_delete = float(result.get('confidence_delete') or 0.0)

    if decision == 'delete' and c_delete >= thresh_delete:
        return 'to_delete'
    if decision == 'unsure' or c_unsure >= thresh_unsure:
        return 'unsure'
    if decision == 'keep' and c_keep < thresh_low_keep:
        return 'low_keep'
    elif decision == 'keep':
        return 'keep'
    else:
        return 'unknown'


def safe_destination(base_dir: Path, bucket: str, src_path: Path) -> Path:
    """Create a safe destination path for file operations."""
    bucket_dir = base_dir / bucket
    bucket_dir.mkdir(parents=True, exist_ok=True)
    dest_path = bucket_dir / src_path.name

    # If file exists, skip it (safest option)
    if dest_path.exists():
        return dest_path  # Return existing path, will be skipped
    
    return dest_path


def build_cp_command(src: Path, dest: Path) -> List[str]:
    """Build copy command."""
    return ['cp', str(src), str(dest)]


def build_move_command(src: Path, dest: Path) -> List[str]:
    """Build move command."""
    return ['mv', str(src), str(dest)]


def calculate_cleanup_plan(cache_path: Path, model_key: str, thresh_delete: float = 0.60,
                          thresh_unsure: float = 0.50, thresh_low_keep: float = 0.75) -> Dict[str, int]:
    """Calculate how many files will go to each bucket."""
    bucket_counts = {}
    
    for _, entry in load_entries(cache_path):
        src_path_str = entry.get('path')
        if not src_path_str:
            continue
        src = Path(src_path_str)
        if not src.exists():
            continue
            
        bucket = select_bucket(entry, model_key, thresh_delete, thresh_unsure, thresh_low_keep)
        if bucket and bucket != 'keep':
            bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    
    return bucket_counts


def execute_cleanup_phase_1(cache_path: Path, model_key: str, run_base: Path,
                           thresh_delete: float = 0.60, thresh_unsure: float = 0.50,
                           thresh_low_keep: float = 0.75, limit: Optional[int] = None,
                           execute: bool = False, verbose: bool = False) -> bool:
    """Execute Phase 1: Copy files to review buckets."""
    try:
        planned: List[Tuple[Path, Path, str]] = []  # (src, dest, bucket)

        for _, entry in load_entries(cache_path):
            src_path_str = entry.get('path')
            if not src_path_str:
                continue
            src = Path(src_path_str)
            if not src.exists():
                continue

            bucket = select_bucket(
                entry,
                model_key,
                thresh_delete,
                thresh_unsure,
                thresh_low_keep,
            )
            if not bucket or bucket == 'keep':
                continue

            dest = safe_destination(run_base, bucket, src)
            planned.append((src, dest, bucket))

            if limit is not None and len(planned) >= limit:
                break

        if not planned:
            if verbose:
                print('No files to move based on current thresholds and model key.')
            return False

        # Ensure destination parent folders exist
        for _, dest, _ in planned:
            dest.parent.mkdir(parents=True, exist_ok=True)

        copied_count = 0
        skipped_count = 0

        for src, dest, bucket in planned:
            # Skip if destination already exists
            if dest.exists():
                if verbose:
                    print(f"SKIP: {src} -> {dest} (already exists)")
                skipped_count += 1
                continue

            cmd = build_cp_command(src, dest)
            if verbose:
                print(' '.join(shlex.quote(c) for c in cmd))
                print(f"  -> {dest}")
            if execute:
                subprocess.run(cmd, check=True)
                copied_count += 1

        if verbose:
            print(f"\nPhase 1 Summary:")
            print(f"  Copied: {copied_count} files")
            print(f"  Skipped: {skipped_count} files (already exist)")
            if not execute:
                print("  Dry run only. Re-run with execute=True to copy files.")

        return True

    except Exception as e:
        if verbose:
            print(f"Error in Phase 1: {e}")
        return False


def execute_cleanup_phase_2(run_base: Path, execute: bool = False, verbose: bool = False) -> bool:
    """Execute Phase 2: Move remaining files to final deletion."""
    try:
        final_dir = run_base / 'final_deletion'
        final_dir.mkdir(parents=True, exist_ok=True)

        actions: List[Tuple[Path, Path]] = []  # (copy, final_dest)
        buckets_for_finalize = {'to_delete', 'unsure', 'low_keep', 'documents', 'unknown'}
        
        # Scan bucket directories directly
        for bucket in buckets_for_finalize:
            bucket_dir = run_base / bucket
            if not bucket_dir.exists():
                continue
                
            for file_path in bucket_dir.iterdir():
                if not file_path.is_file():
                    continue
                    
                # Create final destination path
                final_dest = final_dir / file_path.name
                
                # Handle name collisions
                if final_dest.exists():
                    stem, suffix = final_dest.stem, final_dest.suffix
                    counter = 1
                    while final_dest.exists():
                        final_dest = final_dir / f"{stem}_{counter}{suffix}"
                        counter += 1
                
                actions.append((file_path, final_dest))

        if not actions:
            if verbose:
                print('No items to finalize.')
            return False

        moved_count = 0
        for copy, final_dest in actions:
            mv_cmd = build_move_command(copy, final_dest)
            if verbose:
                print(' '.join(shlex.quote(c) for c in mv_cmd))
                print(f"  -> moved {copy} to {final_dest}")
            if execute:
                subprocess.run(mv_cmd, check=True)
                moved_count += 1

        if verbose:
            print(f"\nPhase 2 Summary:")
            print(f"  Moved: {moved_count} files to final_deletion/")
            if not execute:
                print("  Dry run only. Re-run with execute=True to move files.")
        
        return True

    except Exception as e:
        if verbose:
            print(f"Error in Phase 2: {e}")
        return False


def count_remaining_files(run_base: Path) -> Dict[str, int]:
    """Count remaining files in review buckets."""
    remaining_counts = {}
    buckets = ['to_delete', 'unsure', 'low_keep', 'documents', 'unknown']
    
    for bucket in buckets:
        bucket_dir = run_base / bucket
        if bucket_dir.exists():
            count = len([f for f in bucket_dir.iterdir() if f.is_file()])
            if count > 0:
                remaining_counts[bucket] = count
    
    return remaining_counts