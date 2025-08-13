#!/usr/bin/env python3
"""
test_claude_api.py - Test script for Claude API image analysis

This script demonstrates how to use the Claude Haiku API for analyzing images.
It provides a simple comparison between OpenAI and Claude APIs.

Usage:
    python scripts/test_claude_api.py path/to/image.jpg
"""

import os
import sys
import json
import time
from pathlib import Path

# Add the src directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from image_cleanup_tool.api.claude_api import analyze_image as claude_analyze_image, load_and_encode_image
from image_cleanup_tool.api.openai_api import analyze_image as openai_analyze_image

def test_claude_api(image_path: str, size: int = 512):
    """
    Test the Claude API with a single image.
    
    Args:
        image_path: Path to the image file
        size: Image size for processing
    """
    print(f"Testing Claude API with image: {image_path}")
    print("=" * 60)
    
    # Check API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("❌ ANTHROPIC_API_KEY environment variable not set")
        print("Please set it with: export ANTHROPIC_API_KEY=your_api_key")
        return
    
    # Load and encode image
    print("📸 Loading and encoding image...")
    img_b64 = load_and_encode_image(image_path, size)
    
    # Analyze with Claude
    print("🤖 Analyzing with Claude Haiku...")
    start_time = time.time()
    
    try:
        result = claude_analyze_image(img_b64)
        processing_time = time.time() - start_time
        
        print(f"✅ Analysis completed in {processing_time:.2f} seconds")
        print("\n📊 Results:")
        print(json.dumps(result, indent=2))
        
        # Show classification summary
        classification = result.get('final_classification', {})
        print(f"\n🎯 Classification Summary:")
        print(f"  Keep: {classification.get('keep', 0)}%")
        print(f"  Discard: {classification.get('discard', 0)}%")
        print(f"  Unsure: {classification.get('unsure', 0)}%")
        
    except Exception as e:
        print(f"❌ Claude API analysis failed: {e}")

def compare_apis(image_path: str, size: int = 512):
    """
    Compare OpenAI and Claude APIs for the same image.
    
    Args:
        image_path: Path to the image file
        size: Image size for processing
    """
    print(f"Comparing OpenAI vs Claude APIs with image: {image_path}")
    print("=" * 80)
    
    # Check API keys
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY environment variable not set")
        return
    
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("❌ ANTHROPIC_API_KEY environment variable not set")
        return
    
    # Load and encode image once
    print("📸 Loading and encoding image...")
    img_b64 = load_and_encode_image(image_path, size)
    
    results = {}
    
    # Test OpenAI
    print("\n🤖 Testing OpenAI GPT-5-nano...")
    start_time = time.time()
    try:
        openai_result = openai_analyze_image(img_b64)
        openai_time = time.time() - start_time
        results['openai'] = {'result': openai_result, 'time': openai_time}
        print(f"✅ OpenAI completed in {openai_time:.2f} seconds")
    except Exception as e:
        print(f"❌ OpenAI failed: {e}")
        results['openai'] = {'error': str(e)}
    
    # Test Claude
    print("\n🤖 Testing Claude Haiku...")
    start_time = time.time()
    try:
        claude_result = claude_analyze_image(img_b64)
        claude_time = time.time() - start_time
        results['claude'] = {'result': claude_result, 'time': claude_time}
        print(f"✅ Claude completed in {claude_time:.2f} seconds")
    except Exception as e:
        print(f"❌ Claude failed: {e}")
        results['claude'] = {'error': str(e)}
    
    # Compare results
    print("\n" + "=" * 80)
    print("📊 COMPARISON RESULTS")
    print("=" * 80)
    
    if 'openai' in results and 'result' in results['openai']:
        openai_result = results['openai']['result']
        openai_class = openai_result.get('final_classification', {})
        print(f"🤖 OpenAI GPT-5-nano ({results['openai']['time']:.2f}s):")
        print(f"  📝 Description: {openai_result.get('description', 'N/A')}")
        print(f"  🎯 Classification: Keep: {openai_class.get('keep', 0)}%, Discard: {openai_class.get('discard', 0)}%, Unsure: {openai_class.get('unsure', 0)}%")
        print(f"  💭 Reasoning: {openai_result.get('reasoning', 'N/A')}")
        print()
    
    if 'claude' in results and 'result' in results['claude']:
        claude_result = results['claude']['result']
        claude_class = claude_result.get('final_classification', {})
        print(f"🤖 Claude Haiku ({results['claude']['time']:.2f}s):")
        print(f"  📝 Description: {claude_result.get('description', 'N/A')}")
        print(f"  🎯 Classification: Keep: {claude_class.get('keep', 0)}%, Discard: {claude_class.get('discard', 0)}%, Unsure: {claude_class.get('unsure', 0)}%")
        print(f"  💭 Reasoning: {claude_result.get('reasoning', 'N/A')}")
        print()

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_claude_api.py <image_path> [--compare]")
        print("  --compare: Compare OpenAI and Claude APIs")
        sys.exit(1)
    
    image_path = sys.argv[1]
    compare_mode = "--compare" in sys.argv
    
    if not Path(image_path).exists():
        print(f"❌ Image file not found: {image_path}")
        sys.exit(1)
    
    if compare_mode:
        compare_apis(image_path)
    else:
        test_claude_api(image_path)

if __name__ == "__main__":
    main()
