# Pitfalls, ranked by the cost of hitting them

Every entry below is a real failure from a production delivery, in the order the pain
was felt.

---

## 1. Measuring a page that is still animating

**Symptom** — a card's header row and its first data row render on top of each other in
the design source. Values are stale too.

**Cause** — the list was measured while a `transform: translateY(...)` insert animation
was mid-flight, so every row's `y` was off by ~11–13px. Values were captured from the
previous data cycle.

**Fix** — freeze the runtime first (static mode), then measure. Verify with two renders
+ hash compare.

**Cost if missed** — the whole text layer set for that component is unusable; you find
out only when a human opens the preview.

---

## 2. Slicing to RGB / JPEG

**Symptom** — a bright white rectangle in a dark UI, or a white halo around an icon.

**Cause** — the PNG had no alpha channel (`mode == 'RGB'`), or the capture ran with
`omit_background=False` so the page's default white got baked in.

**Fix** — every asset: RGBA PNG, captured with `omit_background=True` after clearing the
page / panel / sibling backgrounds. Then scan each asset for an opaque near-white border
ring; >60% white on the ring means redo it.

**Cost if missed** — invisible in the browser render (the slice is drawn over a dark
backdrop anyway), glaring the moment someone exports a single layer.

---

## 3. Cloning a card onto a blank canvas to "clean" it

**Symptom** — the card keeps its dividers but loses its outer border glow.

**Cause** — two separate things were thrown away:
(a) the border came from an ancestor selector (`.row .card { border: … }`), which a
detached clone no longer matches;
(b) the visible edge glow was the card's anti-aliased edge blending with the photograph
behind it — physically impossible to reproduce on a transparent canvas.

**Fix** — capture **in place**: leave the page exactly as rendered, globally set text to
`transparent`, hide icon imagery, crop the element box **expanded by 1px**, and place the
PNG at `(x-1, y-1)` with size `+2`. Cloning is only allowed for elements whose styling is
fully self-contained (and then it buys you one reusable asset).

**Cost if missed** — "the border glow is gone" reports, one card at a time.

---

## 4. `series[i].show = false` to split chart layers

**Symptom** — the "base only" and "markers only" captures come out identical.

**Cause** — ECharts ignores `show: false` for some series types (lines, scatter) after the
initial render, and still repaints them.

**Fix** — drive `data`: `setOption({ series: [{ id, data: [] }] }, { lazyUpdate: false })`
for the layers you want hidden, and restore `data` for the layer you want. Same for the
geo component: `geo: [{ show: false }]` works, but only when the series data is empty too.

**Cost if missed** — you bake two identical layers, notice nothing, and the "split" is
cosmetic.

---

## 5. Writing both `href` and `xlink:href`

**Symptom** — a 12MB design source that should be 6MB; uploads time out or exceed a
gateway limit.

**Cause** — every embedded base64 image was written twice for compatibility.

**Fix** — write `href` only. Modern browsers, Figma and Lanhu all read it.

**Cost if missed** — invisible until someone tries to send the file.

---

## 6. De-duplicating by deleting "duplicate" groups

**Symptom** — after a "cleanup" pass, 16 cards and their content vanish from one module.

**Cause** — a dedupe pass removed nodes sharing an `id`, but the pair was not a safe copy:
the surviving node was the parent of the removed one (or vice versa), so the subtree went
with it.

**Fix** — never dedupe by id blindly. Compare the subtree (position + payload) first, and
rebuild from a clean base instead of repairing a damaged file.

**Cost if missed** — the file still renders "mostly fine", which is worse than an obvious
break: you ship a module that is silently empty in places.

---

## 7. Putting a map (or any "reference" art) inside a non-exporting group

**Symptom** — the map base image is visible in the browser but cannot be selected or
downloaded in Lanhu.

**Cause** — the map was nested under a layer named `chartref__*` (a "chart position
reference", deliberately excluded from exports).

**Fix** — promote every asset that a human should be able to grab into its own named,
export-marked group at the root.

**Cost if missed** — "the base map isn't recognised" — the reader simply cannot use it.

---

## 8. Trusting the plugin to "mark everything"

**Symptom** — 91 exportable layers exist, only 58 show up as downloads.

**Cause** — the exporter matched by exact layer name and kept the first hit, treating the
other 33 as duplicates.

**Fix** — normalize names (strip the tool's ` 1` suffix, then your own `-N` instance
suffix) and mark **every instance**. Verify by re-running the same matching rule over the
SVG before handing it over.

**Cost if missed** — everyone downstream thinks the design source is incomplete.

---

## 9. Judging quality by eye

**Symptom** — long rounds of "still not right", each fix breaking something else.

**Cause** — no baseline, no number. Every round was judged on a thumbnail.

**Fix** — baseline = the same page rendered with the same substituted font; report
`overall strong diff`, `non-text strong diff`, and per-text-run placement offsets. Fix
what the numbers point at, re-measure, and only then ask a human to look.
