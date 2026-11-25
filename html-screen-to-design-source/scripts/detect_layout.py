#!/usr/bin/env python3
"""Measure a flat reference screenshot: palette, background, and text boxes.

    python detect_layout.py --image ref.png --width 1920 --height 1080 --json layout.json

What it can measure objectively:
  * canvas size, page background, dominant palette
  * every text run's bounding box, colour and approximate font size

What it deliberately does NOT do: guess the panel grid. On a dark dashboard the
card fill sits 3-5 RGB levels above the page, so threshold/contour detection
either merges cards with the background or splits them at every glyph. Text is
the only high-contrast structure, and it is reliable.

Downstream: a vision pass reads the strings for these boxes, then
`build_layers_from_image.py` inpaints the text out and emits a layered SVG whose
copy is editable.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


def hex_of(rgb):
    return '#%02X%02X%02X' % tuple(int(max(0, min(255, v))) for v in rgb[:3])


def palette(arr, k=6):
    small = arr[::4, ::4].reshape(-1, 3)
    quant = (small // 16 * 16).astype(np.uint8)
    colors, counts = np.unique(quant, axis=0, return_counts=True)
    order = np.argsort(-counts)[:k]
    total = counts.sum()
    return [{'color': hex_of(colors[i]), 'share': round(float(counts[i]) / total, 3)} for i in order]


def text_boxes(arr):
    if cv2 is None:
        raise SystemExit('detect_layout needs opencv: pip install opencv-python-headless')
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    mask = (gray > 110).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)

    boxes = []
    h_img, w_img = gray.shape
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        if area < 25 or h < 8 or h > 64 or w < 4 or w > 900 or w / max(1, h) > 30:
            continue
        boxes.append([int(x), int(y), int(w), int(h)])

    boxes.sort(key=lambda b: (b[1], b[0]))
    lines = []
    for x, y, w, h in boxes:
        for line in lines:
            if abs(line['y'] - y) <= max(6, h * 0.5) and x - line['x2'] < max(20, h * 2.2) \
                    and x >= line['x'] - 6:
                line['x2'] = max(line['x2'], x + w)
                line['y2'] = max(line['y2'], y + h)
                line['n'] += 1
                break
        else:
            lines.append({'x': x, 'y': y, 'x2': x + w, 'y2': y + h, 'n': 1})

    out = []
    for line in lines:
        w = line['x2'] - line['x']
        h = line['y2'] - line['y']
        if w < 8 or h < 8:
            continue
        patch = arr[line['y']:line['y2'], line['x']:line['x2']].reshape(-1, 3)
        bright = patch[patch.max(axis=1) > max(120, np.percentile(patch.max(axis=1), 85))]
        color = bright.mean(axis=0) if len(bright) else patch.mean(axis=0)
        out.append({
            'x': int(line['x']), 'y': int(line['y']), 'w': int(w), 'h': int(h),
            'fontSize': round(h * 0.78, 1),
            'color': hex_of(color),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', required=True)
    ap.add_argument('--width', type=int, default=0)
    ap.add_argument('--height', type=int, default=0)
    ap.add_argument('--json', default='layout.json')
    args = ap.parse_args()

    img = Image.open(args.image).convert('RGB')
    if args.width and args.height and img.size != (args.width, args.height):
        img = img.resize((args.width, args.height), Image.LANCZOS)
    arr = np.array(img)
    h, w = arr.shape[:2]

    text = text_boxes(arr)
    mask = np.ones((h, w), bool)
    for t in text:
        mask[t['y']:t['y'] + t['h'], t['x']:t['x'] + t['w']] = False
    bg = np.median(arr[mask].reshape(-1, 3), axis=0) if mask.any() else np.median(arr.reshape(-1, 3), axis=0)

    layout = {
        'canvas': {'width': w, 'height': h},
        'background': hex_of(bg),
        'palette': palette(arr),
        'text': text,
    }
    dest = Path(args.json)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(layout, ensure_ascii=False, indent=1), encoding='utf-8')
    print('canvas %dx%d | text runs %d | background %s -> %s' % (w, h, len(text), layout['background'], dest))


if __name__ == '__main__':
    main()
