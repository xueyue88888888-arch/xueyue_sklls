---
name: figma-lanhu-export-marker
description: 把设计源 SVG 导入 Figma 后，批量整理图层并给「该能下载的素材」全部打上 Export 标记，再交给蓝湖插件上传。当用户说「蓝湖里很多图下载不了 / 只有一张能下载 / 图层选不中 / 导入后切图不全 / 帮我标导出 / Figma 上传蓝湖」时使用。下游承接 html-screen-to-design-source 产出的 SVG。
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# Figma → 蓝湖 图层整理与导出标记

## 解决什么问题

设计源 SVG 拖进 Figma 后，**图层能看见 ≠ 能下载**。蓝湖只给"打了 Export 标记"的图层生成下载项。
手动一个个点，几十上百个图层根本不可行；而且同名素材有多个实例时，只标第一个是常见事故。

这个技能给一个 Figma 插件 + 一个清单生成器，把这件事变成三步：

```
设计源 SVG（带 data-export 属性）
   ↓  scripts/build_manifest.py       生成 name,FORMAT 清单
   ↓  插件里「载入清单」
   ↓  「导出预览」核对 → 「整理并标记」
Figma 里每个素材实例都带上 1x Export
   ↓  蓝湖插件 Web @1X
蓝湖标注页：可点选、可标注、每个实例都能单独下载
```

## 第 1 步：生成清单

```bash
python scripts/build_manifest.py design-source.svg --stats      # 先看规模和实例数
python scripts/build_manifest.py design-source.svg -o manifest.csv
```

输出格式（每行一条，`#` 开头为注释）：

```
# 素材清单：每行 name,FORMAT
card__mini-metric,PNG
china-map-base,PNG
image__title-decoration,PNG
```

规则：

- 读 `data-name` + `data-export` 两个属性 —— 这是 `html-screen-to-design-source` 的输出约定
- `card__mini-metric-12`、`card__mini-metric 12` 都会归一到 `card__mini-metric`
- 同一基名格式冲突时以第一个为准并告警

> 没有这两个属性？用插件里的「按命名自动推断」：认 `panelbg__ / card__ / icon__ / image__ / photo__ / chartref__ / china-map-` 前缀。

## 第 2 步：装插件

Figma 桌面版 → `Plugins → Development → Import plugin from manifest…` → 选 `plugin/manifest.json`。

插件完全离线，只改当前文件的 `exportSettings`，不联网、不落盘。

## 第 3 步：跑

| 按钮 | 作用 |
| --- | --- |
| **载入清单** | 用输入框里的清单（留空则用内置预设）|
| **按命名自动推断** | 不写清单也能跑，按图层名前缀识别 |
| **诊断** | 顶层节点分类、清单匹配类数/实例数、缺失与未登记图层 |
| **导出预览** | 先出「将要标记什么」的 CSV，**不写入任何标记** |
| **整理并标记** | 清旧标记 → 逐层写 `exportSettings` → 回读校验 |
| **也标素材总板** | 额外给素材板标导出（会产生重复下载项，一般不用）|
| **导出结果 CSV** | 把 Figma 里实际读到的 Export 导出来存档 |
| **清空旧标记 / 移除旧板** | 重来、清理历史资产板 |

正确顺序：**诊断 → 导出预览 → 整理并标记 → 导出结果 CSV → 蓝湖上传大屏稿这一张**。

## 命名约定（与上游一致，别改）

| 前缀 | 含义 | 例 |
| --- | --- | --- |
| `panelbg__` | 模块背景（底+切角+描边+发光）| `panelbg__agriculture` |
| `card__` | 卡片外壳（底+边框+切角+内发光+分隔线）| `card__sales-kpi` |
| `icon__` | 单个图标 | `icon__top-cow` |
| `image__` / `photo__` | 照片、主视觉、品牌图 | `photo__factory` |
| `chartref__` | 图表占位（**不导出**，由开发原生重建）| `chartref__sales__chart-forecast` |
| `china-map-*` | 地图分层（底图/流向/点位）| `china-map-glow` |

## 排错

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 蓝湖里只有个位数下载项 | 只标了每个基名的第一个实例 | 用 v6 插件，「整理并标记」会遍历所有实例 |
| 预览条数和实际标记数不一致 | 稿子里有同名图层被 Figma 加了 ` 1` 后缀 | 插件会归一后缀；仍不一致就重拖 SVG |
| 「清单和稿子一个都对不上」 | 图层名被 Figma 拍平/重命名 | 点「诊断」看子级样例；或改「自动推断」 |
| 标了但蓝湖还是没下载项 | 上传的是素材总板，或没进标注页 | 只上传大屏稿；到该稿的标注页验收 |
| 想要矢量而不是位图 | 清单里没有单独声明 | 清单里把该行写成 `name,SVG` |

## 与上下游的关系

```
big-screen-design-brief        → 任务书（画布/模块/四分类/出图 prompt）
agent 写 HTML                  → 固定画布 + 静态模式 + data-el 命名
html-screen-to-design-source   → 设计源 SVG（每层带 data-name + data-export）
figma-lanhu-export-marker      → 本技能：Figma 里批量标记 → 蓝湖可下载
帆软 / FVS 开发                → 按标注还原，图表用原生组件重建
```

## 一句话开工

> 用 **figma-lanhu-export-marker** 帮我把这个设计源在 Figma 里标好导出，我要传蓝湖。

我会先给你生成清单和实例统计（多少类、多少实例、哪些是多实例），再告诉你该怎么点。
