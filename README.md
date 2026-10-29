# ComfyUI-PathLoader

按文件路径加载图像与文本内容的 ComfyUI 自定义节点。  
相比内置的「上传」控件，本插件直接用字符串路径（或目录 / glob）读取磁盘上的图片和 `.txt`，更适合批量处理、自动化或把其它工具生成的路径喂给 ComfyUI 的工作流。

> Author: **somerlttle**

## 节点一览

所有节点位于 `path loader` 分类下。

| 节点 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| **Load Image By Path** | `image_path` (STRING)<br>`load_cap` (INT, 可选) | `IMAGE`, `MASK` | 支持单文件、目录（加载目录内全部图片，按文件名排序）或 glob 通配符（如 `D:/imgs/*.png`）；`load_cap=0` 表示不限数量 |
| **Load Text By Path** | `text_path` (STRING)<br>`strip_newline` (BOOLEAN, 可选) | `STRING` | 按路径读取 `.txt` 文本，自动尝试 `utf-8` / `gbk` 等编码，可选去除末尾换行 |
| **Load Image And Text By Path** | `image_path` (STRING)<br>`text_path` (STRING)<br>`strip_newline` (BOOLEAN, 可选) | `IMAGE`, `MASK`, `STRING` | 一次性加载图像与文本，等价于上面两个节点合并 |

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

重启 ComfyUI 后，在节点列表中搜索 `Load Image By Path` / `Load Text By Path` 即可。

## 使用示例

1. 新建 `Load Image By Path` 节点，在 `image_path` 填入 `D:/work/input/img.png` 或目录 `D:/work/input`。
2. 新建 `Load Text By Path` 节点，在 `text_path` 填入 `D:/work/prompt.txt`。
3. 把 `IMAGE` 接到后续采样 / 预处理节点，`STRING` 接到 CLIP Text Encode 等节点。

## 许可

[MIT](./LICENSE) © 2026 somerlttle
