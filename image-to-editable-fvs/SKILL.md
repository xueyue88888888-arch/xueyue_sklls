---
name: image-to-editable-fvs
description: 把一张参考大屏图片转成「高还原 + 图表能装数据、用户能改」的 FineReport FVS。核心方法：原图做视觉底、擦除图表区、叠加原生图表。当用户说「照这个图做帆软大屏，要还原度高、数据能改、能装数据」「图片转 FVS 但图表要活的」「不要死图/贴图，要能在帆软里改数据的版本」时使用。上游接 big-screen-design-brief（产出含 ECharts 的 HTML 还原稿），下游是帆软设计器。
allowed-tools:
  - Bash
  - Read
  - Write
---

# 参考图 → 高还原可编辑 FVS

> **模型要求**：本技能全程以参考图为输入。执行它的模型必须**多模态**——能看图、
> 能读图里的文字（OCR）、能判断图表区域和面板边界。纯文本模型做不了，别硬派。



把一张大屏参考图，做成**视觉像原图、图表数据能改**的 FVS。

## 为什么需要这个 skill（核心洞察）

常规链路是「参考图 → agent 写 HTML 还原稿 → SVG → FVS」，但实测 **agent 写的 HTML 还原稿 SSIM 只有 0.41**（深蓝科技风乍看像，结构差很多）。走这条路，后面转什么格式都继承这个 0.41 的底子：

| 走 HTML 还原稿的方案 | 还原度 | 数据可改 |
| --- | --- | --- |
| 原生图表版 | 0.28 | ✅ |
| 图表切图版 | 0.29 | ❌ |
| HTML 还原稿本身 | 0.41 | - |

而「整图做底图」能到 0.97，但数据改不了。

**正解：绕开低还原的 HTML 还原稿，直接以原图为视觉底。**
1. 原图上把图表区精确擦除（周边面板色填充）—— 得到「擦除底图」
2. 擦除底图做 FVS 的底层图片（非图表区 100% 还原）
3. 叠加原生图表 widget + 数据集（图表区数据可改）
4. 实测可达 **0.87**，且 7 个图表全部能在帆软设计器里改数据

关键：HTML 还原稿这里**只用来提供图表**（它的 ECharts option 带完整数据和配色），不用来提供视觉。

## 输入契约

| 需要 | 来源 | 用途 |
| --- | --- | --- |
| 参考图（原图） | 用户提供 | 视觉底 + 擦除源 |
| HTML 还原稿（含 ECharts，静态可渲染） | `big-screen-design-brief` 产出 | 采集原生图表 + 数据集 |
| 转换引擎项目 | HTML转FVS应用 | 提供 `packages/engine/fvs.cjs` + jszip + sharp |

HTML 还原稿必须满足：ECharts 能独立渲染（chart JS 库路径正确、canvas 数量 > 0）。**这是最容易踩的坑，见 pitfalls。**

## 流程

设项目根目录为 `PROJ`（含 `packages/engine/fvs.cjs`、`node_modules`），所有 node 命令在 `PROJ` 下运行。

### 第 0 步：确认 HTML 还原稿的图表能渲染

```bash
# 用浏览器打开 HTML，确认 canvas 数量 = 期望图表数、window.echarts 已定义、无 pageerror
```
若 ECharts 未定义，通常是 HTML 引用的 `assets/echarts.min.js` 缺失或路径不对——补齐整目录资源再继续。可借用项目 `tools/svg-to-fvs.cjs --charts-from <HTML目录>`，它会报「采到 0 个图表」的警告。

### 第 1 步：生成「原生图表版 FVS」（只为拿图表组件）

用 HTML 还原稿 + 它的 SVG 设计源，走项目正常转换，关掉切图模式（`chartsAsSlices:false`），得到一份**带原生图表**的 FVS。这份 FVS 只要图表对，视觉难看没关系。

```bash
cd PROJ
node tools/svg-to-fvs.cjs <design-labeled.svg> <临时名> --charts-from <HTML还原稿目录>
```
确认产物里 `d-chart-*` 组件数 = 图表数、数据集非空。记下这份 FVS 路径为 `NATIVE_FVS`。

### 第 1.5 步：（推荐）量原图图表真实坐标

HTML 还原稿的图表坐标是歪的（还原稿本身 SSIM 0.41）。要用原图图表的**真实位置**：放大原图逐块量出每个图表的 x/y/w/h（原图像素），存成 `chart-coords.json`（格式见 references/measured-case.md）。传给第 2、3 步的脚本。

```bash
export FVS_ENGINE="$(pwd)/packages/engine/fvs.cjs"
node <skill>/scripts/erase-chart-regions.cjs <参考图> <NATIVE_FVS> <擦除底图.png> [chart-coords.json] [画布宽 画布高]
```
脚本自动从 `NATIVE_FVS` 读图表坐标，换算到参考图尺寸，用周边面板色填充擦除。画布宽高默认取 FVS 的 1920×1080。

### 第 3 步：合并成高还原可编辑 FVS

```bash
node <skill>/scripts/merge-editable-fvs.cjs <擦除底图.png> <NATIVE_FVS> <输出.fvs> [chart-coords.json] [画布宽 画布高]
```
产物 = 1 张擦除底图 + 全部原生图表，数据集原样保留。

### 第 4 步：验收（必须实机截图，不许自评）

装进帆软 `webapps/webroot/WEB-INF/reportlets/项目/…`，用项目 `tools/fvs-shot-named.cjs` 按 1920×1080 截图，再跑客观校验：

```bash
node tools/fvs-shot-named.cjs "项目/…/<输出名>.fvs" shot.png
python <big-screen-design-brief>/scripts/verify_reference_match.py \
  --reference <参考图> --render shot.png --threshold 0.70
```
得分 ≥ 0.70 且**人工看渲染图确认图表落在擦除区、无双影/黑边**才算完成。

## 关键坑（血泪）

1. **绝对不要手工 replace HTML 实体**：改 `editor.tpl` 的 `store` 属性时，手工 `&`→`&amp;` 等会产生 `&amp;amp;` 双重转义，帆软直接报「非常抱歉，出错了」。必须用 `fvs.readXML(raw)` 解码 → 改 JSON → `fvs.writeXML(root)` 写回。`merge-editable-fvs.cjs` 已封装正确做法。
2. **ECharts 库路径**：HTML 还原稿引用 `assets/echarts.min.js` 时，采集目录里必须真的有这个路径的文件，否则图表静默采到 0 个。
3. **擦除区与图表尺寸**：原生图表容器有 grid padding，内容比容器小。擦除区按容器尺寸擦可能露黑边。若右上等区域分数低，把擦除区按图表实际内容区收窄、填充色用面板纹理而非纯色。
4. **图表 parent 必须清空**：原生图表的 `parent` 指向 d-group，合并删掉 group 后图表成孤儿、帆软不渲染（图表区空白）。合并脚本已清空 parent 并把图表挂根。
5. **TableDataMap 必须保留原文**：`fvs.writeXML` 往返会破坏 RowData 的帆软私有逐行编码，图表读不到数据。合并脚本已用原文整段替换保护。
6. **只平移不缩放图表**：缩放图表 widget 会裁掉内部文字（65% 变 "65..."）。用坐标表时只把图表中心平移到目标区，保留原始 width/height。若要改图表大小须改内部 stringChartCollection 的 radius 等参数。
7. **未授权水印**：帆软未注册会显示「未注册功能」角标 + 图表区占位图标，正版设计器无此问题，不计入还原度归因。

## 依赖

- 项目引擎：`packages/engine/fvs.cjs`（导出 `readXML`/`writeXML`/`imageWidget`/`loadBases`）
- node 包：`jszip`、`sharp`（脚本用 `createRequire(FVS_ENGINE)` 从项目加载，无需在 skill 内安装）
- 校验：`big-screen-design-brief/scripts/verify_reference_match.py`（需 `pip install scikit-image pillow numpy`）
- 环境：帆软 8075 服务需启动（实机截图用）

## 一句话用法

> 用 **image-to-editable-fvs** 把这张参考图做成帆软大屏：要还原度高、图表能改数据。原图 `<path>`，HTML 还原稿 `<path>`，画布 1920×1080。

回报：实机 SSIM 分数、原生图表数、数据集是否非空、是否确认无双影/黑边。
