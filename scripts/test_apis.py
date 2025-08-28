#!/usr/bin/env python3
"""
test_apis.py - Test script for AI API image analysis

This script demonstrates and compares all available AI APIs (OpenAI, Claude, Gemini)
for analyzing images with unified interface.

Usage:
    python scripts/test_apis.py path/to/image.jpg [--model MODEL]
"""

import os
import sys
import time
from pathlib import Path
from typing import Tuple, Dict

# Add the src directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from image_cleanup_tool.api import ImageProcessor, get_client

# API configuration
APIS = {
    'openai': {'key': 'OPENAI_API_KEY', 'model': 'GPT-5-nano'},
    'claude': {'key': 'ANTHROPIC_API_KEY', 'model': 'Claude Haiku'},
    'gemini': {'key': 'GEMINI_API_KEY', 'model': 'Gemini 1.5 Flash'}
}

def test_api(api_name: str, image_b64: str) -> tuple:
    """Test a single API and return (result, time, token_usage, error)"""
    try:
        client = get_client(api_name)
        start_time = time.time()
        result, token_usage = client.analyze_image(image_b64)
        return result, time.time() - start_time, token_usage, None
    except Exception as e:
        return None, 0, None, str(e)

def print_result(api_name: str, result: dict, processing_time: float, token_usage: dict = None):
    """Print formatted analysis result with token usage"""
    model_name = APIS[api_name]['model']
    classification = result.get('final_classification', {})

    print(f"🤖 {model_name} ({processing_time:.2f}s):")
    print(f"  📝 {result.get('description', 'N/A')[:80]}{'...' if len(result.get('description', '')) > 80 else ''}")
    print(f"  🎯 Keep: {classification.get('keep', 0)}% | Discard: {classification.get('discard', 0)}% | Unsure: {classification.get('unsure', 0)}%")
    print(f"  💭 {result.get('reasoning', 'N/A')[:60]}{'...' if len(result.get('reasoning', '')) > 60 else ''}")

    # Print token usage if available
    if token_usage:
        print(f"  🪙 Tokens: {token_usage.get('input_tokens', 'N/A')} input | {token_usage.get('output_tokens', 'N/A')} output | {token_usage.get('total_tokens', 'N/A')} total")
    else:
        print(f"  🪙 Tokens: Not available")

    print()

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_apis.py <image_path> [--model MODEL]")
        print("  --model: Test specific API (openai, claude, gemini) - default: all")
        sys.exit(1)

    image_path = sys.argv[1]
    target_model = None

    # Parse --model argument
    if '--model' in sys.argv:
        try:
            model_idx = sys.argv.index('--model')
            target_model = sys.argv[model_idx + 1]
            if target_model not in APIS:
                print(f"❌ Invalid model: {target_model}. Choose from: {', '.join(APIS.keys())}")
                sys.exit(1)
        except (IndexError, ValueError):
            print("❌ --model requires a value")
            sys.exit(1)

    if not Path(image_path).exists():
        print(f"❌ Image file not found: {image_path}")
        sys.exit(1)

    # Check API keys
    available_apis = []
    for api_name, config in APIS.items():
        if target_model and api_name != target_model:
            continue
        if os.getenv(config['key']):
            available_apis.append(api_name)
        else:
            print(f"⚠️  {config['key']} not set - skipping {config['model']}")

    if not available_apis:
        print("❌ No API keys configured. Set at least one:")
        for config in APIS.values():
            print(f"   export {config['key']}=your_key_here")
        sys.exit(1)

    # Load and encode image
    print(f"📸 Loading image: {image_path}")
    img_b64 = ImageProcessor.load_and_encode_image(image_path, 512)

    print(f"🤖 Testing {len(available_apis)} API{'s' if len(available_apis) != 1 else ''}")
    print("=" * 60)

    results = {}
    for api_name in available_apis:
        print(f"\n🔄 Testing {APIS[api_name]['model']}...")
        result, processing_time, token_usage, error = test_api(api_name, img_b64)

        if error:
            print(f"❌ {APIS[api_name]['model']} failed: {error}")
            results[api_name] = {'error': error}
        else:
            print(f"✅ {APIS[api_name]['model']} completed in {processing_time:.2f}s")
            results[api_name] = {'result': result, 'time': processing_time, 'tokens': token_usage}

    # Display results
    print("\n" + "=" * 60)
    print("📊 ANALYSIS RESULTS")
    print("=" * 60)

    for api_name, data in results.items():
        if 'result' in data:
            print_result(api_name, data['result'], data['time'], data.get('tokens'))

if __name__ == "__main__":
    main()
