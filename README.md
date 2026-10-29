# ComfyUI 重命名文件夹文件

ComfyUI 自定义节点：把文件夹里的全部文件（图片 + 文本一起）按统一规则批量重命名。

> Author: **somerlttle**

## 节点

所有节点位于 `路径加载` 分类下。

| 节点 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| **重命名文件夹文件** | `folder` (STRING, 文件夹)<br>`filename_prefix` (STRING, 默认 `ComfyUI`)<br>`middle_char` (STRING, 默认 `_`)<br>`start_number` (INT, 默认 1)<br>`number_padding` (INT, 默认 0)<br>`output_dir` (STRING, 可选, 默认空)<br>`only_extensions` (STRING, 可选, 如 `jpg,png,txt`)<br>`pair_by_number` (BOOLEAN, 默认 true)<br>`dry_run` (BOOLEAN, 默认 false)<br>`delete_source` (BOOLEAN, 可选, 默认 false) | `STRING` (`report`) | **批量重命名文件夹里的全部文件（图片+文本一起）**。新文件名格式：`前缀 [中间字符] 编号.原扩展名`（如 `ComfyUI_1.txt` / `ComfyUI_1.jpg`）。`pair_by_number`(默认开)：按原文件名里的数字配对，同编号的图片与文本得到**同一个新编号**，保持成对；`start_number` 控制从几开始编号。`number_padding` 可补零（2=补到2位 `01,02`，上限12）。`only_extensions` 可只处理指定扩展名。`dry_run`(默认关)：**关=真正执行；开=只预览要改的文件清单、不真正改名**。**操作采用「先内部复制 → 改成新名 → 输出到目标目录」**：`delete_source` 默认关时源文件原样保留（复制一份以新名输出，旧名不消失）；`delete_source` 开时复制全部成功后再删除源文件（安全移动）。`output_dir` 留空=输出回原文件夹、填了=输出到该目录。重名冲突或目标已存在会直接报错，不会覆盖 |

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

重启 ComfyUI 后，在节点列表中搜索 `重命名文件夹文件` 即可。

## 使用示例

场景：文件夹 `D:/datasets/8_苗条美女1` 里是成对的 `ComfyUI_1.jpg`+`ComfyUI_1.txt` … 想统一重命名为 `ComfyUI_1.jpg`+`ComfyUI_1.txt`、`ComfyUI_2.*` …（图片也同样改名）。

1. 新建 `重命名文件夹文件` 节点，`folder` 填该目录；`filename_prefix` 填 `ComfyUI`、`middle_char` 填 `_`、`start_number` 填 `1`。
2. **数字补零位数（可选）**：`number_padding` 填 `2` → `ComfyUI_01.jpg`/`ComfyUI_02.jpg`…；`3` → `ComfyUI_001`；`0`=不补零（`ComfyUI_1`）。上限 12。
3. **输出目录（可选）**：`output_dir` 留空 = 把新名字的文件输出回原文件夹；填了某个目录 = 把新名字的文件输出到该目录。无论哪种，`delete_source` 默认关时源文件都**原样保留**（复制而非移动）。
4. 先**保持 `dry_run=开`**，运行一次，看 `report` 输出是否如预期（例如 `ComfyUI_5.jpg -> ComfyUI_5.jpg`、`ComfyUI_5.txt -> ComfyUI_5.txt`）。
5. 确认无误后把 `dry_run` 关掉再运行，即真正改名/复制输出。

> 默认 `pair_by_number=开`：同编号的图片与文本会自动拿到同一个新编号，保证成对。若只想改某类文件，用 `only_extensions` 限定（如 `txt` 或 `jpg,png`）。重命名不可逆，建议先 `dry_run` 预览、`only_extensions` 限定范围，或在操作前备份文件夹。
>
> **关于"保留原文件"**：本节点默认就**复制而非移动**——先在内部把源文件复制一份、改成新名、再输出到目标目录，所以源文件原样保留（旧名字不消失）。只有把 `delete_source=开` 时才会复制成功后再删除源文件（安全移动）。`output_dir` 留空时新旧文件都在原文件夹里（一份原、一份新）；`output_dir` 填了目录时，源文件留在原文件夹、**复制件进目标目录**（源文件夹保持干净、不出现两份）。

## 许可

[MIT](./LICENSE) © 2026 somerlttle
