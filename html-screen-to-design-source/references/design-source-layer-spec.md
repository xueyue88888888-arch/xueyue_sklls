# 设计源 SVG 图层规范（以某乳品企业会员大屏为标杆）

在真实项目上验证过的规范结构。标杆样本是一个 2752×1204 的暗色数据大屏：页面底色 + 页头/内容/明细表三段，每段下 6 个子层，切图与文字全部可编辑。

## 核心原则

**不是一整张图。** SVG 按「模块 → 子层」组织，每层是可独立选择/替换的组件。文字永远是真实 `<text>`，绝不切进图片。图表是占位（`data-role="chart-reference"`），不含真实数据——数据在转 FVS 时用原生图表替换。

## 层级结构

```
<g id="page-background" data-name="页面底色">        ← 整屏纯底色（1张）
<g id="section-header" data-name="页头与顶部指标">
  <g id="header-backgrounds">      ← 页头背景/品牌
  <g id="header-metric-backgrounds"> ← 顶部指标舱背景
  <g id="header-icons">            ← 图标
  <g id="header-text">             ← 真实文字
<g id="section-<模块名>" data-name="XX模块">
  <g id="<m>-module-background">   ← 模块背景边框（不含内容！）
  <g id="<m>-photos">              ← 照片/主视觉
  <g id="<m>-card-backgrounds">    ← 指标卡/图表卡底框
  <g id="<m>-charts">              ← 图表位置参考（占位，不含数据）
  <g id="<m>-icons">               ← 业务图标
  <g id="<m>-text">                ← 文字与数据（真实text）
```

每个模块都是同一套 6 个子层。缺的就省略，不塞进别的层。

## 元素写法

**背景/卡片/图表占位** 用 `<use>` 引用 `<defs>` 里的图：

```xml
<defs>
  <image id="asset_011" .../>  <!-- 或 base64 -->
</defs>
<use href="#asset_011" x="15" y="192" width="735" height="499"
     data-asset="module-agriculture.png" id="card-xxx"
     data-role="card-background"/>
```

`data-role` 取值：`page-background` / `card-background` / `chart-reference` / `photo` / `icon`。

**文字** 用真实 `<text>`：

```xml
<text id="text-000" x="1376" y="34" fill="rgb(237,248,255)"
      font-family="Microsoft YaHei, PingFang SC, Segoe UI"
      data-name="panel-header__xxx">全球业务态势</text>
```

## 为什么这样分

- **可维护**：改图表不动面板底框；改文案不动背景；换一张底图不影响文字层。
- **蓝湖规范切图**：每个 `<use data-role="card-background">` 是一个独立切图，蓝湖里是一层层可选组件，不是一张扁平截图。
- **SVG→FVS 忠实**：转换器按层读——`card-background` 落成 d-image、`text` 落成文字、`chart-reference` 落成原生图表占位。

## 关键红线

1. 面板背景层里**不能有图表和文字**（inpaint 抠掉），否则后面叠原生图表/文字会双影。
2. 图表层只是**位置占位**，不能把原图的图表像素切进去当"图表"——那样数据不可改，违背可编辑原则。
3. 文字必须是 `<text>`，不能是 `<image>` 里的像素。
4. 大背景是**纯底色/纹理**，不含任何模块或内容。
