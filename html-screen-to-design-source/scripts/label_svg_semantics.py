#!/usr/bin/env python3
"""Give an un-named dashboard SVG semantic data-name layers.

Input:  an SVG (optionally embedded in an HTML file) produced by an agent.
Output: the same SVG with each text/rect grouped and named so downstream
        converters (SVG -> FVS) can treat headers, filters and table rows
        as real structures instead of guessing from coordinates.

Heuristic (validated on the 1920x1080 "health-certificate" drill-down page):
  - page shell   : the outermost full-size rect(s)
  - panel-header : the top band (y < first divider) and its text runs
  - filter-bar   : the next band, up to the first large table rect
  - table-header : the first text row inside the table rect
  - table-rows   : subsequent text rows, numbered sequentially
  - table-bg     : the alternating row rectangles inside the table rect
The script never changes geometry, colours or content — it only adds
data-name="<group>__NNN" attributes and wraps each group in a <g>.
"""
import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path

NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
Q = lambda t: '{%s}%s' % (NS, t)
NUM = re.compile(r'-?\d+(?:\.\d+)?')
GROUPS = ('page-bg', 'title-bar-bg', 'filter-bar-bg', 'table-bg',
          'panel-header', 'filter-bar', 'table-header', 'table-rows')
SEMANTIC = {
    'filter': 'filter-bar', 'filter-bar': 'filter-bar', 'filters': 'filter-bar',
    'filter-item': 'filter-bar', 'filter-item-label': 'filter-bar',
    'filter-item-value': 'filter-bar', 'filter-button': 'filter-bar',
    'query': 'filter-bar', 'search': 'filter-bar', 'date-filter': 'filter-bar',
    'panel': 'panel-header', 'panel-header': 'panel-header',
    'kpi': 'panel-header', 'kpi-card': 'panel-header', 'title': 'panel-header',
    'table': 'table-rows', 'table-row': 'table-rows', 'table-body': 'table-rows',
    'table-header': 'table-header', 'thead': 'table-header',
}
FILTER_WORDS = re.compile(r'全部|查询|搜索|日期|时间|近\s*\d+\s*天|选择|筛选|起始|结束')
SLASH_PAIR = re.compile(r'^\s*[^/\s][^/]*\s*/\s*[^/\s][^/]*\s*$')


def num(v, d=0.0):
    m = NUM.search(str(v or ''))
    return float(m.group()) if m else d


def attrs(el):
    return el.attrib


def rect_geom(el):
    a = attrs(el)
    return num(a.get('x')), num(a.get('y')), num(a.get('width')), num(a.get('height'))


def text_geom(el, default_size=12.0):
    a = attrs(el)
    x, y = num(a.get('x')), num(a.get('y'))
    size = num(a.get('font-size'), default_size)
    label = ''.join(el.itertext()).strip()
    w = max(4.0, len(label) * size)
    return x, y, w, size


def extract_svg(raw: str) -> str:
    """If the input is an HTML file with one inline <svg>, return just that SVG."""
    m = re.search(r'<svg\b[\s\S]*?</svg>', raw, re.I)
    if not m:
        raise SystemExit('no <svg> found in input')
    return m.group(0)


def semantic_of(el, parent_of):
    for node in [el] + list(iter_parents(el, parent_of)):
        for key in ('data-name', 'data-el'):
            raw = str(attrs(node).get(key, '')).strip()
            if not raw:
                continue
            for name in [raw] + [p.strip() for p in re.split(r'[>\s/]+', raw) if p.strip()]:
                for prefix in sorted(SEMANTIC, key=len, reverse=True):
                    if name == prefix or name.startswith(prefix + '__') or name.startswith(prefix + '-') or name.startswith(prefix + '_'):
                        return SEMANTIC[prefix]
    return None


def iter_parents(el, parent_of):
    node = el
    while True:
        node = parent_of.get(node)
        if node is None:
            return
        yield node


def row_semantic(row):
    labels = [''.join(t.itertext()).strip() for t in row]
    if any(re.fullmatch(r'[\d.,%+\-\s]+', s) for s in labels):
        return None
    hits = sum(1 for s in labels if FILTER_WORDS.search(s) or SLASH_PAIR.match(s))
    return 'filter-bar' if hits >= 2 else None


def classify(svg_text: str, allow_filters: bool = True) -> ET.Element:
    root = ET.fromstring(svg_text)
    w = num(root.get('width'), 1920)
    h = num(root.get('height'), 1080)
    body = list(root)

    rects = [e for e in root.iter(Q('rect'))]
    texts = [e for e in root.iter(Q('text'))]

    page_rects = [r for r in rects if rect_geom(r)[2] >= w * 0.8 and rect_geom(r)[3] >= h * 0.7]
    dividers = [r for r in rects if rect_geom(r)[3] <= 2 and rect_geom(r)[2] >= w * 0.5
                and r not in page_rects]
    divider_y = min([rect_geom(r)[1] for r in dividers], default=h * 0.15) if dividers else h * 0.15

    def is_table_rect(r):
        if r in page_rects:
            return False
        rw, rh = rect_geom(r)[2], rect_geom(r)[3]
        if not (rw >= w * 0.3 and rh >= h * 0.15 and rh < h * 0.75):
            return False
        return not re.match(r'^rgba\(255,\s*255,\s*255,\s*0\.0', str(attrs(r).get('fill', '')))
    table_rects = [r for r in rects if is_table_rect(r)]
    def rect_text_count(r):
        rx, ry, rw, rh = rect_geom(r)
        return sum(1 for t in texts if rx - 4 <= text_geom(t)[0] <= rx + rw + 4
                   and ry - 4 <= text_geom(t)[1] <= ry + rh + 4)
    table = max(table_rects, key=rect_text_count) if table_rects else None
    table_y = rect_geom(table)[1] if table is not None else h * 0.2
    table_bottom = table_y + rect_geom(table)[3] if table is not None else h

    parent_of = {child: parent for parent in root.iter() for child in parent}
    declared = {}
    for t in texts:
        raw = str(attrs(t).get('data-name', '')).strip()
        match = re.match(r'^(%s)__\d+$' % '|'.join(GROUPS), raw)
        if match:
            declared[id(t)] = match.group(1)
        else:
            declared[id(t)] = semantic_of(t, parent_of)

    groups = {
        'page-bg': [], 'title-bar-bg': [], 'filter-bar-bg': [],
        'panel-header': [], 'filter-bar': [],
        'table-header': [], 'table-rows': [], 'table-bg': [], 'other': [],
    }

    for el in page_rects:
        groups['page-bg'].append(el)
    if table is not None and table not in page_rects:
        groups['table-bg'].append(table)

    y_rows = {}
    for t in texts:
        x, y, tw, size = text_geom(t)
        key = round(y / 3) * 3
        y_rows.setdefault(key, []).append(t)

    ys_sorted = sorted(y_rows)
    max_cols = max((len(y_rows[y]) for y in ys_sorted), default=0)
    row_gap_limit = max(70, h * 0.08)

    blocks = []
    cur = []
    for y in ys_sorted:
        if cur and y - cur[-1] > row_gap_limit:
            blocks.append(cur)
            cur = []
        cur.append(y)
    if cur:
        blocks.append(cur)

    table_blocks = []
    for block in blocks:
        sub = []
        for y in block:
            cols = len(y_rows[y])
            if cols < 3:
                if sub:
                    table_blocks.append(sub)
                    sub = []
                continue
            if sub and abs(cols - len(y_rows[sub[-1]])) >= 2:
                table_blocks.append(sub)
                sub = []
            sub.append(y)
        if sub:
            table_blocks.append(sub)

    best_block = max(table_blocks, key=len) if table_blocks else []
    header_y = best_block[0] if len(best_block) >= 2 else None
    data_ys = set(best_block[1:]) if header_y is not None else set()
    filter_ys = set()
    if allow_filters and table is None and header_y is not None:
        for y in ys_sorted:
            if y >= header_y or y in data_ys or y in best_block:
                continue
            cols = len(y_rows[y])
            row = sorted(y_rows[y], key=lambda e: num(attrs(e).get('x')))
            gap = (header_y - y) / h
            if 3 <= cols <= 5 and gap <= 0.6 and row_semantic(row) == 'filter-bar':
                filter_ys.add(y)

    for y in ys_sorted:
        row = sorted(y_rows[y], key=lambda e: num(attrs(e).get('x')))
        if y in filter_ys:
            groups['filter-bar'].extend(row)
            continue
        tagged = [declared.get(id(t)) for t in row]
        if all(g and g in groups for g in tagged):
            for t, g in zip(row, tagged):
                groups[g].append(t)
            continue
        if y == header_y:
            groups['table-header'].extend(row)
        elif y in data_ys:
            groups['table-rows'].extend(row)
        elif y < divider_y:
            groups['panel-header'].extend(row)
        elif table is not None and y <= table_bottom:
            groups['table-rows'].extend(row)
        elif allow_filters and y < table_y:
            groups['filter-bar'].extend(row)
        elif table is None:
            # No table on this screen (a card grid): every remaining run is panel copy,
            # not a data row. Otherwise a dashboard turns into one 200-row text table.
            groups['panel-header'].extend(row)
        else:
            groups['other'].extend(row)

    for r in rects:
        if r in page_rects or r is table:
            continue
        _, y, rw, rh = rect_geom(r)
        if table is not None and table_y <= y <= table_bottom and rw >= w * 0.5:
            groups['table-bg'].append(r)
        elif y < divider_y and rw >= w * 0.4:
            groups['title-bar-bg'].append(r)
        elif divider_y <= y < table_y and rh >= h * 0.015 and rw >= w * 0.03:
            groups['filter-bar-bg'].append(r)
        else:
            groups['other'].append(r)

    semantic_image_re = re.compile(r'^(page-bg|title-bar-bg|filter-bar-bg|card__|panelbg__|bg-top|chartref__|icon__|photo__|illustration__)', re.I)
    semantic_images = []
    for el in body:
        dn = str(attrs(el).get('data-name', '')).strip()
        has_img = any(True for _ in el.iter(Q('image')))
        if has_img and dn and semantic_image_re.match(dn):
            semantic_images.append(el)
            continue
        if el not in page_rects and el not in rects and el not in texts:
            groups['other'].append(el)

    parent_of = {child: parent for parent in root.iter() for child in parent}
    named = set()
    for items in groups.values():
        for el in items:
            named.add(id(el))
    for name, items in groups.items():
        if not items:
            continue
        g = ET.SubElement(root, Q('g'), {'data-name': name})
        for i, el in enumerate(items, 1):
            parent = parent_of.get(el)
            if parent is not None:
                parent.remove(el)
            existing = str(attrs(el).get('data-name', '')).strip()
            if not re.match(r'^(%s)__\d+$' % '|'.join(GROUPS), existing) and not semantic_image_re.match(existing):
                el.set('data-name', '%s__%03d' % (name, i))
            g.append(el)
    for parent in list(root.iter()):
        if parent.tag == Q('g') and not parent.get('data-name') and len(parent) == 0:
            root.remove(parent)
    return root


def g_table_header_unset(groups):
    return not groups['table-header']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--filters', choices=('yes', 'no'), default='yes',
                    help='no = the screen has no real filter controls; never emit filter-bar text')
    ap.add_argument('--in', dest='src', required=True)
    ap.add_argument('--out', dest='dst', required=True)
    args = ap.parse_args()
    raw = Path(args.src).read_text(encoding='utf-8')
    svg = extract_svg(raw)
    out = classify(svg, allow_filters=(args.filters == 'yes'))
    Path(args.dst).write_text(ET.tostring(out, encoding='unicode'), encoding='utf-8')
    counts = {}
    for g in out.findall(Q('g')):
        counts[g.get('data-name')] = len(list(g))
    print('layers:', counts)


if __name__ == '__main__':
    main()
