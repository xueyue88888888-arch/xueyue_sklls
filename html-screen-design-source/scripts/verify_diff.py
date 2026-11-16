#!/usr/bin/env python3
"""Pixel diff between the rendered HTML (baseline) and the assembled SVG.

Reports the three numbers that matter:
  - overall strong diff  (share of pixels with max-channel delta > threshold)
  - non-text strong diff (same, excluding padded text boxes)
  - worst regions, so you know where to look

Usage:
    python verify_diff.py --baseline render.png --candidate svg-preview.png \
        [--text geometry.json] [--threshold 60] [--top 12]
"""
import argparse
import json
import sys

import numpy as np
from PIL import Image


def load(path):
    return np.asarray(Image.open(path).convert('RGB'), dtype=np.int16)


def text_mask(shape, nodes, pad=4):
    mask = np.zeros(shape, dtype=bool)
    h, w = shape
    for n in nodes:
        x1 = max(0, int(n['x']) - pad); y1 = max(0, int(n['y']) - pad)
        x2 = min(w, int(n['x'] + n['w']) + pad); y2 = min(h, int(n['y'] + n['h']) + pad)
        mask[y1:y2, x1:x2] = True
    return mask


def clusters(delta, cell=8, min_px=6, threshold=60):
    """Coarse connected regions of strong difference."""
    strong = delta > threshold
    h, w = delta.shape
    gh, gw = h // cell, w // cell
    counts = strong[:gh * cell, :gw * cell].reshape(gh, cell, gw, cell).sum(axis=(1, 3))
    seen = np.zeros_like(counts, dtype=bool)
    mask = counts >= min_px
    out = []
    from collections import deque
    for y in range(gh):
        for x in range(gw):
            if not mask[y, x] or seen[y, x]:
                continue
            q = deque([(y, x)]); seen[y, x] = True; cells = []
            while q:
                cy, cx = q.popleft(); cells.append((cy, cx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < gh and 0 <= nx < gw and mask[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True; q.append((ny, nx))
            xs = [c[1] for c in cells]; ys = [c[0] for c in cells]
            weight = int(sum(int(counts[c]) for c in cells))
            out.append((weight, min(xs) * cell, min(ys) * cell,
                        (max(xs) + 1) * cell, (max(ys) + 1) * cell))
    return sorted(out, reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--baseline', required=True)
    ap.add_argument('--candidate', required=True)
    ap.add_argument('--text', default=None, help='geometry.json from measure_dom.py')
    ap.add_argument('--threshold', type=int, default=60)
    ap.add_argument('--top', type=int, default=12)
    args = ap.parse_args()

    a, b = load(args.baseline), load(args.candidate)
    if a.shape != b.shape:
        print('size mismatch: %s vs %s' % (a.shape, b.shape))
        sys.exit(2)

    delta = np.abs(a - b).max(axis=2)
    strong = delta > args.threshold
    print('overall   mean %.2f  strong %.2f%%' % (delta.mean(), 100 * strong.mean()))

    if args.text:
        nodes = json.loads(open(args.text, encoding='utf-8').read())
        nodes = nodes['text'] if isinstance(nodes, dict) else nodes
        tm = text_mask(delta.shape, nodes)
        print('text area   %5.1f%% of canvas   mean %5.2f  strong %5.2f%%' % (
            100 * tm.mean(), delta[tm].mean(), 100 * strong[tm].mean()))
        print('non-text    %5.1f%% of canvas   mean %5.2f  strong %5.2f%%' % (
            100 * (~tm).mean(), delta[~tm].mean(), 100 * strong[~tm].mean()))

    print('\nworst regions (x1,y1,x2,y2  strong px):')
    for w_, x1, y1, x2, y2 in clusters(delta, threshold=args.threshold)[:args.top]:
        print('  (%4d,%4d,%4d,%4d)  %5d   %dx%d' % (x1, y1, x2, y2, w_, x2 - x1, y2 - y1))


if __name__ == '__main__':
    main()
