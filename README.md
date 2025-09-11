# Image Cleanup Tool

An AI-powered tool for analyzing and organizing personal photos. Uses multiple AI models (OpenAI, Claude, Gemini) to classify images and help you decide what to keep, delete, or review.

## Quick Start

### Installation

This project uses [uv](https://github.com/astral.sh/uv) for dependency management, to install it run:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync     # build the environment
uv pip install -e .  # install the image-cleanup command
source .venv/bin/activate  # activate the environment
```

### Basic Usage

```bash
# Analyze images in a directory (launches UI)
image-cleanup --ui path/to/images/

# Use specific API
image-cleanup --ui path/to/images/ --api openai

# Alternative: if you prefer not to activate the environment
uv run image-cleanup --ui path/to/images/
```

## Two-Phase Cleanup

After the images are analyzed, the tool uses a safe two-phase approach for the cleanup part:

**Phase 1**: Copy files to review buckets based on AI analysis
- `to_delete/` - Files marked for deletion
- `unsure/` - Files needing manual review
- `low_keep/` - Files to keep but with low confidence
- `documents/` - Document images

**Phase 2**: Move remaining files to final deletion
- Files still in review buckets → moved to `final_deletion/`
- Files you deleted from buckets → remain in original location

## Benchmark Mode

Test API performance and determinism:

```bash
# Test API performance and determinism
image-cleanup path/to/images/ --benchmark --limit 5

# Test single image multiple times
image-cleanup path/to/images/ --benchmark --test-image images/photo.jpg

# Compare all APIs on same images
image-cleanup path/to/images/ --benchmark --api all --limit 3
```

Benchmark mode shows:
- **Performance comparison** (average response times)
- **Determinism testing** (consistency across multiple runs)
- **Detailed results** per image and API

## API Configuration

### Environment Variables

Set up your API keys:

```bash
# OpenAI (GPT-5-nano)
export OPENAI_API_KEY=your_openai_key

# Anthropic (Claude Haiku)
export ANTHROPIC_API_KEY=your_anthropic_key

# Google (Gemini Flash)
export GOOGLE_API_KEY=your_google_key
```

### API Comparison

| API | Model | Speed | Cost | Deterministic |
|-----|-------|-------|------|---------------|
| OpenAI | GPT-5-nano | Fast | ~$0.85/10k images | Usually |
| Claude | Haiku | Medium | ~$0.50/10k images | Usually |
| Gemini | Flash 8B | Fastest | ~$0.26/10k images | Usually |

## Python API

### Basic Usage

```python
from image_cleanup_tool.api import ImageProcessor, get_client

# Load and encode image
image_b64 = ImageProcessor.load_and_encode_image("photo.jpg", 512)

# Create API client
client = get_client("gemini")

# Analyze image
result, tokens = client.analyze_image(image_b64)
print(f"Decision: {result['decision']}")
print(f"Confidence: {result['confidence_keep']:.2f}")
```

## Analysis Output

Each image analysis returns structured JSON:

```json
{
  "decision": "keep",
  "confidence_keep": 0.85,
  "confidence_unsure": 0.10,
  "confidence_delete": 0.05,
  "primary_category": "personal",
  "reason": "Clear photo of people, good quality, worth keeping"
}
```

### Categories

- **personal** - Photos of people, family, friends
- **document** - Screenshots, receipts, text documents
- **meme** - Internet memes, funny images
- **screenshot** - Screen captures, app interfaces
- **blurry** - Low quality, out of focus images

### Decisions

- **keep** - High quality, meaningful content
- **delete** - Low quality, duplicates, unwanted content
- **unsure** - Needs manual review

## Development

### Running Tests

```bash
# Test imports and basic functionality
uv run python -c "from image_cleanup_tool.core.scan_engine import ImageScanEngine; print('✅ All imports working')"

# Test web UI (development only)
uv run python tests/web_ui.py

# Test the entry point
image-cleanup --help
```

### Adding New APIs

1. Create a new client class inheriting from `APIClient` in `api/clients.py`
2. Implement the required abstract methods
3. Add the client to the `get_client()` factory function
4. Update the available APIs list in `main.py`

## License

This project is licensed under the MIT License - see the LICENSE file for details.