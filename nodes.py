"""ComfyUI path loader nodes.

These nodes load images and text from on-disk file paths instead of the
built-in upload widgets, which is handy for batch / automation workflows
where file paths are produced by other tools or passed in as strings.

Author: somerlttle
"""

import os
import re
import glob
import shutil
import tempfile
import uuid
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


def _extract_number(path: str):
    """Extract the trailing integer from a filename stem, e.g. ComfyUI_5 -> 5."""
    stem = os.path.splitext(os.path.basename(path))[0]
    digits = re.findall(r"\d+", stem)
    return int(digits[-1]) if digits else None


def _natural_sort_key(path: str):
    """Sort key: numeric part first (so ComfyUI_2 < ComfyUI_10), then name."""
    name = os.path.basename(path).lower()
    return (_extract_number(path) or 0, name)


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
        return sorted(files, key=_natural_sort_key)
    if os.path.isfile(image_path):
        return [image_path]
    # support a single glob pattern, e.g. "D:/imgs/*.png"
    matches = sorted(glob.glob(image_path), key=_natural_sort_key)
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


_TEXT_EXTS = (".txt", ".text", ".md", ".csv", ".json", ".prompt", ".caption")


def _resolve_text_paths(text_path: str):
    """Return a sorted list of text file paths from a file, directory, or glob.

    - exact file            -> [that file]
    - directory             -> all text-like files inside, sorted (natural/numeric)
    - bare name w/o ext     -> auto-append .txt if such a file exists
    - glob (e.g. *.txt)     -> all matching files, sorted (natural/numeric)
    """
    text_path = (text_path or "").strip()
    if not text_path:
        return []
    if os.path.isdir(text_path):
        files = [
            os.path.join(text_path, f)
            for f in os.listdir(text_path)
            if f.lower().endswith(_TEXT_EXTS)
        ]
        return sorted(files, key=_natural_sort_key)
    if os.path.isfile(text_path):
        return [text_path]
    # auto-append .txt when the literal path has no extension but a .txt exists
    if not os.path.splitext(text_path)[1] and os.path.isfile(text_path + ".txt"):
        return [text_path + ".txt"]
    # support a glob pattern, e.g. "D:/datasets/*.txt"
    matches = sorted(glob.glob(text_path), key=_natural_sort_key)
    matches = [m for m in matches if os.path.isfile(m)]
    if matches:
        return matches
    return []


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
    CATEGORY = "路径加载"

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
# Node 2: load text content by path (per-file output, with file number)
# ---------------------------------------------------------------------------
class LoadTextByPath:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text_path": (
                    "STRING",
                    {"multiline": False, "default": "",
                     "tooltip": "文本文件路径 / 目录(逐文件加载其中全部文本) / glob 通配符；省略扩展名会自动补 .txt"},
                ),
            },
            "optional": {
                "strip_newline": (
                    "BOOLEAN",
                    {"default": True, "tooltip": "移除每个文件末尾单独的一行换行"},
                ),
                "output_each_file": (
                    "BOOLEAN",
                    {"default": True,
                     "tooltip": "逐文件输出(开): 目录/多文件时每个文件单独输出并带 file_number；关则合并成一个字符串"},
                ),
            },
        }

    RETURN_TYPES = ("STRING", "INT", "STRING")
    RETURN_NAMES = ("text", "file_number", "file_name")
    FUNCTION = "load_text"
    CATEGORY = "路径加载"

    def load_text(self, text_path, strip_newline=True, output_each_file=True):
        paths = _resolve_text_paths(text_path)
        if not paths:
            hint = (
                "支持：完整文件路径 / 目录(逐文件加载其中全部文本文件) / glob 通配符"
                "(如 D:/datasets/*.txt)；若省略扩展名会自动尝试补 .txt"
            )
            raise FileNotFoundError(f"Text file not found: {text_path}\n{hint}")

        entries = []
        for idx, p in enumerate(paths, start=1):
            content = _read_text_file(p)
            if strip_newline and content.endswith("\n"):
                content = content[:-1]
            num = _extract_number(p)
            if num is None:
                num = idx  # 文件名无数字时按序号 1,2,3... 编号
            name = os.path.splitext(os.path.basename(p))[0]
            entries.append((content, num, name))

        # ----- 单文件 或 合并模式：返回标量 -----
        if not output_each_file or len(entries) == 1:
            if len(entries) == 1:
                content, num, name = entries[0]
                return (content, num, name)
            content = "\n\n".join(e[0] for e in entries)
            return (content, len(entries), text_path)

        # ----- 逐文件模式：返回列表，ComfyUI 自动逐个迭代下游节点 -----
        texts = [e[0] for e in entries]
        nums = [e[1] for e in entries]
        names = [e[2] for e in entries]
        return (texts, nums, names)


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
                    {"multiline": False, "default": "",
                     "tooltip": "文本文件路径 / 目录(加载其中全部文本) / glob 通配符；省略扩展名会自动补 .txt"},
                ),
            },
            "optional": {
                "strip_newline": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("image", "mask", "text")
    FUNCTION = "load_both"
    CATEGORY = "路径加载"

    def load_both(self, image_path, text_path, strip_newline=True):
        img_node = LoadImageByPath()
        image, mask = img_node.load_image(image_path)

        txt_node = LoadTextByPath()
        # 合并模式：始终保持返回单个字符串文本
        res = txt_node.load_text(text_path, strip_newline, output_each_file=False)
        text = res[0]

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
                "middle_char": (
                    "STRING",
                    {"multiline": False, "default": "_", "tooltip": "自定义中间字符：前缀/时间戳/后缀之间的连接符，例如 _ 或 -"},
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
                "add_counter": (
                    "BOOLEAN",
                    {"default": True, "tooltip": "在文件名后追加数字后缀（如 _1），并作为重名计数器的起点"},
                ),
                "counter_start": (
                    "INT",
                    {"default": 1, "min": 0, "max": 999999, "step": 1,
                     "tooltip": "数字后缀的起始值（后缀从几开始）；重名时计数器也从该值递增"},
                ),
            },
            "optional": {
                "save_name": (
                    "STRING",
                    {"multiline": False, "default": "",
                     "tooltip": "精确文件名(可选)：填了就直接用此名(自动去扩展名)，覆盖 前缀/时间戳/计数 规则；可接上游 file_name 实现逐文件精确命名"},
                ),
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
    CATEGORY = "路径加载"

    def save_text(self, text, output_dir, filename_prefix, filename_suffix,
                  middle_char, extension, encoding, add_timestamp,
                  add_counter, counter_start, overwrite=False, save_name=""):
        # resolve output directory
        if output_dir and output_dir.strip():
            out_dir = os.path.abspath(output_dir.strip())
        elif folder_paths is not None:
            out_dir = folder_paths.get_temp_directory()
        else:
            out_dir = tempfile.gettempdir()
        os.makedirs(out_dir, exist_ok=True)

        # build base filename
        save_name = (save_name or "").strip()
        if save_name:
            # easy_use 风格：精确文件名，直接覆盖 前缀/时间戳/计数 规则
            base_name = os.path.splitext(save_name)[0]
            add_timestamp = False
            add_counter = False
        else:
            sep = middle_char or ""
            parts = []
            if filename_prefix:
                parts.append(filename_prefix)
            if add_timestamp:
                parts.append(datetime.now().strftime("%Y%m%d-%H%M%S"))
            if filename_suffix:
                parts.append(filename_suffix)
            base_name = sep.join(parts)

        ext = extension.strip() or "txt"
        if not ext.startswith("."):
            ext = "." + ext

        # optional numeric suffix (数字后缀 / 计数器)
        candidate = base_name
        if add_counter:
            cnt = str(int(counter_start))
            candidate = (candidate + sep + cnt) if candidate else cnt

        base_path = os.path.join(out_dir, candidate + ext)

        # avoid overwriting existing files unless explicitly allowed
        final_path = base_path
        if os.path.exists(final_path) and not overwrite:
            # search for a free "base_name [sep] N" starting from counter_start
            i = int(counter_start)
            while os.path.exists(os.path.join(out_dir, f"{base_name}{sep}{i}{ext}")):
                i += 1
            final_path = os.path.join(out_dir, f"{base_name}{sep}{i}{ext}")

        with open(final_path, "w", encoding=encoding) as f:
            f.write(text if isinstance(text, str) else str(text))

        return (final_path,)


# ---------------------------------------------------------------------------
# Node 5: batch rename every file (image + text) in a folder, keep pairs
# ---------------------------------------------------------------------------
class RenameFolderFiles:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "folder": (
                    "STRING",
                    {"multiline": False, "default": "",
                     "tooltip": "要重命名文件的文件夹路径"},
                ),
                "filename_prefix": (
                    "STRING",
                    {"multiline": False, "default": "a", "tooltip": "新文件名前缀，例如 a"},
                ),
                "middle_char": (
                    "STRING",
                    {"multiline": False, "default": "_",
                     "tooltip": "前缀与编号之间的连接符，如 _ 或 -"},
                ),
                "start_number": (
                    "INT",
                    {"default": 1, "min": 0, "max": 999999, "step": 1,
                     "tooltip": "编号起始值（重命名后从几开始）"},
                ),
                "number_padding": (
                    "INT",
                    {"default": 0, "min": 0, "max": 12, "step": 1,
                     "tooltip": "数字补零位数：0=不补零(1,2,3)；2=补到2位(01,02…)；3=补到3位(001,002…)。上限12，比参考插件(was-node-suite)的9更高"},
                ),
            },
            "optional": {
                "output_dir": (
                    "STRING",
                    {"multiline": False, "default": "",
                     "tooltip": "重命名后的输出目录：留空=在原文件夹内原地重命名；填了=把文件移动到该目录并以新名保存"},
                ),
                "only_extensions": (
                    "STRING",
                    {"multiline": False, "default": "",
                     "tooltip": "只处理这些扩展名(逗号分隔，如 jpg,png,txt)；留空=处理全部文件"},
                ),
                "pair_by_number": (
                    "BOOLEAN",
                    {"default": True,
                     "tooltip": "按原文件名里的数字配对：同编号的图片与文本使用同一个新编号（a_1.jpg + a_1.txt）；关闭则纯按文件名顺序重排"},
                ),
                "dry_run": (
                    "BOOLEAN",
                    {"default": True,
                     "tooltip": "预览模式：只返回将要执行的重命名列表，不真正改名（建议先开着确认）"},
                ),
                "delete_source": (
                    "BOOLEAN",
                    {"default": False,
                     "tooltip": "删除源文件：默认关闭时采用【复制】方式——先在内部复制、改成新名、再输出到目标目录，源文件原样保留；开启后复制全部成功后再删除源文件（安全移动）"},
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("report",)
    FUNCTION = "rename_files"
    OUTPUT_NODE = True
    CATEGORY = "路径加载"

    def rename_files(self, folder, filename_prefix, middle_char, start_number,
                     number_padding=0, output_dir="", only_extensions="",
                     pair_by_number=True, dry_run=True, delete_source=False):
        if not folder or not os.path.isdir(folder):
            raise FileNotFoundError(f"文件夹不存在: {folder}")

        # 输出目录：留空=原地重命名；填了=移动到该目录
        if output_dir and output_dir.strip():
            dest_dir = os.path.abspath(output_dir.strip())
            os.makedirs(dest_dir, exist_ok=True)
        else:
            dest_dir = folder

        sep = middle_char or ""
        ext_filter = set()
        if only_extensions and only_extensions.strip():
            ext_filter = {
                ("." + e.strip().lower().lstrip("."))
                for e in only_extensions.split(",") if e.strip()
            }

        files = []
        for f in os.listdir(folder):
            fp = os.path.join(folder, f)
            if not os.path.isfile(fp):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext_filter and ext not in ext_filter:
                continue
            files.append((f, ext))

        if not files:
            return ("没有匹配的文件。",)

        # group files: by original number (so jpg+txt share a new number) or unique per file
        raw_groups = {}
        seq = 0
        for f, ext in files:
            num = _extract_number(f)
            if pair_by_number and num is not None:
                key = num
            else:
                key = ("__seq", seq)
                seq += 1
            raw_groups.setdefault(key, []).append((f, ext))

        def sort_key(k):
            return (0, k) if isinstance(k, int) else (1, k[1])

        ordered_keys = sorted(raw_groups.keys(), key=sort_key)

        # build rename plan: (old_path, new_name)
        pad = max(0, int(number_padding))
        plan = []
        for gi, key in enumerate(ordered_keys, start=int(start_number)):
            new_num = gi
            num_str = str(new_num).zfill(pad) if pad > 0 else str(new_num)
            for f, ext in raw_groups[key]:
                plan.append((os.path.join(folder, f),
                             f"{filename_prefix}{sep}{num_str}{ext}"))

        # collision checks
        final_names = [n for _, n in plan]
        seen = set()
        dups = set()
        for n in final_names:
            if n in seen:
                dups.add(n)
            seen.add(n)
        if dups:
            raise ValueError("重命名后存在重复文件名(同扩展名冲突): " + ", ".join(sorted(dups)))

        planned_new = {n for _, n in plan}
        for o, n in plan:
            if os.path.exists(os.path.join(dest_dir, n)) and n not in planned_new:
                raise FileExistsError(
                    f"目标文件已存在(非本次重命名覆盖): {n}，请换个前缀或先备份。")

        # preview
        if dry_run:
            op = "复制并改名(保留原文件)" if not delete_source else "复制后删除源文件(安全移动)"
            head = (f"[预览] 将{op} {len(plan)} 个文件" +
                    (f" 到 {dest_dir}" if dest_dir != folder else "") +
                    "（未真正执行，关闭 dry_run 才会生效）:")
            lines = [head]
            for o, n in plan:
                lines.append(f"{os.path.basename(o)}  ->  {n}")
            if not delete_source:
                lines.append("（源文件将保留，不会被删除）")
            else:
                lines.append("（复制全部成功后再删除源文件）")
            return ("\n".join(lines),)

        # execute: 先内部复制 -> 改名 -> 输出到目标目录
        copied = []
        temps = []
        try:
            for i, (o, n) in enumerate(plan):
                dst = os.path.join(dest_dir, n)
                # phase1: 复制到目标目录内的临时文件（内部复制）
                tmp = os.path.join(
                    dest_dir,
                    f"__rn_{i}_{uuid.uuid4().hex}__{os.path.splitext(n)[1]}",
                )
                shutil.copy2(o, tmp)        # 复制并保留元数据
                temps.append(tmp)
                # phase2: 改名为最终文件名（输出到目标文件）
                os.rename(tmp, dst)
                copied.append(n)
        except Exception:
            # 清理可能残留的临时文件，避免留下 __rn_ 垃圾
            for t in temps:
                if os.path.exists(t):
                    try:
                        os.remove(t)
                    except OSError:
                        pass
            raise

        # 可选：删除源文件（安全移动）—— 仅在所有复制都成功后
        deleted = []
        if delete_source:
            for o, _ in plan:
                try:
                    os.remove(o)
                    deleted.append(os.path.basename(o))
                except OSError as e:
                    deleted.append(f"{os.path.basename(o)} 删除失败: {e}")

        verb = "已复制并改名(保留原文件)" if not delete_source else "已复制并改名，并删除源文件(安全移动)"
        dest_note = f" -> {dest_dir}" if dest_dir != folder else ""
        result = f"{verb} {len(copied)} 个文件{dest_note}:\n" + "\n".join(copied)
        if delete_source and deleted:
            result += "\n已删除源文件:\n" + "\n".join(deleted)
        return (result,)


# Expose node list for __init__.py
NODE_CLASS_MAPPINGS = {
    "LoadImageByPath": LoadImageByPath,
    "LoadTextByPath": LoadTextByPath,
    "LoadImageAndTextByPath": LoadImageAndTextByPath,
    "SaveTextFile": SaveTextFile,
    "RenameFolderFiles": RenameFolderFiles,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadImageByPath": "按路径加载图像",
    "LoadTextByPath": "按路径加载文本",
    "LoadImageAndTextByPath": "按路径加载图像与文本",
    "SaveTextFile": "保存文本文件",
    "RenameFolderFiles": "重命名文件夹文件",
}
