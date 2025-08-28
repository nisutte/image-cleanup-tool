"""
Prompt for image analysis.
"""

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