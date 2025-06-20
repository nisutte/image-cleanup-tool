# Simple tool to clean up my image mess

## Image Preprocessing Script

`resize_and_encode.py` crops images to a centered square, resizes them to specified square dimensions, and outputs base64-encoded JPEG strings, suitable for use with the o4-mini model. It accepts either a single image file or a directory (recursively processes JPEG/PNG/HEIC files).

### Prerequisites

Install required packages:

```bash
pip install pillow pillow-heif rich
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

After installing prerequisites, you can scan a directory (or single file) to see counts and a capture-date histogram:

```bash
python3 list_images.py path/to/images_dir
```
The output now also includes a table of devices (camera make and model) extracted from the images' EXIF metadata, displayed beside the counts by extension.

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
