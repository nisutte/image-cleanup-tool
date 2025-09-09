#!/usr/bin/env python3
"""
Web UI for comparing LLM image classification results.
Serves a simple web interface to browse and compare model scores.
"""

import os
import json
import argparse
from flask import Flask, render_template, jsonify, send_from_directory
from pathlib import Path

app = Flask(__name__,
           template_folder='../templates',
           static_folder='../static')

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Web UI for comparing LLM image classification results'
    )
    parser.add_argument(
        '--cache-file',
        default='.image_analysis_cache.json',
        help='Path to the cache file (default: .image_analysis_cache.json)'
    )
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Host to bind to (default: 127.0.0.1)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=3000,
        help='Port to bind to (default: 3000)'
    )
    return parser.parse_args()

# Parse command line arguments
args = parse_arguments()

# Path to the cache file
CACHE_FILE = Path(args.cache_file)

@app.route('/')
def index():
    """Serve the main UI page."""
    return render_template('index.html')

@app.route('/api/cache')
def get_cache():
    """API endpoint to get the analysis cache data."""
    try:
        with open(CACHE_FILE, 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except FileNotFoundError:
        return jsonify({"error": "Cache file not found"}), 404
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid cache file format"}), 500

@app.route('/api/sizes')
def get_sizes():
    """API endpoint to get available image sizes."""
    sizes = [256, 512, 768, 1024]  # Common sizes for vision models
    return jsonify({"sizes": sizes, "default": 512})

@app.route('/api/analyze/<model>/<int:size>', methods=['POST'])
def analyze_with_size(model, size):
    """API endpoint to trigger analysis for a specific model and size."""
    try:
        return jsonify({"status": "not_implemented", "message": f"Analysis for {model} with size {size} not yet implemented"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/images/<path:subpath>')
def get_image(subpath):
    """Serve images using the full path from the cache."""
    try:
        full_path = Path('/' + subpath)
        return send_from_directory(full_path.parent, full_path.name)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    print("🚀 Starting Image Classification Comparison Web UI")
    print(f"📊 Visit: http://{args.host}:{args.port}")
    print(f"🔄 Using cache file: {CACHE_FILE}")
    print("🔄 Loading cache data...")
    app.run(debug=True, host=args.host, port=args.port)
