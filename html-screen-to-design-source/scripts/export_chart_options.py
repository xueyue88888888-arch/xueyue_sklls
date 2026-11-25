#!/usr/bin/env python3
"""Export every ECharts option on an HTML page to chart-options.json.

    python export_chart_options.py --html index.html --out work/ [--browser chrome.exe]

Output: <out>/chart-options.json -> {"<key>": {ECharts option}, ...}
  key = element data-name, else element id, else "chart-<i>".

Why this exists: the orchestrator used to call a collector that lived in one
machine's work/selftest folder. Everyone else got `collector not found`, the SVG
kept data-less chart placeholders, and the FVS had blank charts. This ships with
the skill and only needs playwright (already required for measuring/slicing).
"""
import argparse
import json
import os
import sys
from pathlib import Path

JS = r"""
(() => {
  const dash = window.echarts;
  if (!dash || typeof dash.getInstanceByDom !== 'function') {
    return { charts: [], reason: 'no window.echarts' };
  }
  const out = [];
  const strip = (v) => {
    if (typeof v === 'function') return undefined;
    if (Array.isArray(v)) return v.map(strip);
    if (v && typeof v === 'object') {
      const o = {};
      for (const k of Object.keys(v)) o[k] = strip(v[k]);
      return o;
    }
    return v;
  };
  const nodes = [...document.querySelectorAll('*')].filter((el) => {
    const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden';
  });
  for (const el of nodes) {
    let inst = null;
    try { inst = dash.getInstanceByDom(el); } catch (e) { inst = null; }
    if (!inst) continue;
    out.push({
      key: el.getAttribute('data-name') || el.id || '',
      option: strip(inst.getOption()),
    });
  }
  return { charts: out, reason: out.length ? '' : 'echarts loaded but no instance' };
})()
"""

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


def find_browser(explicit=None):
    for p in (explicit, os.environ.get('H2F_BROWSER'), os.environ.get('HTML2DESIGN_BROWSER')):
        if p and Path(p).exists():
            return str(Path(p).resolve())
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--html', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--browser', default=None)
    ap.add_argument('--wait', type=int, default=1500, help='ms after load for charts to draw')
    ap.add_argument('--width', type=int, default=1920)
    ap.add_argument('--height', type=int, default=1080)
    a = ap.parse_args()

    html = Path(a.html).resolve()
    out = Path(a.out).resolve()
    if not html.exists():
        print('html not found: %s' % html)
        return 2
    out.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright
    launch = {'headless': True, 'args': ['--allow-file-access-from-files', '--hide-scrollbars']}
    exe = find_browser(a.browser)
    if exe:
        launch['executable_path'] = exe
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch)
        page = browser.new_page(viewport={'width': a.width, 'height': a.height}, device_scale_factor=1)
        page.goto(html.as_uri(), wait_until='load', timeout=180000)
        page.wait_for_timeout(a.wait)
        result = page.evaluate(JS)
        browser.close()

    charts = result.get('charts') or []
    if not charts:
        print('no ECharts instance (%s)' % (result.get('reason') or 'unknown'))
        return 3

    def finite(v):
        """Replace Infinity/NaN with None.

        ECharts options routinely carry Infinity (e.g. axis `max` thresholds).
        json.dumps happily writes `Infinity`, which is NOT valid JSON, and the
        consumer (svg2fvs / JSON.parse) then drops the whole option — the chart
        silently became a blank slice.
        """
        import math
        if isinstance(v, float):
            return v if math.isfinite(v) else None
        if isinstance(v, list):
            return [finite(x) for x in v]
        if isinstance(v, dict):
            return {k: finite(x) for k, x in v.items()}
        return v

    options = {}
    used = set()
    for i, c in enumerate(charts):
        key = str(c.get('key') or 'chart-%d' % (i + 1))
        if key in used:
            key = '%s-%d' % (key, i + 1)
        used.add(key)
        options[key] = finite(c.get('option'))

    dest = out / 'chart-options.json'
    dest.write_text(json.dumps(options, ensure_ascii=False, indent=1), encoding='utf-8')
    print('chart-options: %d -> %s (%s)' % (len(options), dest, ', '.join(options)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
