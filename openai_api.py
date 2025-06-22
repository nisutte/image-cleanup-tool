from openai import OpenAI
import tiktoken
import json
import argparse
import os
import logging

from log_utils import configure_logging, get_logger
from image_encoder import crop_and_resize_to_b64


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logger = get_logger(__name__)

# === Configuration ===
# 4.1 nano is crazy cheap for images, 0,000063 $ for a 512x512, so 63 cents for 10'000 images
# MODEL = "gpt-4o-mini"
MODEL = "gpt-4.1-nano"

# === Prompt Template ===

PROMPT_TEMPLATE = """
You help sort personal photos. For each image:

1. Describe it in **3 sentences**.
2. Return a **valid JSON**:

{
  "description": "...",
  "category_scores": {
    "blurry": %, "meme": %, "screenshot": %, "document": %, 
    "personal": %, "non_personal": %, "contains_faces": %
  },
  "final_classification": {
    "keep": %, "discard": %, "unsure": %
  }
}

Scoring rules:
- High "keep" if personal or contains_faces.
- High "discard" if blurry, meme, non_personal, screenshot, or document.
- Use "unsure" if uncertain.

Output JSON only. No explanations.
""".strip()

# === Utility Functions ===

def load_and_encode_image(path, size):
    """Crop and resize image to sizexsize and return its base64-encoded JPEG string."""
    return crop_and_resize_to_b64(path, [size])[str(size)]

# === Main Function ===

def analyze_image(image_b64):
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": PROMPT_TEMPLATE
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_b64}",
                        "detail": "low",
                    }
                }
            ],
        }
    ]

    response = client.chat.completions.create(model=MODEL,
        messages=messages,
        max_tokens=300,
        temperature=0.1,
    )

    output_content = response.choices[0].message.content

    try:
        result = json.loads(output_content)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(output_content)


# === CLI Entry Point ===

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze a personal photo using OpenAI GPT-4o vision.")
    parser.add_argument("image_path", help="Path to the image file to analyze")
    parser.add_argument("size", type=int, help="Image size to cut into", default=512)
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical", "none"],
        default="none",
        help="Set logging level (default: info; 'none' disables logging)"
    )
    args = parser.parse_args()
    if args.log_level.lower() != "none":
        configure_logging(getattr(logging, args.log_level.upper()))

    base64_image = load_and_encode_image(args.image_path, args.size)
    analyze_image(base64_image)
