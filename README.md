# Simple tool to clean up my image mess

## Image Preprocessing Script

`resize_and_encode.py` crops images to a centered square, resizes them to specified square dimensions, and outputs base64-encoded JPEG strings, suitable for use with the o4-mini model. It accepts either a single image file or a directory (recursively processes JPEG/PNG/HEIC files).

### Prerequisites

Install required packages:

```bash
pip install pillow pillow-heif
```

### Usage

```bash
# Single image:
python3 resize_and_encode.py path/to/image.jpg --output-dir b64_out --sizes 512 256

# Entire directory (recursive batch):
python3 resize_and_encode.py path/to/images_dir --output-dir b64_out --sizes 512 256
```

Each processed image produces one text file per size, named `<basename>_<size>.txt`, under the given output directory (mirroring subfolders for batch mode).
