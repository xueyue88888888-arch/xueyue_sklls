# skills

个人技能仓库（monorepo）—— 一个仓库放多个 agent skill，一个 clone 管全部。

每个技能是一个独立文件夹，文件夹根目录必有 `SKILL.md`（YAML frontmatter：`name` + `description`）。
其余内容（`scripts/`、`references/`、`examples/`）按需。

## 技能列表

| 技能 | 一句话 | 依赖 |
| --- | --- | --- |
| [big-screen-design-brief](big-screen-design-brief/) | 给一张参考图 → 拆元素 → 判定「CSS / 矢量 / AI 生成图 / 数据图表」→ 出可切图的大屏 HTML 任务书（含 AI 出图 prompt 模板） | image-gen（C 类素材） |
| [html-screen-to-design-source](html-screen-to-design-source/) | 把渲染好的 HTML 大屏转成分层、逐像素验收过的 SVG 设计源，可干净导入 Figma / 蓝湖 / MasterGo | playwright + numpy + pillow |

### 一条链路

```
一张参考图 + 业务数据
   ↓  big-screen-design-brief（拆元素 → 四分类 A/B/C/D → 任务书 + AI 出图 prompt）
Agent 产出 HTML 原型
   ↓  html-screen-to-design-source（静态化 → 量几何 → 切图 → 合成 SVG → 像素验收 → 工具兼容）
Figma / 蓝湖设计源
   ↓
开发（FVS / BI）按标注与切图落地
```

两块合起来解决的是：**设计师不写代码，也能从"一张参考图"走到"能交付的设计源"**。

关键分界：一张大屏里约 **90% 是 CSS 与矢量**，真正需要 AI 出图的通常只有 **5–7 张**（实景、航拍、产品摆拍）。
`big-screen-design-brief` 的核心动作就是先把这个比例分清楚，再开工。

> 想加新技能：新建文件夹 → 写 `SKILL.md` → 在 README 表格里加一行 → 提 PR / 直接 push。

## 安装 / 使用

### 同步到本机 agent（推荐）

```powershell
.\install.ps1                          # Windows：把每个技能同步进 Alma 技能目录
./install.sh                           # macOS / Linux
.\install.ps1 -Only html-screen-to-design-source   # 只同步一个
```

> 用复制而不是软链接：Alma 的技能扫描器不跟随 junction / symlink，链过去会"装了但看不见"。

### 整仓 clone（手动管理）

```bash
git clone https://github.com/xueyue88888888-arch/xueyue_sklls ~/skills-src

# 让 agent 用其中之一：把技能目录链接/拷贝到它扫描的位置
ln -s ~/skills-src/html-screen-to-design-source ~/.config/alma/skills/html-screen-to-design-source
# Windows: mklink /D "%USERPROFILE%\.config\alma\skills\html-screen-to-design-source" "%USERPROFILE%\skills-src\html-screen-design-source"
```

### 只装一个技能

```bash
npx skills add xueyue88888888-arch/xueyue_sklls@html-screen-to-design-source
```

### 直接问 agent

> 用 **html-screen-design-source** 处理这个稿：HTML 在 `<path>`，切图素材在 `<path>`，画布 `<W×H>`

## 约定

- **命名**：文件夹名 = 技能名（kebab-case），与 `SKILL.md` 里的 `name` 一致
- **frontmatter**：`name`、`description` 必填；`description` 要写成"什么时候该用我"，含触发短语
- **自包含**：技能不能假设仓库外的文件存在；需要外部规范时在 `references/` 里写明路径或直接内联
- **可验证**：有脚本的必须能 `python -m py_compile` 过；CI 会跑
- **不塞大文件**：截图/素材走外部路径或 `examples/`，单文件 > 1MB 提 issue 讨论

## CI

`.github/workflows/validate.yml`：每次 push 检查 —— 每个技能有 `SKILL.md` 且 frontmatter 完整、`name` 与目录名一致、所有 Python 脚本语法通过。

## License

MIT，见 [LICENSE](LICENSE)。各技能若需其他协议，在其目录内单独放 `LICENSE`。
