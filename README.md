# Simple tool to clean up my image mess

## Image Preprocessing Script

`resize_and_encode.py` crops images to a centered square, resizes them to specified square dimensions, and outputs base64-encoded JPEG strings, suitable for use with the o4-mini model. It accepts either a single image file or a directory (recursively processes JPEG/PNG/HEIC files).

### Prerequisites

Install required packages:

```bash
pip install pillow pillow-heif rich textual
```

### Usage

```bash
# Single image:
python3 resize_and_encode.py path/to/image.jpg --output-dir b64_out --sizes 512 256

# Entire directory (recursive batch):
python3 resize_and_encode.py path/to/images_dir --output-dir b64_out --sizes 512 256
```

Each processed image produces one text file per size, named `<basename>_<size>.txt`, under the given output directory (mirroring subfolders for batch mode).

## Listing & inspecting images

After installing prerequisites, launch the interactive TUI to scan a directory or single file:

```bash
python3 list_image_infos.py path/to/images_dir
```
This opens a real-time updating terminal interface featuring:
- A progress bar showing scan progress
- A table of image counts by extension
- A table of image counts by device (camera make/model)
- A capture-date histogram table

Press "q" at any time to quit the interface.

## Image Analysis with OpenAI GPT

`openai_api.py` uses OpenAI's GPT-4o Vision model to analyze a single image. It sends a prompt requesting:
1. A 3-sentence description.
2. Scores for categories (`blurry`, `meme`, `screenshot`, `document`, `personal`, `non_personal`, `contains_faces`).
3. A final classification (`keep`, `discard`, `unsure`).

The script requires the `OPENAI_API_KEY` environment variable to be set.

### CLI Usage
```bash
export OPENAI_API_KEY=your_api_key
python3 openai_api.py path/to/image.jpg [size] [--log-level LEVEL]
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
from resize_and_encode import (
    configure_logging,
    crop_and_resize_to_b64,
    batch_images_to_b64,
    write_b64_files,
)

# initialize logging (optional)
configure_logging()

# Single image → dict of size→base64
b64_map = crop_and_resize_to_b64("foo.jpg", [512, 256])

# Directory batch → dict of rel_path→(size→base64)
batches = batch_images_to_b64("images_dir", [512, 256])

# Persist to disk:
write_b64_files(batches, "out_dir")
```
