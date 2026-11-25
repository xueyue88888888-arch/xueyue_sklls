#!/usr/bin/env python3
"""检查一个 HTML 是否满足"可切图设计源"的输入契约。给清单式报告，不通过就明确指出要改什么。
用法: python preflight_html.py --html <index.html> [--charts-dir <HTML所在目录>]
纯静态检查，不依赖浏览器。
"""
import argparse, re, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--html', required=True)
ap.add_argument('--charts-dir', default=None, help='HTML所在目录，用于检查本地资源(JS/图片)是否存在')
a = ap.parse_args()

html = Path(a.html).read_text(encoding='utf-8', errors='replace')
# 去掉注释再检查，避免注释里的 "no mask" 之类误报
html_check = re.sub(r'<!--[\s\S]*?-->', '', html)
html_check = re.sub(r'/\*[\s\S]*?\*/', '', html_check)
base = Path(a.charts_dir or Path(a.html).parent)

results = []  # (True/False/None, name, detail)
def check(ok, name, detail=''):
    results.append((bool(ok), name, detail))

# 1) 静态模式
static = bool(re.search(r'STATIC_MODE|\?live=1|live=1', html_check))
has_motion = bool(re.search(r'setInterval|@keyframes|animation\s*:|transition\s*:', html_check))
if not static and has_motion:
    check(False, '静态模式开关', '有动效但没关掉：应有 STATIC_MODE / ?live=1，否则无法精确切图')
elif not static:
    results.append((None, '静态模式开关', '未声明静态开关，但页面无动效，可视为静态'))
else:
    check(True, '静态模式开关')

# 2) 双命名
dn = len(re.findall(r'data-name=', html_check))
de = len(re.findall(r'data-el=', html_check))
check(dn > 0, 'data-name 命名', f'找到 {dn} 处；下游 svg2fvs 只认 data-name 白名单前缀')
check(de > 0, 'data-el 命名', f'找到 {de} 处；建议 data-el/data-name 双写')

# 3) 语义白名单前缀
whitelist = ['page-bg', 'title-bar-bg', 'panel-header', 'filter-bar', 'table-header', 'table-rows',
             'panelbg__', 'card__', 'chartref__', 'photo__', 'icon__', 'page-bg__']
hit = [w for w in whitelist if w in html_check]
check(len(hit) >= 3, '语义前缀覆盖', f'命中 {len(hit)} 类: {", ".join(hit)}；建议至少 3 类')

# 4) 真实 DOM 文本
text_runs = len(re.findall(r'>\s*[^<>\d\s][^<>]{0,40}\s*<', html_check))
check(text_runs >= 10, '真实文本节点', f'约 {text_runs} 个；文字必须是 DOM 文本' if text_runs < 10 else f'{text_runs} 个')

# 5) 禁用 CSS（检查去注释后的内容）
banned = []
for pat, label in [(r'background-clip\s*:\s*text', 'background-clip:text'),
                   (r'backdrop-filter', 'backdrop-filter'),
                   (r'(?<![\w-])mask\s*:', 'mask'),
                   (r'-webkit-mask', '-webkit-mask')]:
    if re.search(pat, html_check, re.I): banned.append(label)
check(not banned, '无禁用 CSS', '发现: ' + ', '.join(banned) if banned else '')

# 6) 固定画布
fixed = bool(re.search(r'(width\s*:\s*\d{3,4}px[\s\S]{0,80}height\s*:\s*\d{3,4}px)|(#canvas|#stage)[^{]*\{[^}]*\d{3,4}px', html_check))
check(fixed, '固定画布尺寸', '应有固定 px 画布(如 1920x1080)，不要响应式' if not fixed else '')

# 7) 图表
has_echarts = 'echarts' in html_check.lower()
has_init = bool(re.search(r'echarts\.init', html_check))
if has_echarts:
    check(has_init, '图表可采集', '有 echarts 但没找到 echarts.init；图表数据无法注入 SVG' if not has_init else '')
    srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html_check)
    missing = [s for s in srcs if not s.startswith(('http', 'data:')) and not (base / s).exists()]
    check(not missing, '本地JS资源齐全', '缺失: ' + ', '.join(missing) if missing else '')
else:
    results.append((None, '图表', '未检测到 ECharts；若无图表可忽略此条'))

print('\n=== HTML 输入契约检查 ===')
for ok, name, detail in results:
    mark = '✅' if ok is True else ('❌' if ok is False else 'ℹ️ ')
    print(f'{mark} {name}' + (f' — {detail}' if detail else ''))
fails = sum(1 for ok, _, _ in results if ok is False)
print(f'\n失败 {fails} 项' + ('；修完再进入切图流程。' if fails else '；可以进入切图流程。'))
sys.exit(1 if fails else 0)
