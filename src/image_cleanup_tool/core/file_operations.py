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


def safe_destination(base_dir: Path, bucket: str, src_path: Path, preserve_tree: bool,
                     on_collision: str) -> Path:
    """Create a safe destination path for file operations."""
    bucket_dir = base_dir / bucket
    bucket_dir.mkdir(parents=True, exist_ok=True)

    if preserve_tree:
        # Use the source path relative to its drive root, but since we may not
        # know the intended root, just replicate parent folders under the bucket.
        rel_parts = src_path.parent.parts[-3:]  # keep last 3 dirs to avoid deep trees
        dest_dir = bucket_dir.joinpath(*rel_parts)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / src_path.name
    else:
        dest_path = bucket_dir / src_path.name

    if dest_path.exists():
        if on_collision == 'skip':
            return dest_path
        if on_collision == 'overwrite':
            return dest_path
        # rename: append numeric suffix
        stem = dest_path.stem
        suffix = dest_path.suffix
        counter = 1
        while dest_path.exists():
            dest_path = dest_path.with_name(f"{stem}_{counter}{suffix}")
            counter += 1
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
                           thresh_low_keep: float = 0.75, preserve_tree: bool = False,
                           on_collision: str = 'skip', limit: Optional[int] = None,
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

            dest = safe_destination(
                run_base, bucket, src, preserve_tree, on_collision
            )
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

        # Load existing manifest
        manifest_path = run_base / 'manifest.json'
        manifest: Dict[str, str] = {}
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            except Exception:
                manifest = {}

        # Load cache to update copied_path
        cache_data = json.loads(cache_path.read_text(encoding='utf-8'))
        cache_entries = cache_data.get('entries', {})

        for src, dest, bucket in planned:
            cmd = build_cp_command(src, dest)
            if verbose:
                print(' '.join(shlex.quote(c) for c in cmd))
                print(f"  -> {dest}")
            if execute:
                subprocess.run(cmd, check=True)
            # Record manifest mapping
            manifest[str(src)] = str(dest)

        # Update cache with copied_path for entries we processed
        for key, entry in cache_entries.items():
            orig_path = entry.get('path')
            if not orig_path:
                continue
            copied = manifest.get(orig_path)
            if copied:
                # Store per model_key copied target path under models[model_key]['copied_path']
                models = entry.get('models') or {}
                model = models.get(model_key)
                if model is not None:
                    model.setdefault('copied_path', str(copied))

        if execute:
            cache_path.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2), encoding='utf-8')
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        elif verbose:
            print("\nDry run only. Re-run with execute=True to write manifest and update cache.")
            print(f"Would write manifest to: {manifest_path}")

        return True

    except Exception as e:
        if verbose:
            print(f"Error in Phase 1: {e}")
        return False


def execute_cleanup_phase_2(run_base: Path, execute: bool = False, verbose: bool = False) -> bool:
    """Execute Phase 2: Move remaining files to final deletion."""
    try:
        manifest_path = run_base / 'manifest.json'
        manifest: Dict[str, str] = {}
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        else:
            if verbose:
                print('No manifest found for finalize; nothing to do.')
            return False

        final_dir = run_base / 'final_deletion'
        final_dir.mkdir(parents=True, exist_ok=True)

        actions: List[Tuple[Path, Path, Path]] = []  # (orig, copy, final_dest)
        buckets_for_finalize = {'to_delete', 'unsure', 'low_keep', 'documents', 'unknown'}
        for orig_str, copy_str in manifest.items():
            orig = Path(orig_str)
            copy = Path(copy_str)
            if not copy.exists():
                continue
            # Only finalize items whose copy is still inside review buckets
            try:
                copy_rel = copy.relative_to(run_base)
            except Exception:
                continue
            if not (copy_rel.parts and copy_rel.parts[0] in buckets_for_finalize):
                continue
            if not orig.exists():
                continue
            final_dest = final_dir / orig.name
            if final_dest.exists():
                # add numeric suffix to avoid overwriting
                stem, suffix = final_dest.stem, final_dest.suffix
                counter = 1
                while final_dest.exists():
                    final_dest = final_dir / f"{stem}_{counter}{suffix}"
                    counter += 1
            actions.append((orig, copy, final_dest))

        if not actions:
            if verbose:
                print('No items to finalize.')
            return False

        for orig, copy, final_dest in actions:
            mv_cmd = build_move_command(orig, final_dest)
            rm_copy_cmd = ['rm', str(copy)]
            if verbose:
                print(' '.join(shlex.quote(c) for c in mv_cmd))
                print(' '.join(shlex.quote(c) for c in rm_copy_cmd))
                print(f"  -> moved original to {final_dest} and removed copy {copy}")
            if execute:
                subprocess.run(mv_cmd, check=True)
                subprocess.run(rm_copy_cmd, check=True)

        if not execute and verbose:
            print("\nFinalize dry run only. Re-run with execute=True to execute.")
        
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
            count = len(list(bucket_dir.iterdir()))
            if count > 0:
                remaining_counts[bucket] = count
    
    return remaining_counts
