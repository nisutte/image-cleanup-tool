#!/usr/bin/env python3
"""
Web UI for comparing LLM image classification results.
Serves a simple web interface to browse and compare model scores.
"""

import os
import json
from flask import Flask, render_template, jsonify, send_from_directory
from pathlib import Path

app = Flask(__name__,
           template_folder='../templates',
           static_folder='../static')

# Path to the cache file
CACHE_FILE = Path(__file__).parent.parent / '.image_analysis_cache.json'

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
        # This would need to be implemented with proper async handling
        # For now, return a placeholder response
        return jsonify({"status": "not_implemented", "message": f"Analysis for {model} with size {size} not yet implemented"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/images/<path:filename>')
def get_image(filename):
    """Serve images from the images directory."""
    images_dir = Path(__file__).parent.parent / 'images'

    # Remove 'images/' prefix if present in filename
    if filename.startswith('images/'):
        filename = filename[7:]  # Remove 'images/' prefix

    return send_from_directory(images_dir, filename)

if __name__ == '__main__':
    print("🚀 Starting Image Classification Comparison Web UI")
    print("📊 Visit: http://localhost:3000")
    print("🔄 Loading cache data...")
    app.run(debug=True, host='0.0.0.0', port=3000)
