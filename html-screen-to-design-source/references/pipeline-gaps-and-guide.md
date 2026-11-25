# 从 Skill 到可用 FVS：全程断点与通用性指南

用户目标：拿到 skill 后能做出好的分层 SVG，并直接用这个 SVG 引用在线服务转换成 FVS。本文系统列出这条路的断点、注意事项、通用性边界。2026-11-24 实测。

## 全链路（用户视角）

```
文字需求 / 参考图
  → [skill] 生成规范分层 SVG
  → 上传蓝湖（规范切图、评审、修改）
  → 把 SVG 上传在线服务 /api/convert
  → 得到 FVS
```

## 断点清单（按严重程度）

### ✅ P0（已解决）：SVG 上传服务后，图表数据丢失（"数据可改"是断的）

**现象**：用户按规范做出 SVG，图表层是 `chartref__*` 占位图（按设计源规范，图表不含数据）。上传服务转换后，FVS 里图表是**切图或空的，不能改数据**。

**根因**：
- `svg2fvs.cjs` 解析 `chartref` 时只存 `{name,x,y,w,h,buf,format}`（第95行），**SVG 不携带图表数据**。
- 原生图表数据来自 `chartsFrom`（一个本地 HTML 目录，用 Playwright 采 ECharts）。
- 服务端 `/api/convert` 的 `settings.chartsFrom` 默认 null；前端 `convert({id, textCarrier})` 根本不传 chartsFrom。

**结论**：在当前架构下，"用户只上传一个 SVG"永远拿不到数据可改的图表。要么图表是切图（不可改），要么空。

**已解决（2026-11-24）：SVG 内嵌图表数据。** 实现：
- 生成 SVG 时，为每个 chartref 图表的真实 ECharts option 做 base64，写到 `data-chart-option="..."` 属性。
- 工具：`scripts/inject_chart_options.py --svg <design.svg> --options <chart-options.json> --out <out.svg>`。
- `chart-options.json` 格式：`{"chartref__donut-xxx": {ECharts option对象}, ...}`，key 与 chartref 的 data-name 模糊匹配。
- svg2fvs 的 parseSvg 读出 option，图表采集区优先用它调 `fvs.nativeChart` 生成原生图表（数据可改），即使有 chartref 占位图也不再走切图。
- 实测：注入 1 个 option → 转换出 `charts:1, chartBlank:0`。服务端走同一 svg2fvs.run，自动生效。

**给 skill 的要求**：建 HTML 时图表用真实 ECharts（带数据），freeze 生成 SVG 后，把每个图表的 option 导出到 chart-options.json 并注入 SVG。这样用户拿到的是一个"自带数据、上传即转出可编辑图表"的 SVG。

### 🟠 P1：SVG 必须内嵌 base64 图片，不能用相对路径

**现象**：SVG 里 `<image href="assets/xxx.png">` → 转换后 `images:0`，图片全丢。

**根因**：svg2fvs 只认 `href="data:image/png;base64,..."`（第102行 `Buffer.from(b64[2],'base64')`），不认文件路径。

**注意事项**：skill 生成 SVG 必须把每张切图内嵌成 base64。代价是 SVG 体积大（实测 2-4MB，服务端 320MB 上限没问题，前端 200MB 上限没问题）。上传蓝湖也支持内嵌 base64 的 SVG。

### 🟠 P1：SVG→FVS 的文字承载选择会影响可维护性

文字有两种承载：`table`（报表块单元格）和 `text`（文本框/富文本）。服务端 convert 只传 `textCarrier`，默认 table。
- table：组件少、能编辑单元格，但文字位置受单元格网格约束
- text：位置更贴设计稿，但组件多
skill 应提示用户根据"要改文字"的诉求选；默认 table 即可。

### 🟡 P2：通用性边界——skill 对"输入类型"的适用度不同

| 输入 | 适用度 | 说明 |
| --- | --- | --- |
| 纯文字需求 | ⭐⭐⭐⭐⭐ | 最佳。从零画分层画布，每层原生独立，规范干净。 |
| 有设计稿源文件(PSD/Figma/SVG) | ⭐⭐⭐⭐ | 直接导出分层 SVG，最规范。 |
| 扁平参考图 | ⭐⭐ | 从成品图 inpaint 反推"独立面板底框"，信息已丢失，抠不干净(残影)。这是物理限制，不是代码 bug。 |

**必须告诉用户**：图片入口做不到"设计稿原生分层"的干净度。想要干净分层，最好是文字需求或从设计源文件导出。

### 🟡 P2：图层规范的完整落地

当前 skill 产出的 SVG 用的是"扁平 data-name 前缀"分组（panel-header/filter-bar/table-header/table-rows），而标杆 SVG 是"模块→6子层"分组（module-background/photos/card-backgrounds/charts/icons/text）。

**差距**：切图粒度够了（面板/图表/文字各自独立），但分组组织没到那套。对蓝湖切图影响不大（每个 image 仍独立），对"按模块管理图层"有差距。

**todo**：统一 label 脚本或加一个后处理，把扁平前缀重排成"模块→子层"结构。

### 🟢 P3：其他注意点

- **中文编码**：SVG 必须是 UTF-8。有次误判"中文乱码"是读文件用 GBK 解码，实际字节是正确 UTF-8。生成/读取统一 UTF-8。
- **sharp 渲染中文不可靠**：验证环境缺中文字体，sharp 把 SVG 渲染成 PNG 时中文消失，不能用它评估还原度。要用浏览器（有微软雅黑）或帆软实机截图。
- **服务状态**：在线服务要先启动（本地 25432 或线上 101.132.174.209:25432）；帆软实机验证要 8075 服务起来。
- **字体策略**：SVG 文字统一 `font-family="Microsoft YaHei"`，转换器会按字体白名单替换，保证帆软里不乱码。

## 给用户的 skill 使用建议（可直接写进 README）

1. 优先用文字需求或设计源文件，别指望从扁平图片得到干净的独立图层。
2. 图表层只放占位图；要数据可改，当前必须解决 P0（SVG 内嵌数据），否则上传服务后图表不可改。
3. SVG 图片一律内嵌 base64，不要相对路径。
4. 上传前用浏览器打开 SVG 确认显示正常（别用 sharp）。
5. 改设计只改 SVG 对应图层，重新上传转换即可——这是这套方案的核心维护价值。

## 优先级建议

P0 已实现（SVG 内嵌 data-chart-option → 原生图表）。剩余 todo：①skill 生成流程里自动导出图表 option 并注入（当前注入工具已有，需接进 SKILL.md 流程）；②P1/P2 质量和通用性问题。


## 2026-11-24 一键流水线端到端验证（最终）

`scripts/html_to_design_svg.py` 一条命令跑完全链路，已用真 ECharts HTML 端到端验证：
- 合格 HTML → 一键 → `design-layered.svg`（56 base64图 + 42真文字 + 8 chart data注入）→ svg2fvs → `charts:8, chartBlank:0, warnings:0`。

过程中修的 5 个真 bug（都已修进脚本）：
1. orchestrator 调 freeze2 传了目录而非 HTML 路径 → 抓不到图表。改为传 HTML 文件。
2. freeze2 输出 GBK 中文，subprocess utf-8 严格解码崩 → 加 errors='replace'。
3. chart-options.json 的 key（donut/gauge1）与 SVG data-name（chartref__donut）对不上 → freeze2 导出改用容器 data-name 作 key。
4. `data-chart-option` 挂在 `<g>` 上、引擎只从 `<image>` 读 → 引擎 parseSvg 支持从祖先 g 读 option。
5. preflight 把注释里的 "no mask" 当禁用 CSS → 先去注释再检查。

**给用户的捷径**：只要 HTML 合规（preflight 过），一条 `python html_to_design_svg.py --html ... --out ... --charts-dir ...` 就能产出可直接上传转换的合格 SVG。

---

## 2026-11-24 全链路审查：修掉的问题（实测）

用一份合规 HTML（1920×1080、13 个命名块、3 个 ECharts）跑通"HTML → SVG → 服务 → FVS"，沿途修了这些**会让结果看起来"成功"、实际不可用**的问题：

| 问题 | 症状 | 修法 |
| --- | --- | --- |
| 几何兜底死代码 | HTML 没写 `data-name` 时 `images=0`，只有文字 | `named_geom` 只统计命名节点；兜底仅在完全无命名时启用，且按面积取前 N |
| 无止损 | `images=0` 仍然 exit 0、报"无风险" | 退出码 3 + 排查清单；`--allow-empty-images` 可调试绕过 |
| 绘制顺序 | 卡片切图排在文字之后，76 段文字被盖住只剩 2 行 | 按角色排序：page-bg → 卡底/栏底 → chartref → 图标/图片 → 文字 |
| 卡片切图烘焙图表 | canvas 被截进卡底，与原生图表双影 | 非 chartref 任务在截图前隐藏 canvas |
| 索引错位 | 隐藏视图里的同名元素占位，切到 2×2 空图 | 按几何匹配选元素（容差 ≤8px），几何优先于 index |
| 图表采集器写死 | 只找某台机器的 `work/selftest/freeze2.cjs` | 自带 `scripts/export_chart_options.py`（只依赖 Playwright） |
| Infinity 破坏 JSON | option 含 `Infinity` → 消费端 `JSON.parse` 失败 → 图表静默变空 | 导出时清洗非有限值；注入端 `allow_nan=False`；引擎解析失败告警 |
| 注入器只认图片自身 data-name | 占位名在父 `<g>` 上，报"no chartref" | 维护 `<g>` 栈，按最近 chartref 组取名字 |
| 伪筛选控件 | 卡片说明文字被标 `filter-bar` → 13 个下拉 + 2 个日期 | 编排器按 HTML 里有无真实表单控件传 `--filters yes/no`；语义分层在无表格页面不再把正文标成表行 |
| 切图无节制 | 合规稿也被兜底切成 101 张 | 有命名时不做几何兜底 |

**验证数据**：合规 HTML → SVG `images=13 / texts=76 / chart-options=3`，与 HTML 像素 strong diff **2.26%**；上传服务后 `charts=3 / chartBlank=0 / controllers=3`（正好等于真实筛选控件数），FVS 全页底图包含全部卡片/标题栏/表格底。

**仍然存在的边界**：

1. **参考图入口没有可运行脚本**。`build_layered_from_image.py`、`text-input/`、`global-business/layered/` 在仓库里都不存在。让 agent 看着参考图新写 HTML，实测 SSIM 只有 **0.486**（门槛 0.70），5 轮迭代只从 0.430 提到 0.486。图片入口目前只能靠"人给设计源/文字需求"，或退回 `image-to-editable-fvs` 的"原图打底"方案（那条不产 SVG）。
2. **图层结构仍是扁平前缀**（`panel-header__001…`），没到"模块→6 子层"。切图粒度够、蓝湖可用，但按模块管理图层还差一步。
3. **筛选控件只是外观**：FVS 里 `parameterConfigs` 为空，下拉没有参数绑定；选项列表也无法从 SVG 还原（下拉当前值在 HTML 里不是文字）。
4. **`images=0` 是合规结果**：卡底/栏底按规范进全页底图，不再逐个成组件。要"每块可单独替换"，得改用 `panelbg__`/`card__` 命名并接受组件数上升。

---

## 2026-11-24 二次优化：规范结构互通 + 图片入口

### 规范 SVG 以前根本转不了（已修）

`references/design-source-layer-spec.md` 的目标结构和转换器是两套命名：规范用
`<use data-role="card-background" href="#asset_x">` + `data-role`，而 `svg2fvs.parseSvg`
只认满 `<image href="data:image/png;base64,…">` 且名字必须是 8 类前缀。结果：一份完全符合
规范的 SVG 上传后 `images 0 / charts 0`，只有文字能转。

现在解析器同时支持：`<defs><image id=…>` 资源、`<use href="#id">`、`data-role`
（`page-background / card-background / chart-reference / photo / icon` → 自动映射为
`page-bg__ / panelbg__ / chartref__ / photo__ / icon__`），模块分组只是容器，不影响取值。
实测：规范样例 SVG → `images 1 / charts 1 / texts 2 / chartBlank 0`，`data-chart-option`
在 `<use>` 上也能被读到。

### 扁平 → 模块 6 子层（可选，默认开）

`scripts/structure_layers.py`：把扁平组重排成 `页面底色` + `页头与筛选 / 内容模块 / 明细表`，
每个模块下按 `card-backgrounds / photos / charts / icons / text` 分子层。元素自身的
`data-name` 不动，所以转换器看到的文件与重排前完全一致——实测重排前后**像素差 0.000**，
图片/文字/图表数完全相同。`figma_compat.py` 同时放行这种"有 data-layer 子层的模块组"，
不再误报"wrapper groups hide selectable layers"。

### 图片入口：先量再画（新）

`detect_layout.py`（量）+ `build_layers_from_image.py`（inpaint + 分层）：

- 能量到的：画布、主色板、页面底色、**每一个文字框**（坐标/尺寸/近似字号/颜色）。1920×1080 大屏实测 215 个文字框。
- 量不到的：面板网格。深色大屏卡片填色只比底色高 3–5 个 RGB 级差，阈值/轮廓法要么把卡片并进背景，要么在每个字上炸开——所以**不做自动面板检测**，别用它硬猜。
- 文字串必须由看图的那一方给（本脚本不做 OCR，也不瞎编文案）。
- inpaint 掉文字框和图表区后再叠真 `<text>` 与 `chartref__` 占位：容器 run 与子 run 会自动二选一，避免同一行印两遍。

实测（1920×1080 参考图，文字串取自源 DOM 以保证口径）：188 段文字 + 21 个图表占位 → SVG
与参考图 **strong 2.09% / mean 3.91**，文字墨迹比 0.93（无重叠、无重复）；上传服务后
`charts 21 / chartBlank 0 / texts 188`，FVS 578 KB。
