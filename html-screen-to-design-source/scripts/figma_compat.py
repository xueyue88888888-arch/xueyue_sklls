#!/usr/bin/env python3
"""Audit an SVG (+ its asset folder) for design-tool import hazards.

Checks the exact six failure modes that break Figma / Lanhu / MasterGo imports:
  1. layers carrying `mask`                      -> layer silently dropped
  2. text with `fill="url(#...)"`                -> gradient text renders black
  3. `<use>` references                          -> copies lost or flattened
  4. duplicated base64 (`href` + `xlink:href`)   -> file size doubles
  5. non-RGBA / white-matted PNGs                -> white box behind the image
  6. wrapper groups that hide selectable layers  -> "I can only select the module"

Usage:
    python figma_compat.py --svg design.svg [--assets folder] [--max-wrapper-depth 1]

Exit code is non-zero when a blocking issue is found (good for CI).
"""
import argparse
import base64
import glob
import io
import re
import sys
from pathlib import Path

import numpy as np
import xml.etree.ElementTree as ET
from PIL import Image

NS = '{http://www.w3.org/2000/svg}'
WRAPPER_HINT = ('module', 'section', 'group', 'wrapper', 'container', '模块', '分组', '容器')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--svg', required=True)
    ap.add_argument('--assets', default=None, help='folder holding the sliced PNGs')
    args = ap.parse_args()

    raw = Path(args.svg).read_text(encoding='utf-8')
    root = ET.fromstring(raw)
    problems = []

    # 1) masks
    masks = sum(1 for e in root.iter() if e.get('mask'))
    mask_refs = len(re.findall(r'url\(#mask', raw))
    if masks or mask_refs:
        problems.append('mask: %d elements, %d refs — bake the masked result into a PNG'
                        % (masks, mask_refs))

    # 2) gradient text
    grad_text = [t for t in root.iter(NS + 'text') if (t.get('fill') or '').startswith('url(')]
    if grad_text:
        problems.append('gradient text: %d runs — replace with a solid fill' % len(grad_text))

    # 3) <use>
    uses = sum(1 for _ in root.iter(NS + 'use'))
    if uses:
        problems.append('<use>: %d — expand to <image> before delivery' % uses)

    # 4) duplicated base64
    dup = len(re.findall(r'xlink:href="data:', raw))
    if dup:
        problems.append('duplicated base64: %d images carry both href and xlink:href '
                        '(file size ~2x)' % dup)

    # 5) image formats / alpha
    bad_mode, bad_mime, white_matte = 0, 0, []
    for im in root.iter(NS + 'image'):
        href = im.get('href') or ''
        if not href.startswith('data:'):
            continue
        mime = href[5:href.index(';')]
        if mime != 'image/png':
            bad_mime += 1
            continue
        try:
            img = Image.open(io.BytesIO(base64.b64decode(href.split(',', 1)[1])))
        except Exception:
            continue
        if img.mode != 'RGBA':
            bad_mode += 1
            img = img.convert('RGBA')
        a = np.asarray(img)
        h, w = a.shape[:2]
        if h > 3 and w > 3:
            ring = np.concatenate([a[0, :, :], a[-1, :, :], a[:, 0, :], a[:, -1, :]])
            opaque = ring[:, 3] > 200
            white = opaque & (ring[:, :3].min(axis=1) > 235)
            if opaque.mean() > 0.95 and white.mean() > 0.6:
                white_matte.append(im.get('data-name') or im.get('id') or '?')
    if bad_mime:
        problems.append('non-PNG images: %d — export everything as PNG' % bad_mime)
    if bad_mode:
        problems.append('images without alpha: %d — convert to RGBA' % bad_mode)
    if white_matte:
        problems.append('white matte: %d layers look like an opaque white plate (%s)'
                        % (len(white_matte), ', '.join(white_matte[:5])))

    # 6) wrapper groups
    wrappers = []
    for g in root.iter(NS + 'g'):
        nm = (g.get('data-name') or g.get('id') or '')
        kids = [c for c in g if c.tag in (NS + 'g', NS + 'image', NS + 'text')]
        # A module/section group that holds data-layer sublayers is the required handoff
        # structure, not a stray wrapper.
        if (g.get('id', '').startswith(('section-', 'page-background'))
                or any(c.get('data-layer') for c in g)):
            continue
        if not g.get('data-export') and any(h in nm.lower() for h in WRAPPER_HINT):
            wrappers.append('%s(%d children)' % (nm, len(kids)))
    if wrappers:
        problems.append('wrapper groups hide selectable layers: %d — flatten them (%s)'
                        % (len(wrappers), ', '.join(wrappers[:5])))

    # 7) assets on disk
    if args.assets:
        idx = {}
        for f in glob.glob(str(Path(args.assets) / '**' / '*.png'), recursive=True):
            idx.setdefault(len(Path(f).read_bytes()), []).append(f)
        unmatched = 0
        for im in root.iter(NS + 'image'):
            href = im.get('href') or ''
            if not href.startswith('data:'):
                continue
            size = len(base64.b64decode(href.split(',', 1)[1]))
            if size not in idx:
                unmatched += 1
        if unmatched:
            problems.append('assets not on disk: %d embedded images have no matching file'
                            % unmatched)

    print('SVG: %s  (%.2f MB)' % (args.svg, len(raw.encode()) / 1048576))
    print('images %d | text %d | groups %d' % (
        sum(1 for _ in root.iter(NS + 'image')),
        sum(1 for _ in root.iter(NS + 'text')),
        sum(1 for _ in root.iter(NS + 'g'))))
    if not problems:
        print('\nOK — no design-tool import hazards found.')
        return 0
    print('\n%d issue(s) to fix:' % len(problems))
    for p in problems:
        print('  - ' + p)
    return 1


if __name__ == '__main__':
    sys.exit(main())
