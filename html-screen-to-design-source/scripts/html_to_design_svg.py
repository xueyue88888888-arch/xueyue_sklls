#!/usr/bin/env python3
"""End-to-end HTML -> layered design-source SVG orchestrator.

One command replaces the manual jobs.json / config.json dance:

    python html_to_design_svg.py --html index.html --out out/ \
        --width 1920 --height 1080 [--charts-dir html_dir]

Pipeline (all intermediate files are regenerated on every run):
    measure_dom.py -> auto jobs.json -> slice_cards.py -> auto base/config
    -> build_svg.py -> label_svg_semantics.py -> [inject_chart_options.py]
    -> figma_compat.py -> design-layered.svg + 图层清单.md + 校验结果.txt

Environment:
    HTML2DESIGN_PROJECT_ROOT   project root (default: auto-detect / cwd)
    H2F_BROWSER / HTML2DESIGN_BROWSER   chromium executable override
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent

# Windows consoles are often GBK; chart names and layer names contain characters it
# cannot encode, and a print() then kills an otherwise finished conversion.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

# Roles and name prefixes that are eligible for slicing.
ROLE_PREFIXES = (
    ('page-bg', 'page-background'),
    ('panelbg__', 'card-background'),
    ('card__', 'card-background'),
    ('photo__', 'photo'),
    ('icon__', 'icon'),
    ('chartref__', 'chart-reference'),
    ('title-bar-bg', 'card-background'),
    ('filter-bar-bg', 'card-background'),
)
SEMANTIC_PREFIXES = (
    'page-bg', 'panelbg__', 'card__', 'photo__', 'icon__', 'chartref__',
    'chart__', 'title', 'panel-header', 'filter-bar', 'bg-top',
    'illustration__', 'title-bar-bg', 'filter-bar-bg', 'table-bg',
)
FALLBACK_BLOCKS = '.panel,.card,.kpi,.chart-card,.glass-card,[data-name],[data-el]'


def project_root(explicit=None):
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get('HTML2DESIGN_PROJECT_ROOT')
    if env:
        return Path(env).resolve()
    for d in [Path.cwd(), HERE, SKILL] + list(Path.cwd().parents):
        if (d / 'packages' / 'engine' / 'browser.cjs').exists():
            return d
    return Path.cwd()


SYSTEM_BROWSERS = (
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
    '/usr/bin/microsoft-edge',
)


def browser_path(project, override=None):
    """Pick a Chromium binary.

    Order: --browser flag -> HTML2DESIGN_BROWSER / H2F_BROWSER -> browser.cjs of a
    sibling project -> Playwright cache -> installed Chrome/Edge. Without one of
    these, `playwright` fails with "Executable doesn't exist" even though a usable
    Chrome is on the machine.
    """
    for p in (override, os.environ.get('HTML2DESIGN_BROWSER'), os.environ.get('H2F_BROWSER')):
        if p and Path(p).exists():
            return str(Path(p).resolve())
    bc = project / 'packages' / 'engine' / 'browser.cjs'
    if bc.exists():
        js = "const b=require(%s);process.stdout.write(b.resolveBrowser()||'')" % json.dumps(str(bc))
        try:
            r = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=30)
            if r.returncode == 0 and r.stdout.strip() and Path(r.stdout.strip()).exists():
                return r.stdout.strip()
        except Exception:
            pass
    cache = Path.home() / ('Library/Caches/ms-playwright' if sys.platform == 'darwin'
                           else 'AppData/Local/ms-playwright' if os.name == 'nt'
                           else '.cache/ms-playwright')
    if cache.is_dir():
        for exe in ('chrome-win64/chrome.exe', 'chrome-mac/Chromium.app/Contents/MacOS/Chromium',
                    'chrome-linux/chrome'):
            for cand in sorted(cache.glob('chromium-*/' + exe), reverse=True):
                return str(cand)
    for cand in SYSTEM_BROWSERS:
        if Path(cand).exists():
            return cand
    return None


def run(cmd, **kw):
    print('\n$ ' + ' '.join(str(c) for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd], **kw)
    if r.returncode:
        raise SystemExit('FAILED (%d): %s' % (r.returncode, ' '.join(str(c) for c in cmd)))
    return r


def py(exe, script, *args):
    return run([sys.executable, str(HERE / script)] + [str(a) for a in args])


def dump(name, obj, out):
    p = out / name
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    return p


def esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def num(v, d=0.0):
    m = re.search(r'-?\d+(?:\.\d+)?', str(v or ''))
    return float(m.group()) if m else d


def role_of(name):
    for prefix, role in ROLE_PREFIXES:
        if name.startswith(prefix):
            return role
    return ''


def relevant(name):
    return any(name.startswith(p) for p in SEMANTIC_PREFIXES)


def unique_name(base, used):
    if base not in used:
        used.add(base)
        return base
    i = 2
    while '%s-%d' % (base, i) in used:
        i += 1
    name = '%s-%d' % (base, i)
    used.add(name)
    return name


def css_escape(s):
    return re.sub(r'([^a-zA-Z0-9_-])', lambda m: '\\%s' % m.group(1), str(s))


def selector_for(node):
    if node.get('id'):
        return '#%s' % css_escape(node['id'])
    tag = node.get('tag') or '*'
    cls = str(node.get('cls') or '').split()
    extra = ''
    for attr in ('data-name', 'data-el'):
        if node.get(attr):
            extra += '[%s="%s"]' % (attr, node[attr])
    return tag + ''.join('.' + css_escape(c) for c in cls[:2]) + extra


def discover_nodes(html, width, height, browser):
    """Query the live DOM for all semantic blocks with their selector, index and geometry."""
    js = r"""
    (args) => {
      const prefixes = args.prefixes;
      const root = document.querySelector('.view.active') || document.body;
      const vis = el => {
        const r = el.getBoundingClientRect(), s = getComputedStyle(el);
        return r.width >= 6 && r.height >= 6 && s.display !== 'none' &&
               s.visibility !== 'hidden' && Number(s.opacity) > 0;
      };
      const nameOf = el => {
        for (const key of ['data-name', 'data-el']) {
          const raw = String(el.getAttribute(key) || '').trim();
          if (!raw) continue;
          for (const part of raw.split(/[>\s/]+/).filter(Boolean)) {
            if (prefixes.some(p => part.startsWith(p))) return part;
          }
        }
        return '';
      };
      const visible = [...root.querySelectorAll('*')].filter(vis);
      const nodes = visible.map((el, order) => {
        const r = el.getBoundingClientRect();
        const sel = el.id ? '#' + CSS.escape(el.id)
          : el.tagName.toLowerCase() +
            (el.className && typeof el.className === 'string'
              ? '.' + el.className.trim().split(/\s+/).slice(0, 2).map(CSS.escape).join('.') : '') +
            (el.getAttribute('data-name') ? '[data-name="' + el.getAttribute('data-name') + '"]' : '') +
            (el.getAttribute('data-el') ? '[data-el="' + el.getAttribute('data-el') + '"]' : '');
        const idx = visible.filter(e => e !== el && e.matches(sel) &&
          visible.indexOf(e) < order).length;
        return {order, idx, sel, tag: el.tagName, id: el.id || '', cls: String(el.className || ''),
                data_name: el.getAttribute('data-name') || '',
                data_el: el.getAttribute('data-el') || '',
                name: nameOf(el),
                x: +r.x.toFixed(2), y: +r.y.toFixed(2),
                w: +r.width.toFixed(2), h: +r.height.toFixed(2)};
      });
      return nodes;
    }
    """
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        launch = dict(headless=True, args=['--allow-file-access-from-files', '--hide-scrollbars'])
        if browser:
            launch['executable_path'] = browser
        b = p.chromium.launch(**launch)
        page = b.new_page(viewport={'width': width, 'height': height}, device_scale_factor=1)
        page.goto(Path(html).resolve().as_uri(), wait_until='load', timeout=180000)
        page.wait_for_timeout(1200)
        nodes = page.evaluate(js, {'prefixes': list(SEMANTIC_PREFIXES)})
        b.close()
    return nodes


def make_jobs(nodes):
    jobs, used, seen_geom = [], set(), set()
    counts = {}
    for node in nodes:
        name = node.get('name') or ''
        if not relevant(name):
            continue
        role = role_of(name)
        if not role:
            continue
        # page-bg duplicate by data-el: keep one per unique name.
        base = name if name.endswith(('__001', '__1')) else name
        base = re.sub(r'-\d+$', '', base) if role == 'page-background' else base
        if node['w'] < 20 or node['h'] < 10:
            continue  # empty/zero-size wrappers expand to a 2x2 junk slice
        key = (base, round(node['x']), round(node['y']), round(node['w']), round(node['h']))
        if key in seen_geom:
            continue
        seen_geom.add(key)
        counts[base] = counts.get(base, 0) + 1
        final = unique_name(base, used) if counts[base] > 1 else base
        if final in used:
            final = unique_name(base, used)
        job_name = re.sub(r'[^a-zA-Z0-9_-]', '_', final)
        jobs.append({
            'name': job_name,
            'data_name': final,
            'role': role,
            'selector': node['sel'],
            'index': node['idx'],
            'hide_children': role == 'card-background' and node['w'] < 200,
            'node': node,
        })
    return jobs


def make_base_svg(width, height):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="0 0 %d %d"></svg>\n' % (width, height, width, height))


def make_config(jobs, boxes, measure, width, height, font, out=None):
    assets = {}
    for job in jobs:
        name = job['name']
        if name not in boxes:
            continue
        box = boxes[name]
        assets[job['data_name']] = {
            'file': str((out / 'assets' / box['file']).resolve()),
            'x': round(box['x'], 2), 'y': round(box['y'], 2),
            'w': round(box['w'], 2), 'h': round(box['h'], 2),
            'role': job['role'],
        }
    return {
        'base_svg': str((out / 'base.svg').resolve()) if out else 'base.svg',
        'font_family': font,
        'texts': [],
        'assets': assets,
        'glows': [],
        'text_buckets': [],
        'dedupe': False,
    }


def build_text_svg(measure, width, height, font, assets=None):
    """Emit real <text> runs from measure_dom output, with centered alignment.

    Also emits empty <g data-name="..."> placeholders for each asset so
    build_svg.py can fill in the base64 <image> for that group.
    """
    lines = [make_base_svg(width, height).split('></svg>')[0] + '>']
    # Painter order: large backgrounds first, small overlays last.
    def area(item):
        spec = item[1]
        return float(spec.get('w', 0)) * float(spec.get('h', 0))
    for name, _ in sorted((assets or {}).items(), key=area, reverse=True):
        lines.append('  <g data-name="%s" data-export="PNG"></g>' % esc(name))
    n = 0
    for t in measure.get('text', []):
        raw = str(t.get('text') or '').strip()
        if not raw:
            continue
        x, y = float(t.get('x', 0)), float(t.get('y', 0))
        w, h = float(t.get('w', 0)), float(t.get('h', 0))
        if w < 1 or h < 1 or x < -4 or y < -4 or x > width + 4 or y > height + 4:
            continue
        fs = num(t.get('fontSize'), 14)
        color = t.get('color') or '#ffffff'
        align = t.get('textAlign') or 'start'
        if align == 'center':
            tx, anchor = x + w / 2.0, 'middle'
        elif align == 'right':
            tx, anchor = x + w, 'end'
        else:
            tx, anchor = x, 'start'
        ty = y + h * 0.82
        weight = t.get('fontWeight') or '400'
        attrs = ('data-name="text__%03d" x="%.2f" y="%.2f" font-size="%.2f" '
                 'font-weight="%s" fill="%s" font-family="%s" text-anchor="%s"') % (
                     n + 1, tx, ty, fs, esc(weight), esc(color), esc(font), anchor)
        names = t.get('names') or []
        semantic = next((nm for nm in names if relevant(str(nm))), '')
        if semantic:
            attrs += ' data-el="%s"' % esc(semantic)
        lines.append('  <text %s>%s</text>' % (attrs, esc(raw)))
        n += 1
    lines.append('</svg>')
    return '\n'.join(lines), n


def project_rel(path):
    """Shorten absolute output paths to a relative form for the manifest."""
    try:
        return str(Path(path).relative_to(Path.cwd())).replace(chr(92), '/')
    except ValueError:
        return str(path)


def write_manifest(out, svg_path, jobs, boxes, stats, chart_count):
    names = {}
    for job in jobs:
        if job['name'] in boxes:
            names[job['data_name']] = job['role']
    md = ['# 分层 SVG 设计源 · 自动生成清单', '',
          '- 产物：`%s`' % svg_path.name,
          '- 画布：见 SVG 根元素',
          '- 字体：统一 Microsoft YaHei',
          '- 图片：全部内嵌 base64（无相对路径）', '',
          '## 图层统计', '',
          '| 项 | 数量 |', '| --- | ---: |',
          '| 切图 `<image>` | %d |' % stats['images'],
          '| 真文字 `<text>` | %d |' % stats['texts'],
          '| 语义分组 `<g>` | %d |' % stats['groups'],
          '| 图表数据 `data-chart-option` | %d |' % chart_count,
          '| 相对路径 href | %d |' % stats['relative_href'],
          '| mask / use / 渐变文字 | %d / %d / %d |' % (
              stats['masks'], stats['uses'], stats['gradient_text']), '',
          '## 切图清单', '',
          '| data-name | role | 文件 | 几何 (x,y,w,h) |', '| --- | --- | --- | --- |']
    for name, role in names.items():
        spec = stats['asset_geom'].get(name, {})
        f = project_rel(spec.get('file', '-'))
        md.append('| `%s` | %s | `%s` | %.1f, %.1f, %.1f, %.1f |' % (
            name, role or '-', f, spec.get('x', 0), spec.get('y', 0),
            spec.get('w', 0), spec.get('h', 0)))
    md += ['', '## 校验', '',
           '见 `校验结果.txt`。每一步均由脚本重新生成，未手工修改产物。', '']
    (out / '图层清单.md').write_text('\n'.join(md), encoding='utf-8')


def svg_stats(svg_path):
    import xml.etree.ElementTree as ET
    raw = svg_path.read_text(encoding='utf-8')
    root = ET.fromstring(raw)
    ns = '{http://www.w3.org/2000/svg}'
    return {
        'images': len(list(root.iter(ns + 'image'))),
        'texts': len(list(root.iter(ns + 'text'))),
        'groups': len(list(root.iter(ns + 'g'))),
        'uses': len(list(root.iter(ns + 'use'))),
        'masks': sum(1 for e in root.iter() if e.get('mask')),
        'gradient_text': sum(1 for t in root.iter(ns + 'text')
                             if (t.get('fill') or '').startswith('url(')),
        'b64': raw.count('data:image/png;base64,'),
        'relative_href': len(re.findall(r'href="(?!data:)[^"]+"', raw)),
        'chart_options': len(re.findall(r'data-chart-option="', raw)),
        'names': sorted(set(re.findall(r'data-name="([^"]+)"', raw))),
        'bytes': len(raw.encode('utf-8')),
    }


def restore_painter_order(svg_path, assets):
    """Move semantic groups so large backgrounds render before content.

    label_svg_semantics.py appends all <g data-name> wrappers at the end,
    which can bury text under the page background. Reorder root children:
    big images first (page-bg > panelbg), then text groups, then small images.
    """
    import xml.etree.ElementTree as ET
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    ns = '{http://www.w3.org/2000/svg}'
    tree = ET.parse(svg_path)
    root = tree.getroot()

    def area(g):
        a = 0.0
        for im in g.iter(ns + 'image'):
            a += float(im.get('width') or 0) * float(im.get('height') or 0)
        return a

    def kind(g):
        """Painter order by role, not by size.

        Sorting only by area put card/chart slices *after* the text groups, so a 1920x1080
        screen showed the axes and two lines while 74 of 76 text runs were hidden under
        the cards. Size says nothing about which layer belongs underneath.
        """
        nm = (g.get('data-name') or '')
        has_img = any(True for _ in g.iter(ns + 'image'))
        has_text = any(True for _ in g.iter(ns + 'text'))
        if nm.startswith('page-bg'):
            return 0
        if has_img and nm.startswith(('title-bar-bg', 'filter-bar-bg', 'table-bg',
                                      'panelbg__', 'card__', 'bg-top')):
            return 1
        if has_img and nm.startswith('chartref__'):
            return 2
        if has_img and nm.startswith(('icon__', 'photo__', 'illustration__')):
            return 3
        if has_text:
            return 4
        if has_img:
            return 5
        return 6

    children = list(root)
    children.sort(key=lambda g: (kind(g), -area(g)))
    for ch in children:
        root.remove(ch)
    root.extend(children)
    tree.write(svg_path, encoding='UTF-8', xml_declaration=True)


def export_chart_options(project, html, out, browser):
    """Export ECharts options with the collector shipped next to this script."""
    collector = HERE / 'export_chart_options.py'
    if not collector.exists():
        return None, 'collector not found: %s' % collector
    cmd = [sys.executable, str(collector), '--html', str(Path(html).resolve()), '--out', str(out)]
    if browser:
        cmd += ['--browser', browser]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          encoding='utf-8', errors='replace')
    if proc.returncode:
        return None, 'collector failed(%d): %s' % (proc.returncode, (proc.stdout or proc.stderr or '')[:300])
    if proc.stdout:
        print(proc.stdout.strip()[:300])
    found = out / 'chart-options.json'
    if found.exists():
        return found, None
    return None, 'collector ran but wrote no chart-options.json'


FORM_CONTROL_RE = re.compile(r'<(select|input|textarea)\b', re.I)


def detect_form_controls(html_path):
    """True when the page has a real form control.

    A card dashboard has no <select>/<input>; labelling its text as `filter-bar`
    makes svg2fvs invent dropdowns/date pickers that the design never had.
    """
    try:
        text = Path(html_path).read_text(encoding='utf-8', errors='replace')
    except Exception:
        return False
    controls = [m.group(1).lower() for m in FORM_CONTROL_RE.finditer(text)]
    if not controls:
        return False
    # <input type=hidden> and buttons do not count as filters.
    if all(c == 'input' for c in controls) and re.search(r'<input[^>]+type="?hidden', text, re.I):
        return bool(re.search(r'<select\b|<input[^>]+type="?(text|date|search|number|checkbox|radio)', text, re.I))
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--html', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--width', type=int, required=True)
    ap.add_argument('--height', type=int, required=True)
    ap.add_argument('--charts-dir', default=None,
                    help='directory containing ECharts HTML; export + inject chart options')
    ap.add_argument('--font', default='Microsoft YaHei')
    ap.add_argument('--project-root', default=None)
    ap.add_argument('--browser', default=None)
    ap.add_argument('--scale', type=int, default=2, help='slice device scale factor')
    ap.add_argument('--dry-run', action='store_true', help='only print generated jobs/config')
    ap.add_argument('--filters', choices=('auto', 'yes', 'no'), default='auto',
                    help='does this screen have real filter controls? auto = detect <select>/<input> in the HTML')
    ap.add_argument('--allow-empty-images', action='store_true',
                    help='do not fail when the SVG ends up with 0 images (debugging only)')
    ap.add_argument('--layer-structure', choices=('module', 'flat'), default='module',
                    help='module = regroup into 模块→6子层 for design-tool handoff; flat = keep as generated')
    ap.add_argument('--max-fallback', type=int, default=60,
                    help='when the HTML has no data-name: keep at most N largest blocks')
    args = ap.parse_args()

    html = Path(args.html).resolve()
    out = Path(args.out).resolve()
    if not html.exists():
        raise SystemExit('HTML not found: %s' % html)
    project = project_root(args.project_root)
    browser = browser_path(project, args.browser)
    print('project root: %s\nbrowser: %s' % (project, browser or '(playwright default)'))

    # 1. measure DOM (geometry truth)
    if args.dry_run:
        nodes = discover_nodes(html, args.width, args.height, browser)
        jobs = make_jobs(nodes)
        print('\n=== DRY RUN: jobs.json (%d jobs) ===' % len(jobs))
        print(json.dumps([{k: v for k, v in j.items() if k != 'node'} for j in jobs],
                         ensure_ascii=False, indent=2))
        print('\n=== DRY RUN: config.json assets (paths shown relative to output dir) ===')
        preview = make_config(jobs,
                              {j['name']: {'file': j['name'] + '.png',
                                           'x': 0, 'y': 0, 'w': 100, 'h': 100}
                               for j in jobs},
                              {}, args.width, args.height, args.font, out)
        preview['base_svg'] = '<out>/_work/base.svg'
        for key, spec in preview['assets'].items():
            spec['file'] = '<out>/assets/' + Path(spec['file']).name
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        print('\n=== DRY RUN: text runs come from measure_dom.py at build time ===')
        return

    out.mkdir(parents=True, exist_ok=True)
    assets = out / 'assets'
    assets.mkdir(parents=True, exist_ok=True)
    work = out / '_work'
    work.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env['PYTHONPATH'] = str(project / 'node_modules') + os.pathsep + env.get('PYTHONPATH', '')

    measure_path = work / 'geometry.json'
    mcmd = [sys.executable, str(HERE / 'measure_dom.py'), '--html', str(html),
            '--width', str(args.width), '--height', str(args.height),
            '--blocks', FALLBACK_BLOCKS, '-o', str(measure_path)]
    if browser:
        mcmd += ['--browser', browser]
    run(mcmd)
    measure = json.loads(measure_path.read_text(encoding='utf-8'))

    # 2. discover named blocks -> jobs.json
    nodes = discover_nodes(html, args.width, args.height, browser)
    jobs = make_jobs(nodes)
    # Geometry fallback: unnamed structural blocks from measure_dom
    used_names = {j['data_name'] for j in jobs}
    # Only NAMED nodes count as covered. Using every visible node made the fallback
    # dead code: the block itself was always in `nodes`, so every candidate matched
    # and a screen without data-name produced images=0.
    named_geom = {(round(n['x']), round(n['y']), round(n['w']), round(n['h']))
                  for n in nodes if relevant(n.get('name') or '')}
    fallback_used = 0
    if not jobs:
        # Naming is the contract. Only when the HTML carries no usable data-name do we
        # fall back to geometry — otherwise every .card / row / chip also gets sliced,
        # which produced 101 images (4.3 MB) for a 20-block screen.
        cands = []
        for b in measure.get('blocks', []):
            if float(b.get('w', 0)) < 80 or float(b.get('h', 0)) < 30:
                continue
            g = (round(float(b['x'])), round(float(b['y'])),
                 round(float(b['w'])), round(float(b['h'])))
            if g in named_geom:
                continue
            cands.append(b)
        cands.sort(key=lambda b: float(b['w']) * float(b['h']), reverse=True)
        for b in cands[:args.max_fallback]:
            name = 'card__fallback_%03d' % (fallback_used + 1)
            fallback_used += 1
            used_names.add(name)
            jobs.append({
                'name': name.replace('__', '_'),
                'data_name': name,
                'role': 'card-background',
                'selector': b.get('sel', 'div'),
                'index': int(b.get('index', 0)),
                'x': float(b['x']), 'y': float(b['y']),
                'w': float(b['w']), 'h': float(b['h']),
                'hide_children': True,
                'node': {},
            })
        if len(cands) > args.max_fallback:
            print('WARN fallback: %d candidate blocks, kept the %d largest'
                  ' (raise --max-fallback if the design really has more)'
                  % (len(cands), args.max_fallback))
    jobs_path = dump('jobs.json', [{k: v for k, v in j.items() if k != 'node'} for j in jobs], work)
    print('jobs: %d (named=%d, fallback=%d)' % (
        len(jobs), sum(1 for j in jobs if 'fallback' not in j['name']),
        sum(1 for j in jobs if 'fallback' in j['name'])))

    # 3. slice
    cmd = [sys.executable, str(HERE / 'slice_cards.py'), '--html', str(html),
           '--width', str(args.width), '--height', str(args.height),
           '--jobs', str(jobs_path), '--scale', str(args.scale), '-o', str(assets)]
    if browser:
        cmd += ['--browser', browser]
    run(cmd)
    boxes = json.loads((assets / 'boxes.json').read_text(encoding='utf-8'))
    # slice_cards writes Playwright clip keys (width/height); config uses w/h.
    for box in boxes.values():
        box.setdefault('w', box.get('width', 0))
        box.setdefault('h', box.get('height', 0))

    # 3b. Normalise every slice to RGBA (design-tool + figma_compat requirement).
    from PIL import Image
    for f in assets.glob('*.png'):
        try:
            with Image.open(f) as im:
                if im.mode != 'RGBA':
                    im.convert('RGBA').save(f, format='PNG')
        except Exception as exc:
            print('WARN cannot convert %s: %s' % (f, exc))

    # 4. base SVG (real text from measure) + config -> build_svg.py
    config = make_config(jobs, boxes, measure, args.width, args.height, args.font, out)
    base_text, text_count = build_text_svg(measure, args.width, args.height,
                                           args.font, config['assets'])
    base_path = work / 'base.svg'
    base_path.write_text(base_text, encoding='utf-8')
    config['base_svg'] = str(base_path.resolve())
    config['asset_geom'] = {k: v for k, v in config['assets'].items()}
    config_path = dump('config.json', config, work)
    raw_svg = work / 'design-raw.svg'
    py(None, 'build_svg.py', '--config', config_path, '-o', raw_svg)

    # 5. semantic labels
    layered = out / 'design-layered.svg'
    has_filters = detect_form_controls(html) if args.filters == 'auto' else args.filters == 'yes'
    print('filters: %s (source=%s)' % ('yes' if has_filters else 'no', args.filters))
    py(None, 'label_svg_semantics.py', '--in', raw_svg, '--out', layered,
       '--filters', 'yes' if has_filters else 'no')
    restore_painter_order(layered, config['assets'])

    # 6. optional chart options
    chart_count = 0
    if args.charts_dir:
        # freeze2 需要 HTML 文件路径(它 file:// 打开);charts-dir 只作为兜底资源目录
        chart_html = Path(args.html)
        if not chart_html.is_file() and Path(args.charts_dir).is_dir():
            htmls = list(Path(args.charts_dir).glob('*.html'))
            chart_html = htmls[0] if htmls else chart_html
        options, err = export_chart_options(project, chart_html, work, browser)
        if options:
            injected = out / 'design-layered-with-charts.svg'
            r = subprocess.run([sys.executable, str(HERE / 'inject_chart_options.py'),
                                '--svg', str(layered), '--options', str(options),
                                '--out', str(injected)],
                               capture_output=True, text=True, encoding='utf-8', errors='replace')
            print((r.stdout or '').strip()[:600])
            if r.returncode == 0:
                shutil.copyfile(injected, layered)
                injected.unlink()
                chart_count = len(re.findall('data-chart-option=', layered.read_text(encoding='utf-8')))
            elif 'no chartref' in (r.stdout or ''):
                print('WARN chart options: exported %s but the SVG has no chartref__ placeholder,'
                      ' so nothing was injected. Name chart containers data-name="chartref__<name>".' % options)
            else:
                print('WARN chart injection failed (exit %d): %s' % (r.returncode, (r.stdout or r.stderr or '')[:300]))
        else:
            print('WARN chart options: %s' % err)

    # 6b. module -> sublayer structure (spec: module-background/photos/card-backgrounds/charts/icons/text)
    if args.layer_structure == 'module':
        structured = out / 'design-structured.svg'
        r = subprocess.run([sys.executable, str(HERE / 'structure_layers.py'),
                            '--in', str(layered), '--out', str(structured)],
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        if r.returncode == 0:
            before = svg_stats(layered)
            after = svg_stats(structured)
            same = (before['images'], before['texts'], before['chart_options']) ==                    (after['images'], after['texts'], after['chart_options'])
            if same:
                shutil.copyfile(structured, layered)
                print((r.stdout or '').strip())
            else:
                print('WARN structure changed element counts (%s -> %s); kept flat'
                      % ((before['images'], before['texts']), (after['images'], after['texts'])))
            structured.unlink(missing_ok=True)
        else:
            print('WARN structure_layers failed: %s' % (r.stdout or r.stderr or '')[:300])

    # 7. compatibility check
    check = out / '校验结果.txt'
    r = subprocess.run([sys.executable, str(HERE / 'figma_compat.py'), '--svg', str(layered),
                        '--assets', str(assets)],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    (out / '校验结果.txt').write_text(
        (r.stdout or "") + ('\n[stderr]\n' + (r.stderr or "") if r.stderr else '') +
        '\n[exit] %d\n' % r.returncode, encoding='utf-8')
    print(r.stdout or "")

    stats = svg_stats(layered)
    stats['asset_geom'] = config['assets']
    write_manifest(out, layered, jobs, boxes, stats, chart_count)
    print('\n=== RESULT ===')
    print('SVG: %s (%.2f MB)' % (layered, stats['bytes'] / 1048576))
    print('images=%d (base64=%d, relative=%d) texts=%d groups=%d chart-options=%d' % (
        stats['images'], stats['b64'], stats['relative_href'], stats['texts'],
        stats['groups'], chart_count))
    print('compat exit=%d, report: %s' % (r.returncode, check))

    if stats['images'] == 0 and not args.allow_empty_images:
        print('', flush=True)
        print('FAIL: the SVG has 0 images. Text alone is not a design source: cards,', flush=True)
        print('backgrounds, icons and chart placeholders are all missing. Usual causes:', flush=True)
        print('  1. the HTML has no data-name / data-el on visual blocks;', flush=True)
        print('  2. data-name values do not use the whitelist prefixes', flush=True)
        print('     (page-bg / title-bar-bg / filter-bar-bg / table-bg / panel-header /', flush=True)
        print('      filter-bar / table-header / table-rows / card__ / panelbg__ / chartref__);', flush=True)
        print('  3. visual blocks are smaller than 20x10 px or hidden at measure time.', flush=True)
        print('Preflight the HTML first: python scripts/preflight_html.py --html <file>', flush=True)
        raise SystemExit(3)


if __name__ == '__main__':
    main()
