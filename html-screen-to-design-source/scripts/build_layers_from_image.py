#!/usr/bin/env python3
"""Build a layered design SVG from a flat reference image + measured text boxes.

    python build_layers_from_image.py --image ref.png --layout layout.json \
        --text text.json [--charts charts.json] --out out/

Pipeline:
  1. inpaint every text box (and every chart box) out of the reference image,
     so the base picture carries no baked glyphs and no baked chart;
  2. emit `design-layered.svg`: one base image layer, real <text> layers, and
     `chartref__*` placeholders (with `data-chart-option` when data is given);
  3. write the base PNG next to it for traceability.

`text.json` (the strings come from a vision pass — this script never guesses copy):
    [{"x":18,"y":18,"w":192,"h":18,"text":"数据截止 2025-11-24 09:00","name":"filter-bar__hint",
      "fontSize":14,"color":"#8FA6C4","align":"left"}, ...]

`charts.json` (optional, position + ECharts option):
    [{"x":48,"y":400,"w":572,"h":290,"name":"chartref__bar","option":{...}}, ...]

Why inpaint: a screenshot has the glyphs baked into pixels. Overlaying real text
on top of them prints every label twice; leaving them baked means the design
source has no editable text at all.
"""
import argparse
import base64
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

SVG_HEAD = ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="0 0 %d %d">')
TEXT_GROUPS = {
    'panel-header': 'panel-header', 'filter-bar': 'filter-bar',
    'table-header': 'table-header', 'table-rows': 'table-rows',
    'title': 'panel-header', 'kpi': 'panel-header',
}


def esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def group_of(name):
    for key, group in TEXT_GROUPS.items():
        if str(name).startswith(key):
            return group
    return 'panel-header'


def inpaint(base, rects):
    if not rects:
        return base
    if cv2 is None:
        raise SystemExit('build_layers_from_image needs opencv: pip install opencv-python-headless')
    mask = np.zeros(base.shape[:2], np.uint8)
    for r in rects:
        x, y, w, h = [int(v) for v in (r['x'], r['y'], r['w'], r['h'])]
        pad = 2
        mask[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad] = 255
    return cv2.inpaint(base, mask, 3, cv2.INPAINT_TELEA)


def dedupe_runs(texts):
    """Keep either the container run or its leaf runs, never both.

    A DOM dump gives `.cp-title` ("人员数据罗盘 · 总体") and the spans under it
    ("人员数据罗盘", "总体", different colours). Printing both duplicates glyphs;
    splitting the container by width cuts numbers in half. If the leaves' copy adds
    up to the container's copy, emit the leaves (exact text, per-run colour);
    otherwise emit the container and drop the leaves.
    """
    def area(t):
        return float(t['w']) * float(t['h'])

    def inside(a, b):
        return (a['x'] >= b['x'] - 1 and a['y'] >= b['y'] - 1
                and a['x'] + a['w'] <= b['x'] + b['w'] + 1
                and a['y'] + a['h'] <= b['y'] + b['h'] + 1)

    def norm(s):
        return ''.join(str(s).split())

    dropped = set()
    for t in texts:
        kids = [c for c in texts if c is not t and inside(c, t)
                and area(c) < area(t) * 0.95 and norm(c.get('text'))]
        leaves = [c for c in kids if not any(k is not c and inside(c, k) for k in kids)]
        if not leaves:
            continue
        joined = ''.join(norm(c['text']) for c in sorted(leaves, key=lambda c: (c['y'], c['x'])))
        if joined == norm(t.get('text')):
            dropped.add(id(t))
        else:
            dropped.add(id(t))
            for leaf in leaves:
                if norm(leaf['text']) in norm(t.get('text')):
                    dropped.add(id(leaf))
    return [t for t in texts if id(t) not in dropped]


def png_b64(img):
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('ascii')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', required=True)
    ap.add_argument('--layout', required=True)
    ap.add_argument('--text', required=True)
    ap.add_argument('--charts', default=None)
    ap.add_argument('--out', required=True)
    ap.add_argument('--font', default='Microsoft YaHei')
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    layout = json.loads(Path(args.layout).read_text(encoding='utf-8'))
    texts = dedupe_runs(json.loads(Path(args.text).read_text(encoding='utf-8')))
    texts = [t for t in texts if str(t.get('text', '')).strip()]
    if not texts:
        raise SystemExit('text.json has no usable runs. The strings in a picture must be read by a '
                         'vision + OCR model; this script never invents copy. Run detect_layout.py, '
                         'let the model fill text.json, then re-run.')
    charts = json.loads(Path(args.charts).read_text(encoding='utf-8')) if args.charts else []

    width = int(layout['canvas']['width'])
    height = int(layout['canvas']['height'])
    img = Image.open(args.image).convert('RGB')
    if img.size != (width, height):
        img = img.resize((width, height), Image.LANCZOS)

    base = inpaint(np.array(img), list(texts) + list(charts))
    base_img = Image.fromarray(base)
    base_path = out / 'base-clean.png'
    base_img.save(base_path)

    parts = [SVG_HEAD % (width, height, width, height)]
    parts.append('  <g data-name="page-bg__main" data-export="PNG">'
                 '<image x="0" y="0" width="%d" height="%d" preserveAspectRatio="none" '
                 'href="data:image/png;base64,%s"/></g>'
                 % (width, height, png_b64(base_img)))

    for i, ch in enumerate(charts, 1):
        x, y, w, h = (int(ch['x']), int(ch['y']), int(ch['w']), int(ch['h']))
        name = ch.get('name') or ('chartref__chart-%d' % i)
        crop = img.crop((x, y, x + w, y + h))
        attr = ''
        if ch.get('option'):
            data = json.dumps(ch['option'], ensure_ascii=False)
            attr = ' data-chart-option="%s"' % base64.b64encode(data.encode('utf-8')).decode('ascii')
        parts.append('  <g data-name="%s" data-export="PNG">'
                     '<image x="%d" y="%d" width="%d" height="%d" preserveAspectRatio="none"%s '
                     'href="data:image/png;base64,%s"/></g>'
                     % (esc(name), x, y, w, h, attr, png_b64(crop)))

    buckets = {}
    for t in texts:
        buckets.setdefault(group_of(t.get('name', '')), []).append(t)
    for group, items in buckets.items():
        parts.append('  <g data-name="%s">' % group)
        for i, t in enumerate(items, 1):
            fs = float(t.get('fontSize') or max(8, float(t['h']) * 0.78))
            x, y, w, h = (float(t['x']), float(t['y']), float(t['w']), float(t['h']))
            align = t.get('align') or 'left'
            if align == 'center':
                tx, anchor = x + w / 2, 'middle'
            elif align == 'right':
                tx, anchor = x + w, 'end'
            else:
                tx, anchor = x, 'start'
            color = t.get('color')
            if not color:
                patch = np.array(img.crop((int(x), int(y), int(x + w), int(y + h)))).reshape(-1, 3)
                bright = patch[patch.max(axis=1) > 140]
                color = '#%02X%02X%02X' % tuple(int(v) for v in (
                    bright.mean(axis=0) if len(bright) else patch.mean(axis=0)))
            parts.append('    <text data-name="%s__%03d" x="%.2f" y="%.2f" font-size="%.2f" '
                         'font-family="%s" fill="%s" text-anchor="%s">%s</text>'
                         % (group, i, tx, y + h * 0.8, fs, esc(args.font),
                            esc(color), anchor, esc(t['text'])))
        parts.append('  </g>')

    parts.append('</svg>')
    svg = '\n'.join(parts)
    (out / 'design-layered.svg').write_text(svg, encoding='utf-8')

    print('base  %s (%.1f KB)' % (base_path.name, base_path.stat().st_size / 1024))
    print('svg   design-layered.svg (%.1f KB) | images %d | texts %d | charts %d'
          % (len(svg.encode('utf-8')) / 1024, len(charts) + 1, len(texts), len(charts)))


if __name__ == '__main__':
    main()
