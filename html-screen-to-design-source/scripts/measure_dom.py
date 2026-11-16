#!/usr/bin/env python3
"""Dump rendered geometry of every visual element on a fixed-canvas HTML screen.

Usage:
    python measure_dom.py --html page/index.html --width 2752 --height 1204 -o geometry.json

Requires: playwright + a Chromium/Edge binary.
    pip install playwright

Output JSON:
    {
      "canvas": {"width": W, "height": H},
      "img":   [{file, cls, x, y, w, h, fit, opacity}],
      "bg":    [{file, cls, tag, x, y, w, h}],
      "blocks":[{sel, cls, x, y, w, h}],
      "text":  [{text, tag, cls, x, y, w, h, fontSize, fontWeight, color, textAlign,
                 letterSpacing, lineHeight, textShadow}]
    }
"""
import argparse
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

JS = r"""
() => {
  const name = (u) => {
    if (!u) return '';
    u = u.replace(/^url\(["']?/, '').replace(/["']?\)$/, '').split('#')[0];
    return decodeURIComponent(u.split(/[\\/]/).pop() || '');
  };
  const out = {img: [], bg: [], blocks: [], text: []};

  document.querySelectorAll('img').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;
    const cs = getComputedStyle(el);
    out.img.push({file: name(el.currentSrc || el.src), cls: String(el.className || ''),
      x: +r.x.toFixed(2), y: +r.y.toFixed(2), w: +r.width.toFixed(2), h: +r.height.toFixed(2),
      fit: cs.objectFit, opacity: cs.opacity});
  });

  document.querySelectorAll('*').forEach(el => {
    const cs = getComputedStyle(el);
    const m = (cs.backgroundImage || '').match(/url\(([^)]+)\)/);
    if (!m) return;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;
    out.bg.push({file: name(m[1]), cls: String(el.className || ''), tag: el.tagName,
      x: +r.x.toFixed(2), y: +r.y.toFixed(2), w: +r.width.toFixed(2), h: +r.height.toFixed(2)});
  });

  const BLOCK_SELECTORS = (window.__BLOCK_SELECTORS__ || []);
  BLOCK_SELECTORS.forEach(sel => {
    document.querySelectorAll(sel).forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) return;
      out.blocks.push({sel, cls: String(el.className || ''), x: +r.x.toFixed(2),
        y: +r.y.toFixed(2), w: +r.width.toFixed(2), h: +r.height.toFixed(2)});
    });
  });

  document.querySelectorAll('*').forEach(el => {
    const hasText = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!hasText) return;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (r.width < 1 || r.height < 1) return;
    if (cs.visibility === 'hidden' || cs.display === 'none') return;
    out.text.push({text: el.textContent.replace(/\s+/g, ' ').trim(), tag: el.tagName,
      cls: String(el.className || ''), x: +r.x.toFixed(2), y: +r.y.toFixed(2),
      w: +r.width.toFixed(2), h: +r.height.toFixed(2),
      fontSize: cs.fontSize, fontWeight: cs.fontWeight, color: cs.color,
      textAlign: cs.textAlign, letterSpacing: cs.letterSpacing, lineHeight: cs.lineHeight,
      textShadow: cs.textShadow, opacity: cs.opacity, transform: cs.transform});
  });

  return out;
}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--html', required=True)
    ap.add_argument('--width', type=int, required=True)
    ap.add_argument('--height', type=int, required=True)
    ap.add_argument('--blocks', default='.panel,.card,.kpi,.chart-card,.glass-card',
                    help='comma separated selectors treated as structural blocks')
    ap.add_argument('--browser', default=None, help='chromium executable path (optional)')
    ap.add_argument('--wait', type=int, default=1200, help='ms to settle after load')
    ap.add_argument('-o', '--out', required=True)
    args = ap.parse_args()

    with sync_playwright() as p:
        launch = {'headless': True, 'args': ['--allow-file-access-from-files', '--hide-scrollbars']}
        if args.browser:
            launch['executable_path'] = args.browser
        browser = p.chromium.launch(**launch)
        page = browser.new_page(viewport={'width': args.width, 'height': args.height},
                                device_scale_factor=1)
        page.goto(Path(args.html).resolve().as_uri(), wait_until='load', timeout=180000)
        page.wait_for_timeout(args.wait)
        page.evaluate('(sels) => { window.__BLOCK_SELECTORS__ = sels; }',
                      [s.strip() for s in args.blocks.split(',') if s.strip()])
        data = page.evaluate(JS)
        browser.close()

    data['canvas'] = {'width': args.width, 'height': args.height}
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    print('img %d | bg %d | blocks %d | text %d -> %s' % (
        len(data['img']), len(data['bg']), len(data['blocks']), len(data['text']), args.out))


if __name__ == '__main__':
    main()
