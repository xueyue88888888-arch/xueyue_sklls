#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则自测：确保每条规则不是空转、也不误杀。

cases/must_fail/<规则ID>_xxx.sql  必须命中该规则
cases/must_pass/*.sql             必须 0 个 P0
"""
import sys, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD = Path(__file__).resolve().parent / "sqlguard.py"


def check(path, profile):
    cmd = [sys.executable, str(GUARD), "check", str(path), "--json", "--no-style"]
    if profile:
        cmd += ["--profile", profile]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    data = json.loads(out.stdout)
    return data["issues"], out.returncode


def main():
    fails, total = [], 0
    for f in sorted((ROOT / "cases" / "must_fail").glob("*.sql")):
        total += 1
        rid = f.name.split("_")[0]
        profile = "doris" if rid.startswith("D") else None
        issues, _ = check(f, profile)
        got = {i["id"] for i in issues}
        if rid not in got:
            fails.append("漏报 %s（期望 %s，实际 %s）" % (f.name, rid, sorted(got) or "无"))

    for f in sorted((ROOT / "cases" / "must_pass").glob("*.sql")):
        total += 1
        issues, _ = check(f, "doris")
        p0 = [i for i in issues if i["level"] == "P0"]
        if p0:
            fails.append("误杀 %s（P0: %s）" % (f.name, [i["id"] for i in p0]))

    print("用例 %d 个，失败 %d 个" % (total, len(fails)))
    for x in fails:
        print("  ✗ " + x)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
