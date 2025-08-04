#!/usr/bin/env python3
"""
Runner script for the image cleanup tool.
This makes it easy to run the tool with uv: uv run python scripts/run.py <args>
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from scripts.main import main

if __name__ == "__main__":
    main() 