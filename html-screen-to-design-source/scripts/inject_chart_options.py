#!/usr/bin/env python3
"""Inject ECharts options into an SVG's chartref placeholders.

The SVG is the only thing the upload service receives, so chart data has to
travel inside it. Each `chartref__*` image gets
`data-chart-option="<base64 ECharts option>"`, and svg2fvs rebuilds a native,
data-editable chart from it.

Usage:
    python inject_chart_options.py --svg design.svg --options chart-options.json --out out.svg

chart-options.json: {"<key>": {ECharts option}, ...}
Key matching, in order: exact data-name, substring, normalized (case/separator
insensitive), then document order as a last resort. Chart count and option count
usually match one-to-one, so order is a safe fallback — an unmatched placeholder
is a blank chart in FVS.
"""
import argparse
import base64
import json
import re
import sys

ap = argparse.ArgumentParser()
ap.add_argument('--svg', required=True)
ap.add_argument('--options', required=True)
ap.add_argument('--out', required=True)
a = ap.parse_args()

svg = open(a.svg, encoding='utf-8').read()
opts = json.load(open(a.options, encoding='utf-8'))
if not isinstance(opts, dict) or not opts:
    print('no options to inject')
    sys.exit(2)


def norm(s):
    return re.sub(r'[^a-z0-9]', '', str(s).lower())


def chartref_tags(text):
    """Find <image> elements that belong to a chartref__* placeholder.

    The placeholder can be the image itself or a <g data-name="chartref__...">
    wrapper — build_svg emits the wrapper form, so only looking at the image tag
    reported "no chartref" on a perfectly valid design source.
    """
    out = []
    stack = []
    token = re.compile(r'<g[\s>][^>]*>|</g>|<image[\s][^>]*>')
    for m in token.finditer(text):
        tag = m.group(0)
        if tag == '</g>':
            if stack:
                stack.pop()
            continue
        if tag.startswith('<g'):
            dn = re.search(r'data-name="([^"]*)"', tag)
            stack.append(dn.group(1) if dn else '')
            continue
        own = re.search(r'data-name="([^"]*)"', tag)
        name = own.group(1) if own else next((n for n in reversed(stack) if n), '')
        if re.match(r'chartref', name, re.I):
            out.append((m.start(), m.end(), tag, name))
    return out


tags = chartref_tags(svg)
if not tags:
    print('no chartref image in SVG — nothing to inject')
    sys.exit(2)

used = set()
assign = {}
unmatched = []
for _, _, tag, name in tags:
    hit = None
    if name in opts:
        hit = name
    else:
        for k in opts:
            if k not in used and (k in name or name in k):
                hit = k
                break
        if hit is None:
            n = norm(name)
            for k in opts:
                nk = norm(k)
                if k in used:
                    continue
                if nk and (nk == n or nk in n or n in nk):
                    hit = k
                    break
    if hit is None:
        unmatched.append(name)
        continue
    used.add(hit)
    assign[name] = hit

# Order fallback: placeholders left over take the options nobody claimed, in order.
spare = [k for k in opts if k not in used]
for name in list(unmatched):
    if not spare:
        break
    k = spare.pop(0)
    used.add(k)
    assign[name] = k
    unmatched.remove(name)

injected = 0
for start, end, tag, name in reversed(tags):
    key = assign.get(name)
    if key is None:
        continue
    try:
        payload = json.dumps(opts[key], ensure_ascii=False, allow_nan=False)
    except ValueError as exc:
        print('  skip %s: option is not valid JSON (%s)' % (name, exc))
        continue
    b64 = base64.b64encode(payload.encode('utf-8')).decode()
    if 'data-chart-option=' in tag:
        new = re.sub(r'data-chart-option="[^"]*"', 'data-chart-option="%s"' % b64, tag)
    elif tag.rstrip().endswith('/>'):
        new = tag[:-2].rstrip() + ' data-chart-option="%s"/>' % b64
    else:
        new = tag[:-1].rstrip() + ' data-chart-option="%s">' % b64
    svg = svg[:start] + new + svg[end:]
    injected += 1

open(a.out, 'w', encoding='utf-8').write(svg)
for name, key in assign.items():
    print('  %s <- %s' % (name, key))
print('注入图表 option: %d/%d' % (injected, len(tags)))
if unmatched:
    print('未匹配的图表占位（会变成空图）: %s' % ', '.join(unmatched))
sys.exit(0 if injected else 2)
