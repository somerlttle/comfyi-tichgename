"""ComfyUI path loader nodes.

These nodes load images and text from on-disk file paths instead of the
built-in upload widgets, which is handy for batch / automation workflows
where file paths are produced by other tools or passed in as strings.

Author: somerlttle
"""

import os
import glob
import numpy as np
import torch
from PIL import Image, ImageOps


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff", ".tif")


def _load_single_image(path: str):
    """Load one image file and return (image_tensor, mask_tensor).

    image_tensor: torch.float32, shape [1, H, W, 3], range 0..1
    mask_tensor:  torch.float32, shape [1, H, W],    range 0..1
                  alpha channel if present, else all-zeros (fully opaque)
    """
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    image = np.array(img).astype(np.float32) / 255.0
    image = torch.from_numpy(image)[None,]

    if "A" in Image.open(path).getbands():
        mask = np.array(Image.open(path).getchannel("A")).astype(np.float32) / 255.0
        mask = 1.0 - torch.from_numpy(mask)
    else:
        mask = torch.zeros((1, image.shape[1], image.shape[2]), dtype=torch.float32)

    return image, mask


def _resolve_image_paths(image_path: str):
    """Return a sorted list of image file paths from a file or directory."""
    if os.path.isdir(image_path):
        files = [
            os.path.join(image_path, f)
            for f in os.listdir(image_path)
            if f.lower().endswith(_IMAGE_EXTS)
        ]
        return sorted(files)
    if os.path.isfile(image_path):
        return [image_path]
    # support a single glob pattern, e.g. "D:/imgs/*.png"
    matches = sorted(glob.glob(image_path))
    matches = [m for m in matches if m.lower().endswith(_IMAGE_EXTS)]
    if matches:
        return matches
    raise FileNotFoundError(f"Image path not found: {image_path}")


def _read_text_file(path: str) -> str:
    """Read a text file, trying a few common encodings."""
    encodings = ("utf-8", "utf-8-sig", "gbk", "latin-1")
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    # last resort: binary read, replace bad bytes
    with open(path, "rb") as f:
        return f.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Node 1: load a single image (or all images in a directory) by path
# ---------------------------------------------------------------------------
class LoadImageByPath:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_path": (
                    "STRING",
                    {"multiline": False, "default": "", "tooltip": "Image file, directory, or glob pattern"},
                ),
            },
            "optional": {
                "load_cap": (
                    "INT",
                    {"default": 0, "min": 0, "max": 10000, "step": 1,
                     "tooltip": "Max images to load (0 = no limit)"},
                ),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    FUNCTION = "load_image"
    CATEGORY = "path loader"

    def load_image(self, image_path, load_cap=0):
        paths = _resolve_image_paths(image_path)
        if not paths:
            raise FileNotFoundError(f"No images found at: {image_path}")
        if load_cap and len(paths) > load_cap:
            paths = paths[:load_cap]

        images, masks = [], []
        for p in paths:
            img, msk = _load_single_image(p)
            images.append(img)
            masks.append(msk)

        image = torch.cat(images, dim=0)
        mask = torch.cat(masks, dim=0)
        return (image, mask)


# ---------------------------------------------------------------------------
# Node 2: load text content by path
# ---------------------------------------------------------------------------
class LoadTextByPath:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text_path": (
                    "STRING",
                    {"multiline": False, "default": "", "tooltip": "Path to a .txt file"},
                ),
            },
            "optional": {
                "strip_newline": (
                    "BOOLEAN",
                    {"default": True, "tooltip": "Remove a single trailing newline"},
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "load_text"
    CATEGORY = "path loader"

    def load_text(self, text_path, strip_newline=True):
        if not os.path.isfile(text_path):
            raise FileNotFoundError(f"Text file not found: {text_path}")
        content = _read_text_file(text_path)
        if strip_newline and content.endswith("\n"):
            content = content[:-1]
        return (content,)


# ---------------------------------------------------------------------------
# Node 3: load both image and text in one node
# ---------------------------------------------------------------------------
class LoadImageAndTextByPath:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_path": (
                    "STRING",
                    {"multiline": False, "default": "", "tooltip": "Image file, directory, or glob pattern"},
                ),
                "text_path": (
                    "STRING",
                    {"multiline": False, "default": "", "tooltip": "Path to a .txt file"},
                ),
            },
            "optional": {
                "strip_newline": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "text")
    FUNCTION = "load_both"
    CATEGORY = "path loader"

    def load_both(self, image_path, text_path, strip_newline=True):
        img_node = LoadImageByPath()
        image, mask = img_node.load_image(image_path)

        txt_node = LoadTextByPath()
        (text,) = txt_node.load_text(text_path, strip_newline)

        return (image, mask, text)


# Expose node list for __init__.py
NODE_CLASS_MAPPINGS = {
    "LoadImageByPath": LoadImageByPath,
    "LoadTextByPath": LoadTextByPath,
    "LoadImageAndTextByPath": LoadImageAndTextByPath,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadImageByPath": "Load Image By Path (somerlttle)",
    "LoadTextByPath": "Load Text By Path (somerlttle)",
    "LoadImageAndTextByPath": "Load Image And Text By Path (somerlttle)",
}
