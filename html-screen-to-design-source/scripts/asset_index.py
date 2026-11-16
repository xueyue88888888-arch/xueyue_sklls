#!/usr/bin/env python3
"""Prove that every image embedded in the SVG also exists as a file on disk.

Walks the SVG, hashes each embedded image, matches it against the asset folders,
and writes a usage list (asset file -> how many layers use it -> which ones).

Target: 0 unmatched. Anything unmatched means the delivery is not reproducible.

Usage:
    python asset_index.py --svg design.svg --assets ./assets -o asset_usage.csv
"""
import argparse
import base64
import csv
import hashlib
import sys
from pathlib import Path

import xml.etree.ElementTree as ET

NS = '{http://www.w3.org/2000/svg}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--svg', required=True)
    ap.add_argument('--assets', required=True)
    ap.add_argument('-o', '--out', default='asset_usage.csv')
    args = ap.parse_args()

    index = {}
    for f in Path(args.assets).rglob('*'):
        if f.suffix.lower() in ('.png', '.jpg', '.jpeg', '.svg') and f.is_file():
            index.setdefault(hashlib.md5(f.read_bytes()).hexdigest(), []).append(f)

    root = ET.fromstring(Path(args.svg).read_text(encoding='utf-8'))
    parent = {}
    for p in root.iter():
        for c in p:
            parent[c] = p

    def scope(el):
        p = parent.get(el)
        while p is not None:
            if p.tag == NS + 'g' and (p.get('data-name') or p.get('id')):
                return p.get('data-name') or p.get('id')
            p = parent.get(p)
        return ''

    rows, unmatched = [], 0
    for el in root.iter():
        if el.tag not in (NS + 'image', NS + 'use'):
            continue
        href = el.get('href') or ''
        if el.tag == NS + 'use':
            ref = href.lstrip('#')
            m = [e for e in root.iter() if e.get('id') == ref]
            href = (m[0].get('href') or '') if m else ''
        if not href.startswith('data:'):
            continue
        raw = base64.b64decode(href.split(',', 1)[1])
        md5 = hashlib.md5(raw).hexdigest()
        files = index.get(md5)
        if not files:
            unmatched += 1
            rows.append({'asset': '(missing)', 'layers': scope(el), 'uses': 1,
                         'size_kb': round(len(raw) / 1024), 'ref': el.tag.replace(NS, '')})
            continue
        f = sorted(files)[0]
        rows.append({'asset': str(f.relative_to(args.assets)).replace('\\', '/'),
                     'layers': scope(el), 'uses': 1,
                     'size_kb': round(f.stat().st_size / 1024),
                     'ref': el.tag.replace(NS, '')})

    agg = {}
    for r in rows:
        a = agg.setdefault(r['asset'], {'uses': 0, 'layers': [], 'size_kb': r['size_kb'],
                                        'refs': set()})
        a['uses'] += 1
        a['layers'].append(r['layers'])
        a['refs'].add(r['ref'])

    with open(args.out, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['#', 'asset', 'uses', 'reference', 'size_kb', 'first_layer'])
        for i, (k, v) in enumerate(sorted(agg.items(), key=lambda kv: -kv[1]['uses']), 1):
            uniq = sorted(set(v['layers']))
            w.writerow([i, k, v['uses'], '/'.join(sorted(v['refs'])), v['size_kb'],
                        uniq[0] + ('' if len(uniq) == 1 else ' (+%d)' % (len(uniq) - 1))])

    total = sum(v['uses'] for v in agg.values())
    print('image layers %d | unique assets %d | unmatched %d' % (total, len(agg), unmatched))
    print('written %s' % args.out)
    if unmatched:
        print('\n! %d embedded images have no file on disk — the delivery is not reproducible.'
              % unmatched)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
