#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sqlguard — SQL 交付质量门禁（通用，不绑库表）

用法:
    python sqlguard.py check <文件|-> [--profile doris|mysql|postgres] [--json] [--no-style]
    python sqlguard.py rules [--profile XX]

退出码: 0 通过 / 1 有 P0 / 2 用法错误
"""
import sys, os, re, json, argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RULES_DIR = ROOT / "rules"

WS = "[" + "".join(chr(c) for c in (32, 9, 10, 13)) + "]"
WORD = "[A-Za-z0-9_]"
FW = "，；：（）［］｛｝"
INVISIBLE = {"\u200b": "零宽空格", "\u200c": "零宽连接符", "\u200d": "零宽连字号",
             "\u2018": "左弯引号", "\u2019": "右弯引号", "\ufeff": "BOM"}


def read_text(path):
    if path == "-":
        return sys.stdin.buffer.read().decode("utf-8", "replace")
    return Path(path).read_bytes().decode("utf-8", "replace")


def mask(text):
    """把注释和字符串内容替换成空格（保持长度与换行），用于代码区检查。"""
    out = list(text)
    i, n, quote = 0, len(text), None

    def blank(a, b):
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        ch = text[i]
        if quote is None:
            if text.startswith("--", i):
                j = text.find("\n", i)
                j = n if j < 0 else j
                blank(i, j); i = j; continue
            if text.startswith("/*", i):
                j = text.find("*/", i + 2)
                j = n if j < 0 else j + 2
                blank(i, j); i = j; continue
            if ch in ("'", '"'):
                quote = ch; blank(i, i + 1); i += 1; continue
            i += 1
        else:
            if ch == quote:
                if i + 1 < n and text[i + 1] == quote:
                    blank(i, i + 2); i += 2; continue
                blank(i, i + 1); quote = None; i += 1; continue
            blank(i, i + 1); i += 1
    return "".join(out)


def strings_with_pos(text):
    """返回 [(内容, 起始偏移)]，用于检查字面量里的隐藏字符。"""
    res, i, n, quote, start = [], 0, len(text), None, 0
    while i < n:
        ch = text[i]
        if quote is None:
            if text.startswith("--", i):
                j = text.find("\n", i); i = n if j < 0 else j; continue
            if text.startswith("/*", i):
                j = text.find("*/", i + 2); i = n if j < 0 else j + 2; continue
            if ch in ("'", '"'):
                quote = ch; start = i + 1
            i += 1
        else:
            if ch == quote:
                res.append((text[start:i], start))
                quote = None
            i += 1
    return res


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def line_snippet(text, offset, width=96):
    s = text.rfind("\n", 0, offset) + 1
    e = text.find("\n", offset)
    e = len(text) if e < 0 else e
    seg = text[s:e].strip()
    return seg if len(seg) <= width else seg[:width - 1] + "…"


class Issue:
    def __init__(self, rid, level, title, line, snippet, fix, why):
        self.id, self.level, self.title = rid, level, title
        self.line, self.snippet, self.fix, self.why = line, snippet, fix, why

    def as_dict(self):
        return {"id": self.id, "level": self.level, "title": self.title,
                "line": self.line, "snippet": self.snippet, "fix": self.fix}


# ---------- custom checks ----------

def chk_invisible(text, masked):
    out = []
    for content, pos in strings_with_pos(text):
        found = [desc for ch, desc in INVISIBLE.items() if ch in content]
        if found:
            out.append(Issue("S02", "P0", "字面量里含" + "、".join(found), line_of(text, pos),
                             line_snippet(text, pos), "删掉隐藏字符、弯引号改直引号后重写该字面量",
                             "含隐藏字符的值肉眼完全一样，匹配却永远不中"))
    return out


def chk_division(masked, text):
    out = []
    for m in re.finditer(r"/\s*\(?\s*(count|sum|avg)\s*\(", masked, re.I):
        # 往前看 200 字符内是否已有 NULLIF 包住分母
        ctx = masked[max(0, m.start() - 200):m.end() + 40]
        if re.search(r"nullif\s*\(", ctx, re.I):
            continue
        out.append(Issue("S03", "P0", "除法分母没有 NULLIF 保护", line_of(text, m.start()),
                         line_snippet(text, m.start()),
                         "把分母包起来：/ NULLIF(SUM(x), 0)；比例再套 ROUND(..., 2)",
                         "分母为 0 时要么报错要么返回 NULL，占比列直接空白"))
    return out


HEADER_KEYS = ("用途", "口径", "对账")


def chk_header(text):
    head = "\n".join(text.splitlines()[:40])
    miss = [k for k in HEADER_KEYS if k not in head]
    if not miss:
        return []
    return [Issue("S12", "P1", "交付头注释缺：%s" % "、".join(miss), 1,
                  head.strip().splitlines()[0][:96] if head.strip() else "",
                  "按 references/delivery.md 的模板补：用途 / 口径 / 参数 / 输出 / 对账 / 变更",
                  "没有口径声明的 SQL，三个月后没人敢改，也没法验收")]


def chk_long_lines(text):
    out = []
    for idx, ln in enumerate(text.splitlines(), 1):
        if len(ln) > 120:
            out.append(Issue("S15", "P1", "单行 %d 字符" % len(ln), idx, ln.strip()[:96],
                             "按 SELECT / FROM / WHERE / GROUP BY 分段换行",
                             "横向滚动会让人跳过整段代码"))
    return out[:5]


KW = ("select", "from", "where", "group by", "order by", "join", "left join",
      "inner join", "with", "having", "union all", "case when")


def chk_keyword_case(masked):
    up = lo = 0
    for k in KW:
        up += len(re.findall(r"(?<![\w])" + k.upper() + r"(?![\w])", masked))
        lo += len(re.findall(r"(?<![\w])" + k + r"(?![\w])", masked))
    if up and lo:
        return [Issue("S16", "P1", "关键字大小写混用（大写 %d 处 / 小写 %d 处）" % (up, lo), 1, "",
                      "统一成大写关键字", "混用时分不清哪个是关键字、哪个是字段名")]
    return []


def chk_window(masked, text):
    out = []
    for m in re.finditer(r"(?is)row_number\s*\(\s*\)\s*over\s*\(([^)]*)\)", masked):
        body = m.group(1)
        om = re.search(r"(?is)order\s+by\s+(.+)$", body)
        if not om:
            continue
        keys = [k for k in om.group(1).split(",") if k.strip()]
        if len(keys) < 2:
            out.append(Issue("S22", "P2", "取最新一条但 ORDER BY 只有 1 个排序键",
                             line_of(text, m.start()), line_snippet(text, m.start()),
                             "补上第二排序键，如 ORDER BY aedtm DESC, begda DESC, seqnr DESC",
                             "同一时间多条记录时取到哪条不确定，今天对明天错"))
    return out


def chk_table_alias(masked, text):
    hits = {}
    ws = "[" + "".join(chr(c) for c in (32, 9, 10, 13)) + "]"
    pattern = "(?i)(?:from|join)" + ws + "+([A-Za-z0-9_.$]+)" + ws + "+(?:as" + ws + "+)?([a-z]|t[0-9]+)(?![A-Za-z0-9_(])"
    for m in re.finditer(pattern, masked):
        hits.setdefault(m.group(2), []).append(m.start())
    out = []
    for alias, pos in hits.items():
        out.append(Issue("S13", "P1", "表别名 `%s` 无意义（%d 处）" % (alias, len(pos)),
                         line_of(text, pos[0]), line_snippet(text, pos[0]), "", ""))
    return out[:4]


def strip_comments(text):
    out = list(text)
    i, n, quote = 0, len(text), None
    while i < n:
        ch = text[i]
        if quote is None:
            if text.startswith("--", i):
                j = text.find(chr(10), i)
                j = n if j < 0 else j
                for k in range(i, j):
                    if out[k] != chr(10):
                        out[k] = " "
                i = j
                continue
            if text.startswith("/*", i):
                j = text.find("*/", i + 2)
                j = n if j < 0 else j + 2
                for k in range(i, j):
                    if out[k] != chr(10):
                        out[k] = " "
                i = j
                continue
            if ch in ("'", '"'):
                quote = ch
            i += 1
        else:
            if ch == quote:
                quote = None
            i += 1
    return "".join(out)


def chk_hardcoded_date(text, masked):
    code = strip_comments(text)
    pat = "(?i)(" + WS + "*date" + WS + "*'|')" + WS + "*(20[0-9][0-9])-([0-9][0-9])-([0-9][0-9])"
    out, seen = [], set()
    for m in re.finditer(pat, code):
        day = "-".join(m.group(2, 3, 4))
        if day in seen:
            continue
        seen.add(day)
        out.append(Issue("S17", "P1", "硬编码日期 " + day, line_of(text, m.start()),
                         line_snippet(text, m.start()),
                         "改成参数 ${data_dt}，或提到最前面的 CTE 里定义一次",
                         "写死的日期明年就错，也没人记得回来改"))
    return out[:3]


def chk_partition(masked, text):
    pat = "(?i)(from|join)" + WS + "+([A-Za-z0-9_]+[.])?(dwd_|dws_|ads_|ods_|dim_)" + WORD + "+"
    m = re.search(pat, masked)
    if not m:
        return []
    colref = "(^|[^A-Za-z0-9_])(data_dt|pt)([^A-Za-z0-9_]|$)"
    if re.search("(?i)" + colref, masked, re.M):
        return []
    return [Issue("S21", "P2", "查数仓表但没有日期/分区条件", line_of(text, m.start()),
                  line_snippet(text, m.start()),
                  "加 data_dt = ${data_dt} 或 pt BETWEEN ... 或 data_dt >= ...",
                  "无分区条件等于全表扫描，查一次几十秒")]


CUSTOM = {
    "hardcoded_date": lambda text, masked: chk_hardcoded_date(text, masked),
    "table_alias": lambda text, masked: chk_table_alias(masked, text),
    "invisible_chars": lambda text, masked: chk_invisible(text, masked),
    "division_guard": lambda text, masked: chk_division(masked, text),
    "header_block": lambda text, masked: chk_header(text),
    "long_lines": lambda text, masked: chk_long_lines(text),
    "keyword_case": lambda text, masked: chk_keyword_case(masked),
    "partition_filter": lambda text, masked: chk_partition(masked, text),
    "window_order": lambda text, masked: chk_window(masked, text),
}


def load_rules(profile):
    files = [RULES_DIR / "common.json"]
    if profile:
        p = RULES_DIR / ("%s.json" % profile)
        if not p.exists():
            print("没有这个方言的规则文件: %s（可选: %s）；先用通用规则跑" % (
                p, ", ".join(sorted(x.stem for x in RULES_DIR.glob("*.json") if x.stem != "common"))),
                file=sys.stderr)
            sys.exit(2)
        files.append(p)
    rules = []
    for f in files:
        rules += json.loads(f.read_text(encoding="utf-8"))["rules"]
    return rules


def run(text, rules):
    masked = mask(text)
    issues = []
    for r in rules:
        if r["type"] == "regex":
            for m in re.finditer(r["pattern"], masked):
                issues.append(Issue(r["id"], r["level"], r["title"], line_of(text, m.start()),
                                    line_snippet(text, m.start()), r["fix"], r["why"]))
        elif r["type"] == "custom":
            fn = CUSTOM.get(r["check"])
            if fn:
                for it in fn(text, masked):
                    it.id, it.level, it.title = r["id"], r["level"], it.title
                    it.fix, it.why = r["fix"], r["why"]
                    issues.append(it)
    issues.sort(key=lambda x: (x.level, x.line, x.id))
    return issues


def style_report(text, masked, issues):
    total_lines = len(text.splitlines()) or 1
    has_cte = bool(re.search(r"(?i)\bwith\b", masked))
    dims = {
        "结构": (0 if not has_cte else 3) + (0 if re.search(r"(?i)\bfrom\s+\(", masked) else 2),
        "命名": 4 - len([i for i in issues if i.id in ("S13",)]),
        "可读": 7 - len([i for i in issues if i.id in ("S11", "S14", "S15", "S16", "S18")]),
        "正确": 8 - len([i for i in issues if i.level == "P0"]),
    }
    dims = {k: max(0, v) for k, v in dims.items()}
    cap = {"结构": 5, "命名": 4, "可读": 7, "正确": 8}
    score = int(round(sum(dims[k] / cap[k] for k in dims) / len(dims) * 100))
    return dims, cap, score


def _setup_io():
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main():
    _setup_io()
    ap = argparse.ArgumentParser(prog="sqlguard")
    sub = ap.add_subparsers(dest="cmd")

    c = sub.add_parser("check", help="检查一个 SQL 文件")
    c.add_argument("target")
    c.add_argument("--profile", default=None, help="方言规则: doris / mysql / postgres")
    c.add_argument("--json", action="store_true")
    c.add_argument("--no-style", action="store_true", help="不输出风格分")

    r = sub.add_parser("rules", help="列出规则")
    r.add_argument("--profile", default=None)

    args = ap.parse_args()
    if args.cmd == "rules":
        for x in load_rules(args.profile):
            print("%-4s %-3s %s" % (x["id"], x["level"], x["title"]))
        return 0
    if args.cmd != "check":
        ap.print_help(); return 2

    text = read_text(args.target)
    if not text.strip():
        print("空文件", file=sys.stderr); return 2

    issues = run(text, load_rules(args.profile))
    p0 = [i for i in issues if i.level == "P0"]
    dims, cap, score = style_report(text, mask(text), issues)

    if args.json:
        print(json.dumps({"file": args.target, "profile": args.profile,
                          "p0": len(p0), "issues": [i.as_dict() for i in issues],
                          "score": score, "dims": dims}, ensure_ascii=False, indent=2))
    else:
        name = os.path.basename(args.target) if args.target != "-" else "<stdin>"
        print("检查 %s  方言 %s  规则 %d 条" % (name, args.profile or "(通用)", len(load_rules(args.profile))))
        print("─" * 68)
        if not issues:
            print("✓ 没有问题")
        for i in issues:
            mark = "✗" if i.level == "P0" else ("!" if i.level == "P1" else "·")
            loc = ("第 %d 行" % i.line) if i.line else ""
            print("%s %s %-4s %s  %s" % (mark, i.level, i.id, i.title, loc))
            if i.snippet:
                print("      %s" % i.snippet)
            print("      修：%s" % i.fix)
        print("─" * 68)
        if not args.no_style:
            print("风格  " + "  ".join("%s %d/%d" % (k, dims[k], cap[k]) for k in dims) +
                  "   综合 %d/100（仅供观察，判定只看 P0）" % score)
        print("结论：%s（P0 %d 条，P1 %d 条，P2 %d 条）" % (
            "不通过" if p0 else "通过",
            len(p0), len([i for i in issues if i.level == "P1"]),
            len([i for i in issues if i.level == "P2"])))
    return 1 if p0 else 0


if __name__ == "__main__":
    sys.exit(main())
