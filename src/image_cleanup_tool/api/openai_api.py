import os
import sys
import json
import argparse
import logging

from openai import OpenAI

from ..utils.log_utils import configure_logging, get_logger
from ..core.image_encoder import crop_and_resize_to_b64


logger = get_logger(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# === Configuration ===
# GPT-5-nano is the latest and most cost-effective model for image analysis
MODEL = "gpt-5-nano"

# === Prompt Template ===

PROMPT_TEMPLATE = """
You help sort personal photos. For each image, analyze it and return a structured JSON response.

Return a valid JSON object with the following structure:

{
  "description": "A clear 2-3 sentence description of what's in the image",
  "category_scores": {
    "blurry": 0-100,
    "meme": 0-100, 
    "screenshot": 0-100,
    "document": 0-100,
    "personal": 0-100,
    "non_personal": 0-100,
    "contains_faces": 0-100
  },
  "final_classification": {
    "keep": 0-100,
    "discard": 0-100,
    "unsure": 0-100
  },
  "reasoning": "Brief explanation of the classification decision (max 100 words)"
}

Scoring rules:
- All scores should be integers between 0-100
- final_classification should sum to 100
- High "keep" if personal, contains_faces, or meaningful content
- High "discard" if blurry, meme, non_personal, screenshot, or document
- Use "unsure" when the image quality or content is ambiguous

Example response:
{
  "description": "A clear photo of a family gathering at a park with 5 people smiling and enjoying a picnic.",
  "category_scores": {
    "blurry": 5,
    "meme": 0,
    "screenshot": 0,
    "document": 0,
    "personal": 95,
    "non_personal": 5,
    "contains_faces": 90
  },
  "final_classification": {
    "keep": 95,
    "discard": 5,
    "unsure": 0
  },
  "reasoning": "High personal value with clear faces and meaningful family moment"
}

IMPORTANT: Return ONLY a valid JSON object. No extra text or markdown!
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
            max_completion_tokens=2000,
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
