#!/usr/bin/env python3
"""Slice "card chrome" (background + border + corner cut + inner glow + child dividers)
WITHOUT the text and icon content, keeping the page layout untouched.

Why in-place: a card's border/glow often comes from ancestor selectors, and its outer
glow is the element edge blending with whatever sits behind it. A detached clone loses
both. So we never clone — we hide text and icons globally, then crop the real page.

Usage:
    python slice_cards.py --html page/index.html --width 2752 --height 1204 \
        --jobs jobs.json -o slices/

jobs.json:
    [
      {"name": "card-kpi-1", "selector": ".kpi",      "index": 0},
      {"name": "card-kpi-2", "selector": ".kpi",      "index": 1},
      {"name": "strip-1",    "selector": ".metric-strip", "index": 0, "hide_children": true}
    ]

Notes:
- "hide_children": true also removes the element's own subtree (use it for a bar whose
  children are sliced separately).
- Each slice is expanded by `--pad` px (default 1) so the anti-aliased edge that blends
  with the backdrop is baked in. Place the PNG at (x-pad, y-pad) when composing.
"""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

# Kill text ink and icon imagery, keep every box, border, shadow and pseudo element.
STRIP_CSS = """
#dashboard *, body > * { color: transparent !important; text-shadow: none !important; }
svg.icon, svg.feature-icon, svg.gauge { display: none !important; }
[class*="icon"] { background-image: none !important; }
"""

PREP = r"""
(arg) => {
  const [sel, idx, pad, hideChildren] = arg;
  document.querySelectorAll('.__hideme').forEach(n => n.classList.remove('__hideme'));
  const el = [...document.querySelectorAll(sel)][idx];
  if (!el) return null;
  if (hideChildren) {
    el.querySelectorAll('*').forEach(n => { n.style.visibility = 'hidden'; });
  }
  const r = el.getBoundingClientRect();
  return {x: r.x - pad, y: r.y - pad, w: r.width + pad * 2, h: r.height + pad * 2};
}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--html', required=True)
    ap.add_argument('--width', type=int, required=True)
    ap.add_argument('--height', type=int, required=True)
    ap.add_argument('--jobs', required=True)
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--pad', type=int, default=1)
    ap.add_argument('--scale', type=int, default=2, help='device pixel ratio for the capture')
    ap.add_argument('--ready', default=None,
                    help='JS expression to run after load (e.g. stop timers)')
    ap.add_argument('--browser', default=None)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = json.loads(Path(args.jobs).read_text(encoding='utf-8'))

    with sync_playwright() as p:
        launch = {'headless': True, 'args': ['--allow-file-access-from-files', '--hide-scrollbars']}
        if args.browser:
            launch['executable_path'] = args.browser
        browser = p.chromium.launch(**launch)
        page = browser.new_page(viewport={'width': args.width, 'height': args.height},
                                device_scale_factor=args.scale)
        page.goto(Path(args.html).resolve().as_uri(), wait_until='load', timeout=180000)
        page.wait_for_timeout(1200)
        if args.ready:
            page.evaluate(args.ready)
        page.add_style_tag(content=STRIP_CSS)
        page.wait_for_timeout(300)

        boxes = {}
        for job in jobs:
            box = page.evaluate(PREP, [job['selector'], job.get('index', 0),
                                       args.pad, bool(job.get('hide_children'))])
            if not box:
                print('MISS', job['name'], job['selector'], job.get('index', 0))
                continue
            f = out / (job['name'] + '.png')
            page.screenshot(path=str(f), clip=box, animations='disabled')
            boxes[job['name']] = box
            print('%-24s %.1fx%.1f @(%.1f,%.1f) %dKB' % (
                job['name'], box['w'], box['h'], box['x'], box['y'], f.stat().st_size // 1024))
        (out / 'boxes.json').write_text(json.dumps(boxes, ensure_ascii=False, indent=1),
                                        encoding='utf-8')
        browser.close()


if __name__ == '__main__':
    main()
