from pydantic import BaseModel
from typing import Literal

"""
Prompt for image analysis.
"""

class ImageClassificationResponse(BaseModel):
    decision: Literal["keep", "unsure", "delete"]
    confidence_keep: float
    confidence_unsure: float
    confidence_delete: float
    primary_category: Literal["people", "scenery", "document", "screenshot", "meme", "pet", "food", "vehicle", "object", "unknown"]
    reason: str


class JsonSchema(BaseModel):
    name: str
    strict: bool
    schema: ImageClassificationResponse


PROMPT_TEMPLATE_V1 = """
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


PROMPT_TEMPLATE_V2 = """
You are an image-triage assistant for a single downscaled 512x512 WhatsApp image from old phones (5+ years).

OUTPUT (STRICT JSON ONLY)
Fields:
{
  "decision": "keep" | "unsure" | "delete",
  "confidence_keep": <0..1>,
  "confidence_unsure": <0..1>,
  "confidence_delete": <0..1>,
  "primary_category": "people" | "scenery" | "document" | "screenshot" | "meme" | "pet" | "food" | "vehicle" | "object" | "unknown",
  "reason": "<<=100 chars, single line, ASCII-only>"
}
Rules:
- Confidences must each be 0..1, rounded to two decimals, and sum to exactly 1.00.
- No extra text/markdown. JSON only.
- Do not invent dates/locations/names.

POLICY (delete is intentionally loose; screenshots are usually low value after 5+ years)
- KEEP: clear personal moments with people/pets; strong scenery/travel landmarks; important documents with long-term value (passport/ID/visa/diploma).
- UNSURE: ambiguous subject; document-like but not clearly important; partial/obscured faces; could be personal but unclear.
- DELETE: default for screenshots unless clearly personal (e.g., chat with known faces or unique memory); memes; accidental shots; heavy blur/blank/dark frames; no salient subject.
- If torn between UNSURE and DELETE and there are no people or important documents → choose DELETE.

Return JSON only. Examples:
{
  "decision": "delete",
  "confidence_keep": 0.03,
  "confidence_unsure": 0.07,
  "confidence_delete": 0.90,
  "primary_category": "screenshot",
  "reason": "Generic app settings UI; no personal context; old screenshots low value"
},
{
  "decision": "keep",
  "confidence_keep": 0.88,
  "confidence_unsure": 0.08,
  "confidence_delete": 0.04,
  "primary_category": "people",
  "reason": "Two friends smiling indoors; clear personal memory"
},
{
  "decision": "unsure",
  "confidence_keep": 0.34,
  "confidence_unsure": 0.46,
  "confidence_delete": 0.20,
  "primary_category": "scenery",
  "reason": "Dim landscape; subject unclear but could be from a trip"
}

""".strip()

PROMPT_TEMPLATE = PROMPT_TEMPLATE_V2