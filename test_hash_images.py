#!/usr/bin/env python3
"""
test_hash_images.py - example script to compute and print image hashes for files in a directory.
"""

import argparse
from pathlib import Path

from log_utils import configure_logging

from image_cache import compute_image_hash

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.heic', '.heif'}
exists = {}

def main():
    parser = argparse.ArgumentParser(
        description='Compute image hashes for all images under a directory.'
    )
    parser.add_argument(
        'input', nargs='?', default='images',
        help="Path to images directory (default: 'images')"
    )
    args = parser.parse_args()
    #configure_logging()
    root = Path(args.input)
    if not root.exists():
        parser.error(f"Path '{root}' does not exist")
    for path in root.rglob('*'):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            h = compute_image_hash(path, 0)
            # print(f"{path}: {h}")
            if h in exists:
                print(f"found double: {path} and {exists[h]} with hash {h}")
            else:
                exists[h] = path

if __name__ == '__main__':
    main()
