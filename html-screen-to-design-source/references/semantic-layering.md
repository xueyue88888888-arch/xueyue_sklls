# 语义分层：给未命名的 SVG 打 data-name

## 什么时候用

上游 agent 直接吐出的 SVG（或内嵌在 HTML 里的 SVG）通常**没有 `data-name`**：所有 `<text>`、`<rect>` 都堆在一起。下游的 SVG→FVS 转换器只能靠坐标猜哪是表头、哪是数据行、哪是底色——猜错就出现表头竖排、数据折行、背景丢失。

`scripts/label_svg_semantics.py` 用空间聚类把散元素分进语义组，只加 `data-name`，不改任何坐标 / 颜色 / 文字。

## 用法

```bash
python scripts/label_svg_semantics.py \
  --in  path/to/agent-output.html \
  --out work/labeled-design-source.svg
```

输入可以是纯 SVG，也可以是内嵌了一个 `<svg>` 的 HTML（agent 常把 SVG 包在 `<div>` 里交付）。脚本会抽出那段 SVG 再处理。

输出形如：

```xml
<svg width="1920" height="1080">
  <g data-name="page-bg"><rect data-name="page-bg__001" .../></g>
  <g data-name="panel-header"><text data-name="panel-header__001">健康证异常明细</text>...</g>
  <g data-name="table-header"><text data-name="table-header__001">工号</text>...</g>
  <g data-name="table-rows"><text data-name="table-rows__001">02381</text>...</g>
  <g data-name="table-bg"><rect data-name="table-bg__001" .../></g>
</svg>
```

## 分组规则（按空间，不靠猜文字）

| 组 | 识别方式 |
|---|---|
| `page-bg` | 覆盖画布 ≥80% 宽、≥70% 高的 rect |
| `panel-header` | 第一条横向分隔线（细长 rect）之上的文字 |
| `filter-bar` | 分隔线与主表格之间的文字 |
| `table-header` | 主表格区域内第一行文字 |
| `table-rows` | 主表格区域内后续文字，按行编号 |
| `table-bg` | 主表格区域内的行底 rect 与大表格框 |
| `other` | 其余图标 / 按钮 / 未归类元素 |

“主表格区域”= 宽度 ≥80% 画布、高度 ≥40% 画布的最大 rect。

## 实测

在某乳品企业「健康证异常明细」两页上：

```
04_下钻C_模块内展开.html → page-bg:3  panel-header:6  table-header:10  table-rows:96  table-bg:12
05_下钻C_无筛选版.html   → page-bg:4  panel-header:6  table-header:6   table-rows:90  table-bg:11
```

`table-rows` 数量与手工分层版一致（96 / 90），证明行聚类可靠。

## 局限

- 依赖画布尺寸写死在 `<svg width height>`；agent 必须输出固定画布（这是上游 7 条硬约束之一）。
- `filter-bar` 与 `table-header` 的边界靠"主表格 rect 的上沿"判断。若 agent 把筛选栏画在表格 rect 内部，会被并进 `table-header`——结果仍可用（都是短文本行），只是分组名不够精确。
- 不识别图表：ECharts / canvas 图表应走 `slice_charts.py`，本脚本只处理 SVG 原生元素。

## 与 SVG→FVS 的配合

分层后的 SVG 交给本站「SVG → 帆软 FVS」工具时，转换器会优先按 `data-name` 前缀理解结构：

- `table-header__*` → 独立横排文字组件
- `table-rows__*` → 原生表格单元格（带数据集绑定）
- `table-bg__*` → 表格底色
- `panel-header__*` → 标题文字

所以**先跑这个脚本分层，再转 FVS**，是把"看起来对"变成"能编辑、不折行"的关键一步。

## 上游 HTML 的双写命名契约

脚本分层是兜底，不是理由。上游 HTML 每个可视块应**同时写 `data-el` 和 `data-name`**：

| 设计元素 | data-el | data-name 前缀 |
| --- | --- | --- |
| 页面/面板底 | `page-bg` / `panelbg__*` | `page-bg__` |
| 标题栏 | `titlebar` | `panel-header__`（标题文字）或 `title-bar-bg__`（栏底） |
| KPI 卡 | `card__kpi` | `panel-header__`（KPI 文字）或 `title-bar-bg__`（卡底） |
| 筛选框 | `filter` / `filter-item` | `filter-bar__` / `filter-bar-bg__` |
| 查询按钮 | `query` / `btn-query` | `filter-bar__`（含“查询”文字） |
| 表格 | `table` | `table-header__` / `table-rows__` / `table-bg__` |
| 图表容器 | `chart` / `chart__<type>` | （图表由 chartsFrom 采集，SVG 里留位置） |

**为什么**：下游 svg2fvs 只读 `data-name` 的 8 类白名单前缀（page-bg / title-bar-bg / filter-bar-bg / table-bg / panel-header / filter-bar / table-header / table-rows）；不写 `data-name` 就靠几何猜，命中率下降。只写了 `data-el` 的元素，本脚本会按 `SEMANTIC` 别名宽表推导，但最终 SVG 上应落成白名单前缀；`card__*` / `panelbg__*` / `bg-top` 这类图片语义名由桥接脚本直接写入 `<image data-name>`，不要再交给本脚本重命名。
