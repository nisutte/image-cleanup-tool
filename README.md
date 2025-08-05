# Image Cleanup Tool

A tool for scanning and analyzing personal photos using AI.

## Project Structure

This project follows Python packaging best practices:

```
image-cleanup-tool-1/
├── src/image_cleanup_tool/     # Main package
│   ├── core/                   # Core functionality
│   ├── api/                    # External API integrations
│   ├── ui/                     # User interface components
│   └── utils/                  # Shared utilities
├── scripts/                    # CLI entry points
├── tests/                      # Test suite
└── pyproject.toml             # Project configuration
```

## Image Preprocessing Script

`resize_and_encode.py` crops images to a centered square, resizes them to specified square dimensions, and outputs base64-encoded JPEG strings, suitable for use with the o4-mini model. It accepts either a single image file or a directory (recursively processes JPEG/PNG/HEIC files).

### Prerequisites

This project uses [uv](https://github.com/astral.sh/uv) for dependency management. Install uv first:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then install dependencies:

```bash
uv sync
```

Alternatively, if you prefer pip:

```bash
pip install pillow pillow-heif rich openai aiohttp tenacity
```

### Usage

With uv (recommended):
```bash
# Single image:
uv run python src/image_cleanup_tool/core/image_encoder.py path/to/image.jpg --output-dir b64_out --sizes 512 256

# Entire directory (recursive batch):
uv run python src/image_cleanup_tool/core/image_encoder.py path/to/images_dir --output-dir b64_out --sizes 512 256
```

With pip:
```bash
# Single image:
python3 resize_and_encode.py path/to/image.jpg --output-dir b64_out --sizes 512 256

# Entire directory (recursive batch):
python3 resize_and_encode.py path/to/images_dir --output-dir b64_out --sizes 512 256
```

Each processed image produces one text file per size, named `<basename>_<size>.txt`, under the given output directory (mirroring subfolders for batch mode).

## Listing & inspecting images

After installing prerequisites, you can perform a quick CLI scan or launch the interactive TUI.

### Non-interactive CLI

Scan a directory to count images by extension and display a capture-date histogram.
The CLI will also report how many images are cached, then prompt to analyze any uncached images one by one:

```bash
uv run python scripts/main.py path/to/images_dir
```

### Interactive Rich UI

Launch the interactive Rich UI to explore scan progress, cache status, and image analysis in real time:

```bash
uv run python scripts/main.py --ui path/to/images_dir
```

- **Scan Progress Bar**: Shows file scanning progress with time elapsed
- **Cache Status Bar**: Displays cached vs uncached images with color coding (green=cached, yellow=uncached)
- **Analysis Progress Bar**: Full-width progress bar for analyzing uncached images with time remaining
- **Results Display**: 3-line text area showing latest analysis results with color-coded classifications
- **Automatic Analysis**: Analysis starts automatically after cache check completes

## Image Analysis with OpenAI GPT

`openai_api.py` uses OpenAI's GPT-4o Vision model to analyze a single image. It sends a prompt requesting:
1. A 3-sentence description.
2. Scores for categories (`blurry`, `meme`, `screenshot`, `document`, `personal`, `non_personal`, `contains_faces`).
3. A final classification (`keep`, `discard`, `unsure`).

The script requires the `OPENAI_API_KEY` environment variable to be set.

### CLI Usage
```bash
export OPENAI_API_KEY=your_api_key
uv run python src/image_cleanup_tool/api/openai_api.py path/to/image.jpg [size] [--log-level LEVEL]
```
- `path/to/image.jpg`: Path to the image file to analyze.
- `size`: Optional integer for the square crop/resize dimension (default: 512).
- `--log-level`: Optional logging level (`debug`, `info`, `warning`, `error`, `critical`, `none`).

The output is printed as formatted JSON with these keys:
- `description`: Textual description of the image.
- `category_scores`: Scores for each category.
- `final_classification`: Scores suggesting whether to keep, discard, or mark as unsure.

### Python API
```python
import json
from openai_api import load_and_encode_image, analyze_image

# Load and encode image to a base64 string
image_b64 = load_and_encode_image("path/to/foo.jpg", 512)

# Analyze and get the result dict
result = analyze_image(image_b64)
print(json.dumps(result, indent=2))
```

## Python API

If you’d rather call the logic programmatically, import these helpers:

```python
from image_cleanup_tool.core.image_encoder import (
    crop_and_resize_to_b64,
    batch_images_to_b64,
)
from image_cleanup_tool.utils.log_utils import configure_logging
```

# initialize logging (optional)
configure_logging()

# Single image → dict of size→base64
b64_map = crop_and_resize_to_b64("foo.jpg", [512, 256])

# Directory batch → dict of rel_path→(size→base64)
batches = batch_images_to_b64("images_dir", [512, 256])

# Persist to disk:
write_b64_files(batches, "out_dir")
```

### Async Image Analysis

For efficient concurrent image analysis, use the async worker pool:

```python
import asyncio
from image_cleanup_tool.core import analyze_images_async, AsyncWorkerPool

# Simple usage with convenience function
async def analyze_my_images():
    image_paths = [Path("image1.jpg"), Path("image2.jpg")]
    results = await analyze_images_async(
        image_paths=image_paths,
        max_concurrent=5,        # Process 5 images at once
        requests_per_minute=30,  # Rate limit to 30 requests per minute
        size=512                 # Resize images to 512x512
    )
    
    for path, result in results.items():
        if not isinstance(result.result, Exception):
            classification = result.result['final_classification']
            print(f"{path.name}: {classification['keep']}% keep")

# Advanced usage with custom worker pool
async def advanced_analysis():
    pool = AsyncWorkerPool(
        image_paths=image_paths,
        max_concurrent=10,
        requests_per_minute=60,
        size=512,
        timeout=30.0
    )
    
    results = await pool.analyze_all()
    # Process results...

# Run the async function
asyncio.run(analyze_my_images())
```

The async implementation provides:
- **Efficient concurrency** using asyncio instead of threading
- **Built-in rate limiting** to respect API limits
- **Automatic retry logic** with exponential backoff
- **Progress tracking** for monitoring analysis status
- **Connection pooling** for better performance

### Cache Management

The image analysis cache includes versioning and cleanup features:

```python
from image_cleanup_tool.core import ImageCache

# Create cache with specific model
cache = ImageCache(model="gpt-4.1-nano")

# Get cache statistics
stats = cache.get_stats()
print(f"Cache has {stats['total_entries']} entries")

# Clean up old entries (older than 30 days, max 10000 entries)
removed = cache.cleanup(max_age_days=30, max_entries=10000)
print(f"Removed {removed} old entries")
```

**Features:**
- **Version control**: Cache entries are invalidated when analysis logic changes
- **Model tracking**: Different AI models have separate cache entries
- **Automatic cleanup**: Remove old entries by age or count
- **Statistics**: Monitor cache size and usage
- **Backward compatibility**: Handles legacy cache formats
