# 图层整理与导出标记 v6（Figma 插件）

配套技能：[figma-lanhu-export-marker](../SKILL.md)

## 安装

Figma 桌面版 → `Plugins → Development → Import plugin from manifest…` → 选本目录 `manifest.json`。

`manifest.id` 与 v5 相同，**v5 用户不用重装**，改名后重启一次 Figma 刷新列表即可。

## v6 相对 v5 的变化

| | v5 | v6 |
| --- | --- | --- |
| 素材清单 | 写死在 code.js（58 类，一鸣专用） | 三种来源：预设 / 粘贴 CSV / 按命名自动推断 |
| 多实例 | 同名只标第一个（91 个只标 58 个） | 后缀归一到基名，**每个实例都标** |
| 预览 | 无 | 「导出预览」先出 CSV，确认后再写 |
| 诊断 | 只报匹配数 | 分类、匹配类/实例数、缺失、未登记但像素材的图层 |
| 格式 | PNG / SVG 硬编码 | 清单里逐条声明，默认 PNG |

## 输入清单格式

```
# 注释行会被忽略
card__mini-metric,PNG
image__title-decoration,PNG
some-vector-asset,SVG
```

用 `scripts/build_manifest.py` 从设计源 SVG 直接生成，别手抄。

## 已知限制

- 素材总板默认不标记（避免蓝湖出现两套下载项）；要标就点「也标素材总板」
- 图层名被 Figma 完全拍平（没有 `data-name` 保留）时，只能靠「自动推断」的前缀规则
- 导出倍率固定 1x（大屏是 1:1 交付，2x 会让蓝湖下载项尺寸翻倍）
