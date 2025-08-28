import os
import sys
import json
import argparse
import logging
import base64

import anthropic

from ..utils.log_utils import configure_logging, get_logger
from ..core.image_encoder import crop_and_resize_to_b64


logger = get_logger(__name__)
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# === Configuration ===
# Claude Haiku is cost-effective for image analysis
MODEL = "claude-3-haiku-20240307"

# === Prompt Template ===
from .prompt import PROMPT_TEMPLATE


def load_and_encode_image(path: str, size: int) -> str:
    """
    Crop and resize image to size x size and return its base64-encoded JPEG string.
    """
    encoded = crop_and_resize_to_b64(path, [size])
    return encoded.get(str(size), "")

def analyze_image(image_b64: str) -> dict:
    """
    Send the image (base64) to the Claude Haiku vision model and return parsed JSON result.
    Raises RuntimeError or ValueError on failure.
    """
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=400,
            temperature=0.1,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": PROMPT_TEMPLATE
                        },
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_b64
                            }
                        }
                    ]
                }
            ]
        )
    except Exception as err:
        logger.error("API request failed: %s", err)
        raise RuntimeError(f"Claude API error: {err}")
    
    content = response.content[0].text
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.error("Failed to parse JSON response: %s", content)
        raise ValueError(f"Invalid JSON response: {content}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze a personal photo using Claude Haiku vision.")
    parser.add_argument("image_path", help="Path to the image file to analyze")
    parser.add_argument("size", nargs="?", type=int, default=512, help="Optional image size to crop/resize (default: 512)")
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical", "none"],
        default="none",
        help="Set logging level ('none' to disable)"
    )
    args = parser.parse_args()
    if args.log_level.lower() != "none":
        configure_logging(getattr(logging, args.log_level.upper()))
    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)
    img_b64 = load_and_encode_image(args.image_path, args.size)
    try:
        result = analyze_image(img_b64)
        print(json.dumps(result, indent=2))
    except Exception as err:
        logger.error("Analysis failed: %s", err)
        sys.exit(1)
