#!/usr/bin/env python3
"""
参考图 vs HTML 截图的客观还原校验。
用法:
  python verify_reference_match.py --reference <原图> --render <HTML截图> [--out <报告.json>] [--threshold 0.70]
输出: 全局 SSIM + 分区 SSIM + 是否达标。不达标 exit code 1，用于卡住交付。

设计要点:
- 两张图尺寸/比例可能不同 -> 先统一缩放到同一网格(默认 480x270)。
- SSIM 用灰度 + 边缘图两个信号: 灰度抓明暗结构, 边缘抓布局/轮廓(深蓝科技风颜色接近, 光靠颜色会虚高)。
- 分区评分: 定位到底是哪个模块画歪了, 便于迭代, 而不是只有一个总分。
"""
import argparse, json, sys
from PIL import Image, ImageFilter
import numpy as np

try:
    from skimage.metrics import structural_similarity as ssim
except ImportError:
    print("缺少 scikit-image: pip install scikit-image", file=sys.stderr)
    sys.exit(2)

REGIONS = {
    "标题栏":      (0.00, 0.00, 1.00, 0.10),
    "左上区域":    (0.00, 0.10, 0.24, 0.42),
    "左中区域":    (0.00, 0.42, 0.24, 0.75),
    "左下区域":    (0.00, 0.75, 0.24, 1.00),
    "中央主视觉":  (0.24, 0.10, 0.76, 0.88),
    "右上区域":    (0.76, 0.10, 1.00, 0.42),
    "右中区域":    (0.76, 0.42, 1.00, 0.75),
    "右下区域":    (0.76, 0.75, 1.00, 1.00),
    "底部栏":      (0.24, 0.88, 1.00, 1.00),
}

def load_gray_edges(path, size):
    im = Image.open(path).convert("RGB").resize(size, Image.Resampling.LANCZOS)
    gray = np.asarray(im.convert("L"), dtype=np.float32)
    edges = np.asarray(im.convert("L").filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    return gray, edges

def score(a, b):
    g = ssim(a[0], b[0], data_range=255)
    e = ssim(a[1], b[1], data_range=255) if a[1].std() > 1 and b[1].std() > 1 else 0.0
    return 0.5 * g + 0.5 * e, g, e

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", required=True, help="参考图路径")
    ap.add_argument("--render", required=True, help="HTML 截图路径")
    ap.add_argument("--out", default=None, help="报告 JSON 输出路径")
    ap.add_argument("--threshold", type=float, default=0.70, help="全局得分达标线 (默认0.70)")
    ap.add_argument("--grid", default="480x270", help="配准网格 (默认480x270)")
    args = ap.parse_args()

    try:
        w, h = (int(x) for x in args.grid.lower().split("x"))
    except Exception:
        print("--grid 格式应为 WIDTHxHEIGHT", file=sys.stderr); sys.exit(2)

    ref = load_gray_edges(args.reference, (w, h))
    ren = load_gray_edges(args.render, (w, h))
    overall, g, e = score(ref, ren)

    parts = {}
    for name, (x1, y1, x2, y2) in REGIONS.items():
        xs, xe = int(x1 * w), int(x2 * w)
        ys, ye = int(y1 * h), int(y2 * h)
        ra = (ref[0][ys:ye, xs:xe], ref[1][ys:ye, xs:xe])
        rb = (ren[0][ys:ye, xs:xe], ren[1][ys:ye, xs:xe])
        if ra[0].size == 0: continue
        s, gg, ee = score(ra, rb)
        parts[name] = round(float(s), 4)

    worst = sorted(parts.items(), key=lambda kv: kv[1])[:3]
    report = {
        "reference": args.reference,
        "render": args.render,
        "grid": args.grid,
        "overall": round(float(overall), 4),
        "gray_ssim": round(float(g), 4),
        "edge_ssim": round(float(e), 4),
        "threshold": args.threshold,
        "passed": bool(overall >= args.threshold),
        "regions": parts,
        "worst_regions": worst,
    }
    print(f"全局还原得分: {overall:.3f} (灰度 {g:.3f} / 边缘 {e:.3f})  达标线 {args.threshold} -> {'通过' if report['passed'] else '不通过'}")
    print("最差 3 个区域: " + ", ".join(f"{n} {s:.3f}" for n, s in worst))
    if args.out:
        import os
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print("报告:", args.out)
    sys.exit(0 if report["passed"] else 1)

if __name__ == "__main__":
    main()
