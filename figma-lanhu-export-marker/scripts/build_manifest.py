#!/usr/bin/env python3
"""Generate the export manifest (name,FORMAT per line) from a design-source SVG.

The design-source SVG already carries the marking intent:
    <g data-name="card__mini-metric-3" data-export="PNG"> … </g>

This script turns those attributes into the flat list the Figma plugin expects,
normalizing per-instance suffixes (`-3`, ` 3`) back to the asset base name.

Usage:
    python build_manifest.py design-source.svg                 # print to stdout
    python build_manifest.py design-source.svg -o manifest.csv # write file
    python build_manifest.py design-source.svg --stats         # show counts only

Then in the Figma plugin: paste the list into the manifest box → 「载入清单」.
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter

NS = '{http://www.w3.org/2000/svg}'


def base_of(name):
    """card__mini-metric-12 -> card__mini-metric ; keep names that just end in digits."""
    m = re.match(r'^(.*?)-\d+$', name)
    return m.group(1) if m else name


def collect(svg_path):
    root = ET.parse(svg_path).getroot()
    items = []
    for g in root.iter():
        if g.tag not in (NS + 'g', NS + 'image'):
            continue
        name = g.get('data-name') or ''
        fmt = g.get('data-export')
        if not name or not fmt:
            continue
        items.append((name, fmt.upper()))
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('svg')
    ap.add_argument('-o', '--out', default=None)
    ap.add_argument('--stats', action='store_true')
    args = ap.parse_args()

    items = collect(args.svg)
    if not items:
        print('no layers with data-export found — does this SVG come from '
              'html-screen-to-design-source?', file=sys.stderr)
        return 2

    formats = {}
    instances = Counter()
    for name, fmt in items:
        base = base_of(name)
        if base in formats and formats[base] != fmt:
            print('::warning::%s has mixed export formats (%s vs %s) — using the first'
                  % (base, formats[base], fmt), file=sys.stderr)
        formats.setdefault(base, fmt)
        instances[base] += 1

    lines = ['# 素材清单：每行 name,FORMAT —— 由 %s 生成' % args.svg.split('/')[-1].split('\\')[-1]]
    lines += ['%s,%s' % (b, formats[b]) for b in sorted(formats)]
    text = '\n'.join(lines) + '\n'

    if args.stats:
        print('layers %d | asset classes %d | multi-instance classes %d'
              % (len(items), len(formats), sum(1 for k, v in instances.items() if v > 1)))
        for b, n in sorted(instances.items(), key=lambda kv: -kv[1])[:10]:
            if n > 1:
                print('  %-32s ×%d' % (b, n))
        return 0

    if args.out:
        with open(args.out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
        print('wrote %s — %d classes / %d layers' % (args.out, len(formats), len(items)))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
