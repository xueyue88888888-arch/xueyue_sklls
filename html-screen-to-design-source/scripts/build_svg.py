#!/usr/bin/env python3
"""Template: assemble the design-source SVG from a clean base + sliced assets.

Copy this file, edit CONFIG, run it. Re-run it after every asset change — never
hand-patch the output. Everything here is idempotent.

Design rules baked in:
  * one font stack for all text, glows mapped from style buckets (not per-run guesses)
  * one `href` per image (never href + xlink:href — that doubles the file)
  * images stored as RGBA PNG, optional <defs>+<use> reuse while iterating
  * optional effects (clip / mask / css filter) applied only in "browser mode";
    delivery mode bakes them into the PNG instead

Usage:
    python build_svg.py --config config.json -o design.svg
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path

import xml.etree.ElementTree as ET

NS = 'http://www.w3.org/2000/svg'
NSM = '{%s}' % NS
ET.register_namespace('', NS)


# ---------------------------------------------------------------- helpers
def load_base(path):
    tree = ET.parse(path)
    return tree, tree.getroot()


def defs_of(root):
    d = root.find(NSM + 'defs')
    if d is None:
        d = ET.Element(NSM + 'defs')
        root.insert(0, d)
    return d


def add_clip(defs, cid, x, y, w, h):
    cp = ET.SubElement(defs, NSM + 'clipPath')
    cp.set('id', cid); cp.set('clipPathUnits', 'userSpaceOnUse')
    r = ET.SubElement(cp, NSM + 'rect')
    for k, v in (('x', x), ('y', y), ('width', w), ('height', h)):
        r.set(k, '%.3f' % float(v))


def add_linear(defs, gid, x1, y1, x2, y2, stops):
    g = ET.SubElement(defs, NSM + 'linearGradient')
    g.set('id', gid); g.set('gradientUnits', 'userSpaceOnUse')
    for k, v in (('x1', x1), ('y1', y1), ('x2', x2), ('y2', y2)):
        g.set(k, '%.3f' % float(v))
    for off, colour, opacity in stops:
        s = ET.SubElement(g, NSM + 'stop')
        s.set('offset', str(off)); s.set('stop-color', colour)
        s.set('stop-opacity', str(opacity))


def add_glow(defs, fid, blur, colour, opacity):
    f = ET.SubElement(defs, NSM + 'filter')
    f.set('id', fid)
    for k, v in (('x', '-25%'), ('y', '-40%'), ('width', '150%'), ('height', '180%')):
        f.set(k, v)
    d = ET.SubElement(f, NSM + 'feDropShadow')
    d.set('dx', '0'); d.set('dy', '0')
    d.set('stdDeviation', '%.2f' % (float(blur) / 2.0))
    d.set('flood-color', colour); d.set('flood-opacity', str(opacity))


def data_uri(path):
    from io import BytesIO
    from PIL import Image
    raw = Path(path).read_bytes()
    try:
        im = Image.open(BytesIO(raw))
        if im.mode != 'RGBA':
            buf = BytesIO()
            im.convert('RGBA').save(buf, format='PNG')
            raw = buf.getvalue()
    except Exception:
        pass
    return 'data:image/png;base64,' + base64.b64encode(raw).decode('ascii')


def put_image(group, path, x, y, w, h):
    im = group.find(NSM + 'image')
    if im is None:
        im = ET.SubElement(group, NSM + 'image')
    uri = data_uri(path)
    im.set('x', '%.2f' % x); im.set('y', '%.2f' % y)
    im.set('width', '%.2f' % w); im.set('height', '%.2f' % h)
    im.set('preserveAspectRatio', 'none')
    im.set('href', uri)
    return im


def walk_groups(node, out=None):
    out = [] if out is None else out
    for ch in node:
        if ch.tag == NSM + 'g':
            out.append(ch)
            walk_groups(ch, out)
    return out


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True, help='JSON config (see CONFIG in the skill)')
    ap.add_argument('-o', '--out', required=True)
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text(encoding='utf-8'))

    tree, root = load_base(cfg['base_svg'])
    defs = defs_of(root)

    if cfg.get('font_family'):
        for t in root.iter(NSM + 'text'):
            t.set('font-family', cfg['font_family'])

    # 1) clips (browser mode only — delivery bakes them into the PNG)
    for c in cfg.get('clips', []):
        add_clip(defs, c['id'], c['x'], c['y'], c['w'], c['h'])
        for g in walk_groups(root):
            if (g.get('data-name') or g.get('id')) == c['target']:
                g.set('clip-path', 'url(#%s)' % c['id'])

    # 2) text glows from style buckets
    for fid_spec in cfg.get('glows', []):
        add_glow(defs, fid_spec['id'], fid_spec['blur'], fid_spec['color'], fid_spec['opacity'])
    for bucket in cfg.get('text_buckets', []):
        for t in root.iter(NSM + 'text'):
            fill = (t.get('fill') or '').replace(' ', '')
            if fill == bucket['fill'].replace(' ', '') and \
               float(t.get('font-size') or 0) >= bucket.get('min_size', 0):
                t.set('filter', 'url(#%s)' % bucket['glow'])

    # 3) swap in sliced assets
    for name, spec in cfg.get('assets', {}).items():
        for g in walk_groups(root):
            if (g.get('data-name') or g.get('id')) != name:
                continue
            put_image(g, spec['file'], spec['x'], spec['y'], spec['w'], spec['h'])
            if spec.get('drop_children'):
                for ch in list(g):
                    if ch.tag != NSM + 'image':
                        g.remove(ch)
            if spec.get('clear_clip') and g.get('clip-path'):
                del g.attrib['clip-path']

    # 4) optional: reuse identical images through <defs> + <use>
    if cfg.get('dedupe'):
        seen, n = {}, 0
        for parent in root.iter():
            for ch in list(parent):
                if ch.tag != NSM + 'image':
                    continue
                href = ch.get('href') or ''
                if not href.startswith('data:'):
                    continue
                key = hashlib.md5(href.encode()).hexdigest()[:12]
                sig = (key, ch.get('width'), ch.get('height'))
                if sig not in seen:
                    seen[sig] = ch
                    continue
                master = seen[sig]
                if not master.get('id'):
                    master.set('id', 'asset-' + key)
                use = ET.Element(NSM + 'use')
                use.set('href', '#asset-' + key)
                use.set('x', ch.get('x') or '0'); use.set('y', ch.get('y') or '0')
                idx = list(parent).index(ch)
                parent.remove(ch); parent.insert(idx, use)
                n += 1
        print('dedupe: %d instances now reference <defs> masters' % n)

    # 5) strip duplicated base64
    raw = ET.tostring(root, encoding='unicode')
    tree.write(args.out, encoding='UTF-8', xml_declaration=True)
    text = Path(args.out).read_text(encoding='utf-8')
    import re
    text = re.sub(r'\s+xlink:href="[^"]*"', '', text)
    Path(args.out).write_text(text, encoding='utf-8')

    r = ET.fromstring(text)
    print('g=%d image=%d text=%d use=%d  size %.2f MB' % (
        sum(1 for _ in r.iter(NSM + 'g')), sum(1 for _ in r.iter(NSM + 'image')),
        sum(1 for _ in r.iter(NSM + 'text')), sum(1 for _ in r.iter(NSM + 'use')),
        Path(args.out).stat().st_size / 1048576))


if __name__ == '__main__':
    main()
