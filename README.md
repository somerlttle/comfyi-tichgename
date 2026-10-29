# ComfyUI-PathLoader

按文件路径加载图像与文本内容的 ComfyUI 自定义节点。  
相比内置的「上传」控件，本插件直接用字符串路径（或目录 / glob）读取磁盘上的图片和 `.txt`，更适合批量处理、自动化或把其它工具生成的路径喂给 ComfyUI 的工作流。

> Author: **somerlttle**

## 节点一览

所有节点位于 `路径加载` 分类下。

| 节点 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| **按路径加载图像** | `image_path` (STRING)<br>`load_cap` (INT, 可选) | `IMAGE`, `MASK` | 支持单文件、目录（加载目录内全部图片，按文件名排序）或 glob 通配符（如 `D:/imgs/*.png`）；`load_cap=0` 表示不限数量 |
| **按路径加载文本** | `text_path` (STRING)<br>`strip_newline` (BOOLEAN, 可选)<br>`逐文件输出` (BOOLEAN, 可选, 默认 true) | `STRING` (`text`)<br>`INT` (`file_number`)<br>`STRING` (`file_name`) | 读取文本：支持**单文件 / 目录(逐文件加载其中全部文本) / glob 通配符**（如 `D:/datasets/*.txt`）；**省略扩展名会自动补 `.txt`**（如 `8_苗条美女1` → `8_苗条美女1.txt`）；自动尝试 `utf-8` / `gbk` 等编码，可选去除末尾换行。<br>**逐文件输出(默认开)**：输入目录/多个文件时，每个文件单独输出（返回列表，ComfyUI 自动逐个迭代下游节点），并额外带出 `file_number`（文件名里的数字编号，如 `ComfyUI_5.txt`→`5`，无数字时按 1,2,3… 序号）与 `file_name`（去扩展名的文件名）。关闭则合并成一个字符串（旧行为）。文件名按数字自然排序（1,2,…,12 而非 1,10,11,12,2…） |
| **按路径加载图像与文本** | `image_path` (STRING)<br>`text_path` (STRING)<br>`strip_newline` (BOOLEAN, 可选) | `IMAGE`, `MASK`, `STRING` | 一次性加载图像与文本，等价于上面两个节点合并 |
| **保存文本文件** | `text` (STRING, 多行)<br>`output_dir` (STRING, 保存路径)<br>`filename_prefix` (STRING, 前缀)<br>`filename_suffix` (STRING, 后缀)<br>`middle_char` (STRING, 中间字符, 默认 `_`)<br>`extension` (STRING, 默认 `txt`)<br>`encoding` (下拉: `utf-8`/`utf-8-sig`/`gbk`/`latin-1`)<br>`add_timestamp` (BOOLEAN, 默认 true)<br>`add_counter` (BOOLEAN, 默认 true, 数字后缀开关)<br>`counter_start` (INT, 默认 1, 数字后缀起始值)<br>`overwrite` (BOOLEAN, 可选) | `STRING` (`file_path`) | 把文本按「前缀 [中间字符] [时间戳] [中间字符] 后缀 [中间字符] 计数.扩展名」保存；`middle_char` 为前缀/时间戳/后缀/计数之间的连接符（如 `_`/`-`，留空则无）；`add_counter` 控制是否追加数字后缀，`counter_start` 设定该数字后缀（及重名计数器）的起始值（即“后缀从几开始”）；`output_dir` 留空则用 ComfyUI 临时目录；同名文件从 `counter_start` 起递增 `_N` 直到不冲突（除非 `overwrite=true`）；输出完整路径便于串联 |

图像输出格式与 ComfyUI 内置 `LoadImage` 完全一致：`IMAGE` 为 `float32`、形状 `[B, H, W, 3]`、范围 `0..1`；`MASK` 取 alpha 通道（无 alpha 时全 0，即完全不透明）。

## 安装

将本仓库放到 ComfyUI 的 `custom_nodes` 目录下：

```bash
# 进入你的 ComfyUI 目录
cd ComfyUI/custom_nodes
git clone https://github.com/somerlttle/comfyi-tichgename.git
# 或手动把本文件夹复制为 custom_nodes/comfyi-tichgename
```

依赖（通常 ComfyUI 已自带）：

```bash
pip install -r requirements.txt
```

重启 ComfyUI 后，在节点列表中搜索 `按路径加载图像` / `按路径加载文本` / `保存文本文件` 即可。

## 使用示例

1. 新建 `按路径加载图像` 节点，在 `image_path` 填入 `D:/work/input/img.png` 或目录 `D:/work/input`。
2. 新建 `按路径加载文本` 节点，在 `text_path` 填入 `D:/work/prompt.txt` 或目录 `D:/work/prompts`。
3. 把 `IMAGE` 接到后续采样 / 预处理节点，`STRING` 接到 CLIP Text Encode 等节点。

### 批量改写文件夹里全部 txt（保留原编号）

场景：文件夹 `D:/datasets/8_苗条美女1` 内有 `ComfyUI_1.txt` … `ComfyUI_12.txt`，想逐个读取、处理后再以**相同编号**写回。

1. `按路径加载文本` 的 `text_path` 填该目录（或 `D:/datasets/8_苗条美女1/*.txt`）。默认 `逐文件输出=开` → 该节点分别输出 12 个 `text`、12 个 `file_number`(1…12)、12 个 `file_name`。
2. （中间接你的翻译 / 处理节点，输出仍是 12 份文本）
3. `保存文本文件` 的 `text` 接处理后的文本；`counter_start` 接上一步的 `file_number`；`filename_prefix` 填 `ComfyUI`、`middle_char` 填 `_`、`add_timestamp` 关、`add_counter` 开、`overwrite` 开。
4. ComfyUI 会以列表长度自动逐个迭代，依次写出 `ComfyUI_1.txt` … `ComfyUI_12.txt`，编号与源文件一致。

> 提示：若只想新增而不覆盖原文件，把 `overwrite` 关掉即可（同名时自动 `_N` 递增）。

## 许可

[MIT](./LICENSE) © 2026 somerlttle
