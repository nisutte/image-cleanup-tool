import os
import sys
import json
import argparse
import logging

from openai import OpenAI

from log_utils import configure_logging, get_logger
from image_encoder import crop_and_resize_to_b64


logger = get_logger(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# === Configuration ===
# 4.1 nano is crazy cheap for images, 0,000063 $ for a 512x512, so 63 cents for 10'000 images
# MODEL = "gpt-4o-mini"
MODEL = "gpt-4.1-nano"

# === Prompt Template ===

PROMPT_TEMPLATE = """
You help sort personal photos. For each image:

1. Describe it in 3 sentences.
2. Return a valid JSON object with the following structure, deciding if the image is worth keeping or not:

{
  "description": "...",
  "category_scores": {
    "blurry": %, "meme": %, "screenshot": %, "document": %, 
    "personal": %, "non_personal": %, "contains_faces": %
  },
  "final_classification": {
    "keep": %, "discard": %, "unsure": %
  },
}

Scoring rules:
- In general, keep if it is worth keeping, discard otherwise and unsure if unsure. Classification should sum up to 100.
- Also: High "keep" if personal or contains_faces.
- High "discard" if blurry, meme, non_personal, screenshot, or document.

IMPORTANT: Return ONLY a JSON object. No extra text or markdown!
""".strip()


def load_and_encode_image(path: str, size: int) -> str:
    """
    Crop and resize image to size x size and return its base64-encoded JPEG string.
    """
    encoded = crop_and_resize_to_b64(path, [size])
    return encoded.get(str(size), "")

def analyze_image(image_b64: str) -> dict:
    """
    Send the image (base64) to the GPT vision model and return parsed JSON result.
    Raises RuntimeError or ValueError on failure.
    """
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT_TEMPLATE},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}", "detail": "low"}}
            ],
        }
    ]
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=300,
            temperature=0.0,
        )
    except Exception as err:
        logger.error("API request failed: %s", err)
        raise RuntimeError(f"OpenAI API error: {err}")
    content = response.choices[0].message.content
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.error("Failed to parse JSON response: %s", content)
        raise ValueError(f"Invalid JSON response: {content}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze a personal photo using OpenAI GPT-4o vision.")
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
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    img_b64 = load_and_encode_image(args.image_path, args.size)
    try:
        result = analyze_image(img_b64)
        print(json.dumps(result, indent=2))
    except Exception as err:
        logger.error("Analysis failed: %s", err)
        sys.exit(1)
