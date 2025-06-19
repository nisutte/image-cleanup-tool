#!/usr/bin/env python3
"""
resize_and_encode.py: Crop images to centered square, resize to specified sizes, and output base64-encoded JPEG strings.

Supports input formats JPEG, PNG, and HEIC (requires pillow-heif). Operates on a single image or recursively on a directory.

Usage:
    python3 resize_and_encode.py <input_path> --output-dir <out_dir> [--sizes 512 256]

Dependencies:
    pip install pillow pillow-heif
"""

import argparse
import base64
import io
import os
import sys

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

from PIL import Image


def process_image(path, sizes):
    """Open the image at `path`, resize to each dimension in `sizes`, and return dict of base64 strings."""
    try:
        img = Image.open(path)
    except Exception as e:
        print(f"Error opening image '{path}': {e}", file=sys.stderr)
        sys.exit(1)

    # Crop to centered square to preserve aspect ratio
    w, h = img.size
    min_side = min(w, h)
    left = (w - min_side) // 2
    top = (h - min_side) // 2
    img = img.crop((left, top, left + min_side, top + min_side))

    try:
        resample_filter = Image.Resampling.LANCZOS
    except AttributeError:
        resample_filter = Image.LANCZOS

    results = {}
    for size in sizes:
        img_resized = img.resize((size, size), resample=resample_filter)
        buffer = io.BytesIO()
        img_resized.save(buffer, format="JPEG")
        b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
        results[str(size)] = b64

    return results


def parse_args():
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
        default=[512, 256],
        help="List of output square sizes (default: 512 256)."
    )
    return parser.parse_args()


def main():
    args = parse_args()
    # prepare output directory
    os.makedirs(args.output_dir, exist_ok=True)

    # process a directory recursively or a single file
    allowed_exts = {'.jpg', '.jpeg', '.png', '.heic', '.heif'}
    if os.path.isdir(args.input):
        for root, _, files in os.walk(args.input):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in allowed_exts:
                    continue
                full = os.path.join(root, fname)
                rel_dir = os.path.relpath(root, args.input)
                out_dir = os.path.join(args.output_dir, rel_dir)
                os.makedirs(out_dir, exist_ok=True)
                results = process_image(full, args.sizes)
                base = os.path.splitext(fname)[0]
                for size, b64 in results.items():
                    out_path = os.path.join(out_dir, f"{base}_{size}.txt")
                    with open(out_path, 'w') as f:
                        f.write(b64)
    else:
        results = process_image(args.input, args.sizes)
        base = os.path.splitext(os.path.basename(args.input))[0]
        for size, b64 in results.items():
            out_path = os.path.join(args.output_dir, f"{base}_{size}.txt")
            with open(out_path, 'w') as f:
                f.write(b64)


if __name__ == "__main__":
    main()

