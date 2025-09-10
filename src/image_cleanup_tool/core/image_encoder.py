#!/usr/bin/env python3
"""
image_encoder.py: Crop images to centered square, resize to specified sizes, and output base64-encoded JPEG strings.

Supports input formats JPEG, PNG, and HEIC (requires pillow-heif). Operates on a single image or recursively on a directory.

Usage:
    python3 image_encoder.py <input_path> --output-dir <out_dir> [--sizes 512 256]

Dependencies:
    pip install pillow pillow-heif
"""

import argparse
import logging
import base64
import io
import os
import sys
from math import sqrt

from ..utils.log_utils import configure_logging, get_logger
logger = get_logger(__name__)

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

from PIL import Image

from typing import List, Dict


def process_image(path, sizes):
    """Open the image at `path`, resize to each dimension in `sizes`, and return dict of base64 strings."""
    try:
        img = Image.open(path)
    except Exception:
        logger.exception("Failed to open image '%s'", path)
        sys.exit(1)

    results = {}
    for size in sizes:
        w, h = img.size
        aspect_ratio = w / h
        new_w, new_h = sqrt(size**2 / aspect_ratio), sqrt(size**2 * aspect_ratio)

        smaller_side = min(new_w, new_h)
        smaller_side = int(round(smaller_side / 32) * 32)
        if new_w < new_h:
            new_w, new_h = smaller_side, int(round(smaller_side * aspect_ratio))
        else:
            new_h, new_w = smaller_side, int(round(smaller_side / aspect_ratio))

        try:
            resample_filter = Image.Resampling.LANCZOS
        except AttributeError:
            resample_filter = Image.LANCZOS

        img_resized = img.resize((new_w, new_h), resample=resample_filter)
        if img_resized.mode != "RGB":
            img_resized = img_resized.convert("RGB")
        buffer = io.BytesIO()
        img_resized.save(buffer, format="JPEG")
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        results[str(size)] = b64

    return results


def crop_and_resize_to_b64(path: str, sizes: List[int]) -> Dict[str, str]:
    """
    For a single image, crop to preserve aspect ratio and approximate the target pixel count for each requested size.
    Resize to each size in `sizes` and return a dict mapping size (as str) to base64-encoded JPEG.
    """
    return process_image(path, sizes)


def batch_images_to_b64(input_path: str, sizes: List[int]) -> Dict[str, Dict[str, str]]:
    """
    Recursively process a directory (or single file) and return a mapping from
    relative file path to a dict of size->base64 JPEG string.
    """
    allowed_exts = {'.jpg', '.jpeg', '.png', '.heic', '.heif'}
    results: Dict[str, Dict[str, str]] = {}
    if os.path.isdir(input_path):
        for root, _, files in os.walk(input_path):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                # Skip macOS metadata files
                if fname.startswith("._") or fname == ".DS_Store":
                    continue
                if ext not in allowed_exts:
                    continue
                full = os.path.join(root, fname)
                logger.debug("Processing image '%s'", full)
                rel = os.path.relpath(full, input_path)
                results[rel] = process_image(full, sizes)
    else:
        logger.debug("Processing single image '%s'", input_path)
        base = os.path.basename(input_path)
        results[base] = process_image(input_path, sizes)
    return results


def write_b64_files(b64_map: Dict[str, Dict[str, str]], output_dir: str) -> None:
    """
    Write a nested mapping (from batch_images_to_b64) to text files under output_dir.
    Each output file is named <basename>_<size>.txt, preserving subdirectory structure.
    """
    for rel, size_map in b64_map.items():
        base, _ = os.path.splitext(rel)
        subdir = os.path.dirname(rel)
        out_dir = output_dir if not subdir else os.path.join(output_dir, subdir)
        os.makedirs(out_dir, exist_ok=True)
        for size, b64 in size_map.items():
            out_path = os.path.join(out_dir, f"{base}_{size}.txt")
            logger.debug("Writing base64 to '%s'", out_path)
            with open(out_path, 'w') as f:
                f.write(b64)



def parse_args():
    # mainly used to test
    parser = argparse.ArgumentParser(
        description="Crop and resize input image(s) to specified square sizes and write base64-encoded JPEG strings to files."
    )
    parser.add_argument(
        "input",
        help="Path to the input image file or directory."
    )
    parser.add_argument(
        "-o", "--output-dir",
        required=True,
        help="Directory where output text files with base64 strings will be written."
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        default=[512],
        help="List of output square sizes (default: 512)."
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical", "none"],
        default="none",
        help="Set logging level (default: info; 'none' disables logging)"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.log_level.lower() != 'none':
        configure_logging(getattr(logging, args.log_level.upper()))
    # prepare output directory
    os.makedirs(args.output_dir, exist_ok=True)

    # process input and write outputs via helper functions
    b64_map = batch_images_to_b64(args.input, args.sizes)
    write_b64_files(b64_map, args.output_dir)


if __name__ == "__main__":
    main()

