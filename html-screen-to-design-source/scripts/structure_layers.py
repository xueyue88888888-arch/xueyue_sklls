#!/usr/bin/env python3
"""Regroup a flat design SVG into the module -> sublayer structure.

    python structure_layers.py --in design-layered.svg --out design-structured.svg

Flat output looks like:

    <g data-name="page-bg__main"><image .../></g>
    <g data-name="title-bar-bg__kpi-1"><image .../></g>
    <g data-name="chartref__bar"><image .../></g>
    <g data-name="panel-header"><text .../>...</g>

Structured output keeps every element (and its data-name) but nests it:

    <g id="page-background" data-name="页面底色">...</g>
    <g id="section-header" data-name="页头与筛选">
      <g data-layer="card-backgrounds">...</g>
      <g data-layer="charts">...</g>
      <g data-layer="text">...</g>
    </g>
    <g id="section-content" data-name="内容模块">...
    <g id="section-table" data-name="明细表">...

Why it is safe: the converter reads the nearest `data-name`, not the new
wrappers, so renaming structure does not change how svg2fvs sees the file.
Painter order is preserved inside each sublayer, and modules are emitted in
reading order (background, header, content, table).
"""
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

SVG = 'http://www.w3.org/2000/svg'
NS = '{%s}' % SVG
ET.register_namespace('', SVG)

BG_PREFIXES = ('page-bg', 'title-bar-bg', 'filter-bar-bg', 'table-bg', 'panelbg__', 'card__', 'bg-top')
TEXT_GROUPS = ('panel-header', 'filter-bar', 'table-header', 'table-rows', 'other')
TABLE_GROUPS = ('table-header', 'table-rows', 'table-bg')


def num(v, d=0.0):
    try:
        return float(str(v).replace('px', ''))
    except (TypeError, ValueError):
        return d


def bbox(el):
    xs, ys, xe, ye = [], [], [], []
    for node in el.iter():
        tag = node.tag.replace(NS, '')
        if tag in ('image', 'rect', 'use'):
            x, y = num(node.get('x')), num(node.get('y'))
            w, h = num(node.get('width')), num(node.get('height'))
            if w > 0 and h > 0:
                xs.append(x); ys.append(y); xe.append(x + w); ye.append(y + h)
        elif tag == 'text':
            x, y = num(node.get('x')), num(node.get('y'))
            fs = num(node.get('font-size'), 14)
            content = ''.join(node.itertext()).strip()
            width = max(fs, len(content) * fs * 0.9)
            xs.append(x); ys.append(y - fs); xe.append(x + width); ye.append(y + fs * 0.4)
    if not xs:
        return None
    return min(xs), min(ys), max(xe), max(ye)


def name_of(el):
    return el.get('data-name') or ''


def sublayer_of(el, name):
    if el.tag == NS + 'text':
        return 'text'
    if name.startswith(BG_PREFIXES):
        return 'card-backgrounds'
    if name.startswith('chartref'):
        return 'charts'
    if name.startswith(('photo__', 'illustration__')):
        return 'photos'
    if name.startswith('icon__'):
        return 'icons'
    if any(True for _ in el.iter(NS + 'text')):
        return 'text'
    if any(True for _ in el.iter(NS + 'image')):
        return 'card-backgrounds'
    return 'icons'


def module_of(el, name, box, height):
    if name.startswith('page-bg'):
        return 'background'
    if name.split('__')[0].split('-')[0] in TABLE_GROUPS or name in TABLE_GROUPS:
        return 'table'
    if name.startswith(TEXT_GROUPS[:3]):
        top = box[1] if box else height
        if top < height * 0.16:
            return 'header'
    if box and box[3] < height * 0.16:
        return 'header'
    return 'content'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='src', required=True)
    ap.add_argument('--out', dest='dst', required=True)
    args = ap.parse_args()

    tree = ET.parse(args.src)
    root = tree.getroot()
    height = num(root.get('height'), 1080)
    items = [(el, name_of(el), bbox(el)) for el in list(root)]
    for el in list(root):
        root.remove(el)

    page = [it for it in items if it[1].startswith('page-bg')]
    body = [it for it in items if not it[1].startswith('page-bg')]

    header, rest = [], []
    for it in body:
        top = it[2][1] if it[2] else height
        bottom = it[2][3] if it[2] else height
        if bottom < height * 0.20 and top < height * 0.16:
            header.append(it)
        else:
            rest.append(it)

    table = [it for it in rest if it[1].split('__')[0] in TABLE_GROUPS]
    content = [it for it in rest if it not in table]

    if page:
        bg_group = ET.SubElement(root, NS + 'g', {'id': 'page-background', 'data-name': '页面底色'})
        for el, _, _ in page:
            bg_group.append(el)

    def emit(section_id, section_name, entries):
        if not entries:
            return
        section = ET.SubElement(root, NS + 'g', {'id': section_id, 'data-name': section_name})
        order = ['module-background', 'card-backgrounds', 'photos', 'charts', 'icons', 'text']
        buckets = {k: [] for k in order}
        for el, name, _ in entries:
            buckets[sublayer_of(el, name)].append(el)
        for key in order:
            if not buckets[key]:
                continue
            layer = ET.SubElement(section, NS + 'g', {'data-layer': key})
            for el in buckets[key]:
                layer.append(el)

    emit('section-header', '页头与筛选', header)
    emit('section-content', '内容模块', content)
    emit('section-table', '明细表', table)

    tree.write(args.dst, encoding='UTF-8', xml_declaration=True)
    counts = {}
    for sec in root.findall(NS + 'g'):
        for layer in sec.findall(NS + 'g'):
            counts[layer.get('data-layer')] = len(list(layer))
    print('modules: %d, sublayers: %s' % (len(root.findall(NS + 'g')), counts))


if __name__ == '__main__':
    main()
