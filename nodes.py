"""ComfyUI 文件夹批量重命名节点。

只保留「重命名文件夹文件」一个节点：把文件夹里的全部文件（图片+文本）按
`前缀 [中间字符] 编号.原扩展名` 的格式批量重命名，支持数字补零、按编号成对、
先复制改名再输出到目标目录（默认保留原文件）。

Author: somerlttle
"""

import os
import re
import shutil
import tempfile
import uuid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _extract_number(path: str):
    """Extract the trailing integer from a filename stem, e.g. ComfyUI_5 -> 5."""
    stem = os.path.splitext(os.path.basename(path))[0]
    digits = re.findall(r"\d+", stem)
    return int(digits[-1]) if digits else None


# ---------------------------------------------------------------------------
# 重命名文件夹文件：批量把文件夹里的全部文件改名（图片+文本一起）
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
                    {"multiline": False, "default": "ComfyUI",
                     "tooltip": "新文件名前缀，例如 ComfyUI"},
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
                     "tooltip": "数字补零位数：0=不补零(1,2,3)；2=补到2位(01,02…)；3=补到3位(001,002…)。上限12"},
                ),
            },
            "optional": {
                "output_dir": (
                    "STRING",
                    {"multiline": False, "default": "",
                     "tooltip": "重命名后的输出目录：留空=输出回原文件夹；填了=把新名字的文件输出到该目录"},
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
                    {"default": False,
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
                     pair_by_number=True, dry_run=False, delete_source=False):
        if not folder or not os.path.isdir(folder):
            raise FileNotFoundError(f"文件夹不存在: {folder}")

        # 输出目录：留空=输出回原文件夹；填了=输出到该目录
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
                    "（仅预览，将 dry_run 关闭才会真正执行）:")
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
    "RenameFolderFiles": RenameFolderFiles,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RenameFolderFiles": "重命名文件夹文件",
}
