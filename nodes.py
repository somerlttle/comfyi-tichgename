"""ComfyUI path loader nodes.

These nodes load images and text from on-disk file paths instead of the
built-in upload widgets, which is handy for batch / automation workflows
where file paths are produced by other tools or passed in as strings.

Author: somerlttle
"""

import os
import glob
import tempfile
from datetime import datetime

import numpy as np
import torch
from PIL import Image, ImageOps

try:
    import folder_paths  # provided by ComfyUI at runtime
except Exception:  # pragma: no cover - keeps module importable outside ComfyUI
    folder_paths = None


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


# ---------------------------------------------------------------------------
# Node 4: save text to a file with custom prefix / suffix / path
# ---------------------------------------------------------------------------
class SaveTextFile:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "default": "", "tooltip": "Text content to save"}),
                "output_dir": (
                    "STRING",
                    {"multiline": False, "default": "", "tooltip": "Save folder; empty = ComfyUI temp dir"},
                ),
                "filename_prefix": (
                    "STRING",
                    {"multiline": False, "default": "ComfyUI", "tooltip": "Filename prefix"},
                ),
                "filename_suffix": (
                    "STRING",
                    {"multiline": False, "default": "", "tooltip": "Filename suffix (appended before extension)"},
                ),
                "extension": (
                    "STRING",
                    {"multiline": False, "default": "txt", "tooltip": "File extension without dot"},
                ),
                "encoding": (["utf-8", "utf-8-sig", "gbk", "latin-1"], {"default": "utf-8"}),
                "add_timestamp": (
                    "BOOLEAN",
                    {"default": True, "tooltip": "Append YYYYMMDD-HHMMSS to keep filenames unique"},
                ),
            },
            "optional": {
                "overwrite": (
                    "BOOLEAN",
                    {"default": False, "tooltip": "If false, append _1/_2... when the file already exists"},
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("file_path",)
    FUNCTION = "save_text"
    OUTPUT_NODE = True
    CATEGORY = "path loader"

    def save_text(self, text, output_dir, filename_prefix, filename_suffix,
                  extension, encoding, add_timestamp, overwrite=False):
        # resolve output directory
        if output_dir and output_dir.strip():
            out_dir = os.path.abspath(output_dir.strip())
        elif folder_paths is not None:
            out_dir = folder_paths.get_temp_directory()
        else:
            out_dir = tempfile.gettempdir()
        os.makedirs(out_dir, exist_ok=True)

        # build base filename: prefix [+ _timestamp] + suffix
        name = filename_prefix or ""
        if add_timestamp:
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            name = f"{name}_{ts}" if name else ts
        name = name + (filename_suffix or "")

        ext = extension.strip() or "txt"
        if not ext.startswith("."):
            ext = "." + ext
        base_path = os.path.join(out_dir, name + ext)

        # avoid overwriting existing files unless explicitly allowed
        final_path = base_path
        if os.path.exists(final_path) and not overwrite:
            stem, ext2 = os.path.splitext(base_path)
            i = 1
            while os.path.exists(f"{stem}_{i}{ext2}"):
                i += 1
            final_path = f"{stem}_{i}{ext2}"

        with open(final_path, "w", encoding=encoding) as f:
            f.write(text if isinstance(text, str) else str(text))

        return (final_path,)


# Expose node list for __init__.py
NODE_CLASS_MAPPINGS = {
    "LoadImageByPath": LoadImageByPath,
    "LoadTextByPath": LoadTextByPath,
    "LoadImageAndTextByPath": LoadImageAndTextByPath,
    "SaveTextFile": SaveTextFile,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadImageByPath": "Load Image By Path (somerlttle)",
    "LoadTextByPath": "Load Text By Path (somerlttle)",
    "LoadImageAndTextByPath": "Load Image And Text By Path (somerlttle)",
    "SaveTextFile": "Save Text File (somerlttle)",
}
