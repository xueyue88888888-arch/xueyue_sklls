#!/usr/bin/env python3
"""Split an ECharts canvas into independent layers (base / connectors / markers / labels).

`series[i].show = false` is unreliable for line/scatter series, so this drives the
chart API by emptying `data` instead — deterministic and repaint-safe.

Usage:
    python slice_charts.py --html page/index.html --width 2752 --height 1204 \
        --mount '#china-map' --base-series mapGeo,mapDots \
        --layers routes=mapRoutes points=mapCities,mapHubGlow \
        -o charts/ --scale 3

Output:
    charts/<layer>.png        transparent PNG per layer
    charts/base.png           everything except the listed layers
    charts/labels.json        label text runs (x/y/size/colour/anchor) for real <text>
    charts/boxes.json         capture box of the chart
"""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

TRANSPARENT_CSS = """
html, body { background: transparent !important; background-image: none !important; }
#dashboard, .panel, .chart-card, .glass-card, .echart-mount,
#china-map, .map, .stage { background: transparent !important; background-image: none !important; }
"""

HELPER = r"""
window.__chartLayer = function (arg) {
  const [mountSel, showIds, hideIds, keepGeo] = arg;
  const host = document.querySelector(mountSel);
  if (!host) return {err: 'mount not found'};
  const dom = host.querySelector('.echart-mount') || host;
  const chart = echarts.getInstanceByDom(dom);
  if (!chart) return {err: 'chart instance not found'};
  if (!window.__orig) {
    window.__orig = {};
    (chart.getOption().series || []).forEach(s => {
      window.__orig[s.id] = JSON.parse(JSON.stringify(s.data || []));
    });
  }
  const series = Object.keys(window.__orig).map(id => {
    const on = showIds.indexOf(id) >= 0;
    return {id: id, data: on ? window.__orig[id] : []};
  });
  chart.setOption({geo: [{show: !!keepGeo}], series: series}, {lazyUpdate: false});
  dom.querySelectorAll('svg text').forEach(t => t.remove());
  return {shown: showIds, hidden: hideIds};
};
window.__labels = function (mountSel) {
  const host = document.querySelector(mountSel);
  const dom = host.querySelector('.echart-mount') || host;
  const hr = host.getBoundingClientRect();
  return [...dom.querySelectorAll('svg text')].map(t => {
    const r = t.getBoundingClientRect(); const cs = getComputedStyle(t);
    return {text: t.textContent.trim(), x: +(r.x - hr.x).toFixed(2), y: +(r.y - hr.y).toFixed(2),
            w: +r.width.toFixed(2), h: +r.height.toFixed(2), fontSize: cs.fontSize,
            fill: cs.fill, anchor: t.getAttribute('text-anchor') || 'start'};
  }).filter(o => o.text);
};
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--html', required=True)
    ap.add_argument('--width', type=int, required=True)
    ap.add_argument('--height', type=int, required=True)
    ap.add_argument('--mount', required=True, help="CSS selector of the chart host")
    ap.add_argument('--layers', required=True,
                    help='name=id1,id2 separate multiple layers with ";" e.g. "routes=mapRoutes;points=mapCities,mapHubGlow"')
    ap.add_argument('--geo-on-base', action='store_true',
                    help='keep the geo/map component rendered on the base layer')
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--scale', type=int, default=3)
    ap.add_argument('--browser', default=None)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    layers = []
    for chunk in args.layers.split(';'):
        if not chunk.strip():
            continue
        name, ids = chunk.split('=')
        layers.append((name.strip(), [i.strip() for i in ids.split(',') if i.strip()]))

    with sync_playwright() as p:
        launch = {'headless': True, 'args': ['--allow-file-access-from-files', '--hide-scrollbars']}
        if args.browser:
            launch['executable_path'] = args.browser
        browser = p.chromium.launch(**launch)
        page = browser.new_page(viewport={'width': args.width, 'height': args.height},
                                device_scale_factor=args.scale)
        page.goto(Path(args.html).resolve().as_uri(), wait_until='load', timeout=180000)
        page.wait_for_timeout(1600)
        page.add_script_tag(content=HELPER)

        labels = page.evaluate('(s) => window.__labels(s)', args.mount)
        (out / 'labels.json').write_text(json.dumps(labels, ensure_ascii=False, indent=1),
                                         encoding='utf-8')

        page.add_style_tag(content=TRANSPARENT_CSS)
        rect = page.evaluate("""(s) => { const r = document.querySelector(s).getBoundingClientRect();
                              return {x: r.x, y: r.y, w: r.width, h: r.height}; }""", args.mount)
        (out / 'boxes.json').write_text(json.dumps({'chart': rect}, ensure_ascii=False, indent=1),
                                        encoding='utf-8')
        clip = {'x': rect['x'], 'y': rect['y'], 'width': rect['w'], 'height': rect['h']}

        plan = [('base', [], 'base')] + [(name, ids, name) for name, ids in layers]
        for name, ids, fname in plan:
            info = page.evaluate('(a) => window.__chartLayer(a)',
                                 [args.mount, ids, [], args.geo_on_base if name == 'base' else False])
            page.wait_for_timeout(700)
            f = out / (fname + '.png')
            page.screenshot(path=str(f), clip=clip, omit_background=True, animations='disabled')
            print('%-12s %s  %dKB' % (name, info, f.stat().st_size // 1024))
        browser.close()


if __name__ == '__main__':
    main()
