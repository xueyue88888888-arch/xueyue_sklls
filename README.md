# skills

个人技能仓库（monorepo）—— 一个仓库放多个 agent skill，一个 clone 管全部。

每个技能是一个独立文件夹，文件夹根目录必有 `SKILL.md`（YAML frontmatter：`name` + `description`）。
其余内容（`scripts/`、`references/`、`examples/`）按需。

## 技能列表

| 技能 | 一句话 | 依赖 |
| --- | --- | --- |
| [html-screen-to-design-source](html-screen-to-design-source/) | 把渲染好的 HTML 大屏转成分层、逐像素验收过的 SVG 设计源，可干净导入 Figma / 蓝湖 / MasterGo | playwright + numpy + pillow |

> 想加新技能：新建文件夹 → 写 `SKILL.md` → 在 README 表格里加一行 → 提 PR / 直接 push。

## 安装 / 使用

### 整仓 clone（推荐给自己用）

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
