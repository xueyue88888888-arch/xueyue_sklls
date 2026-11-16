# Design-tool compatibility matrix

What survives an SVG import, what gets dropped, and what to do instead.

Tested against **Figma desktop** (SVG import + the Lanhu upload plugin) and **Lanhu**
(蓝湖) design-source upload. MasterGo / Pixso behave like Figma for the items below;
verify per version.

| SVG feature | Figma import | Lanhu (via Figma) | Recommended handling |
| --- | --- | --- | --- |
| `<image>` with `data:image/png;base64,…` | ✔ becomes an image fill | ✔ | keep, one `href` only |
| `<image>` with `href` **and** `xlink:href` | ✔ | ✔ | don't — file size doubles |
| `<image>` inside `<g clip-path>` | ✔ (clip becomes a frame clip) | ✔ | fine for photos |
| `<g mask="url(#…)">` | ✖ mask lost, layer often dropped | ✖ | **bake the masked result into the PNG** |
| `filter="url(#feDropShadow)"` on text | ✖ ignored (text still imports) | ✖ ignored | acceptable; bake if the glow is structural |
| `filter` / `feGaussianBlur` on a vector group | ✖ group may be dropped | ✖ | bake at 2× into a PNG |
| `fill="url(#grad)"` on `<text>` | ✖ renders solid black | ✖ | use a solid colour |
| `fill="url(#grad)"` on a `<path>`/`<rect>` | ✔ | ✔ | fine |
| `<use href="#id">` | ✖ copies lost or flattened | ✖ | **expand to `<image>` before delivery** |
| CSS `style="filter: brightness(…)"` | ✖ ignored | ✖ | bake the filter into the PNG |
| CSS `backdrop-filter` | ✖ | ✖ | bake the backdrop into the slice |
| `opacity` attribute | ✔ | ✔ | fine |
| `<text>` with `font-family` not installed | ✔ substituted, metrics shift | ✔ | pick a font both sides have; document it |
| Deep wrapper `<g>` (module → group → card) | ✔ but you must double-click to reach children | ✖ "can only select the module" | **flatten wrappers**; elements at root |
| 300+ root-level elements | ✔ | ✔ | preferred over deep nesting |
| Duplicate layer names | ✔ renamed with ` 1`, ` 2` | ✔ | normalize when matching by name |
| `id` with Chinese characters | ✔ | ✔ | fine, but avoid `/` |
| `data-name` / `data-export` attributes | ignored (kept as custom data) | ignored | use them for your own tooling only |

## Delivery checklist (run `scripts/figma_compat.py`)

- [ ] 0 `mask` references
- [ ] 0 gradient-filled `<text>`
- [ ] 0 `<use>` elements
- [ ] 0 images with duplicate `href` + `xlink:href`
- [ ] 100% of embedded images are RGBA PNG
- [ ] 0 assets with an opaque near-white border ring
- [ ] no wrapper groups hiding selectable layers
- [ ] every image baked byte-exists in the asset folder

## Export marking (Figma → Lanhu)

- Mark **every instance** of a repeated asset, not just the first:
  normalize `layer-name 3` → `layer-name`, `layer-name-3` → `layer-name`, then export-mark
  all matches.
- Names must be unique after normalization, or Lanhu shows duplicate download entries.
- Keep one export format per asset family; mixing PNG and SVG in one family confuses the
  download list.
