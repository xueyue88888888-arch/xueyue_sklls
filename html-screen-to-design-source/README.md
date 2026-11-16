# html-screen-to-design-source

An agent skill that turns a **rendered** HTML dashboard (fixed-canvas "big screen") into a
**layered, pixel-verified SVG design source** that imports cleanly into Figma, Lanhu,
MasterGo or any design-handoff tool.

Built from a real delivery: a 2752×1204 production dashboard with 40 cards, 35 icons,
11 charts, a layered China map and 191 live text runs, handed off to BI developers.

```
HTML + cut assets  →  static HTML  →  measured geometry  →  slices
                   →  layered SVG  →  pixel diff  →  design-tool audit  →  delivery
```

## Why this exists

Converting an HTML screen to a design source looks like "export an SVG". In practice the
failure modes are all silent:

- text layers land on top of each other because the page was measured mid-animation
- images come out with white boxes because the PNG had no alpha
- card borders and glows disappear because the slice was taken from a detached clone
- the whole background image vanishes in Figma because the layer carried a `mask`
- the headline turns black because it used gradient text
- only 1 of 16 identical cards is exportable because the exporter dedupes by name

This skill encodes the method that fixes all of them, plus the numbers used to accept the
result.

## Install

**As an Alma / Claude-style skill** (folder contains `SKILL.md`):

```bash
# this skill lives in a monorepo: one repo, one folder per skill
git clone https://github.com/xueyue88888888-arch/xueyue_sklls ~/skills-src
ln -s ~/skills-src/html-screen-design-source ~/.config/alma/skills/html-screen-to-design-source

# or install just this one
npx skills add xueyue88888888-arch/xueyue_sklls@html-screen-to-design-source
```

**Requirements**

```bash
pip install playwright numpy pillow
python -m playwright install chromium    # or point --browser at Edge/Chrome
```

## Use

Just ask in natural language:

> Use **html-screen-to-design-source** on this screen: HTML at `page/index.html`,
> cut assets at `assets/`, canvas `2752×1204`.

The agent will freeze the page, measure it, slice by element type, assemble the SVG,
verify with pixel diffs, audit design-tool compatibility, and report:

```
overall strong diff       1.91%
non-text strong diff      0.59%
export layers             94 (61 asset families)
file size                 12.5 MB
asset match rate         104/104 layers → 79 files, 0 unmatched
```

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/measure_dom.py` | dump rendered geometry of every img / background-image / block / text run |
| `scripts/slice_cards.py` | in-place card-chrome slices (text+icons removed, box expanded 1px) |
| `scripts/slice_charts.py` | split an ECharts canvas into base / connectors / markers + label JSON |
| `scripts/build_svg.py` | template assembler: clips, text-glow buckets, asset swap, dedupe, size fix |
| `scripts/verify_diff.py` | baseline-vs-candidate diff: overall / text / non-text strong%, worst regions |
| `scripts/figma_compat.py` | audits the six import-breaking features, non-zero exit for CI |
| `scripts/asset_index.py` | proves every embedded image exists on disk; writes the usage list |

## Method in one screen

1. **Freeze** — one `STATIC_MODE` flag kills timers, chart animations and self-animating
   effects; verify with two hashed renders.
2. **Measure** — Playwright at canvas size, DPR 1. Never hand-place from CSS.
3. **Slice by type** — in-place + 1px expansion for anything with an outer glow; bake
   `backdrop-filter`; empty chart `data` to split layers; photos as RGBA PNG.
4. **Assemble** — one idempotent build script from a clean base; one font stack; glows from
   style buckets; one `href` per image.
5. **Verify** — compare against the same page rendered with the same font; targets:
   overall strong < 2.5%, non-text < 1%, text placement median < 2px.
6. **Adapt** — bake masks / CSS filters / gradient text, expand `<use>`, flatten wrapper
   groups, RGBA everything, mark every export instance.
7. **Package** — asset folders, usage list, hash traceability, self-check report.

## Repository layout

```
SKILL.md                      the skill itself (agent-facing instructions)
references/pitfalls.md        ranked failure modes with symptom → cause → fix
references/compat-matrix.md   SVG feature × design tool support table
scripts/                      runnable starting points
examples/config.example.json  config for build_svg.py
```

## Limitations

- Built and validated on **Chromium/Edge**; Firefox/Safari sub-pixel rounding differs.
- The chart splitter assumes **ECharts** (`echarts.getInstanceByDom`). For Chart.js or
  canvas-based charts, adapt the "empty the data" idea to that library's API.
- Font substitution always leaves glyph-shape differences; the verifier separates those
  from real layout errors instead of pretending they are zero.
- `backdrop-filter` cannot be reproduced in SVG — that slice must be baked.

## License

MIT — see [LICENSE](LICENSE).

Contributions welcome, especially: adapters for other chart libraries, a MasterGo/Pixso
compat table, and CI recipes that run `figma_compat.py` on every build.
