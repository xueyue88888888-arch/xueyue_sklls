#!/usr/bin/env python3
"""Validate every skill folder in this monorepo.

Rules:
  - a skill = a top-level directory containing SKILL.md
  - SKILL.md must start with YAML frontmatter delimited by ---
  - frontmatter needs `name` and `description`
  - `name` must equal the folder name
  - description should be long enough to tell an agent WHEN to use the skill
Exit code 1 on any error (warnings don't fail).
"""
import pathlib
import re
import sys

SKIP = {'.git', '.github', 'node_modules'}


def frontmatter(text):
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.S)
    return m.group(1) if m else None


def field(fm, key):
    m = re.search(r'^%s:\s*(.+?)\s*$' % key, fm, re.M)
    if not m:
        return None
    return m.group(1).strip().strip('"\'')


def main(root='.'):
    root = pathlib.Path(root)
    errors, warnings, count = [], [], 0
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        if d.name in SKIP:
            continue
        skill = d / 'SKILL.md'
        if not skill.is_file():
            if any(d.iterdir()):
                errors.append('%s: directory has content but no SKILL.md' % d.name)
            continue
        count += 1
        text = skill.read_text(encoding='utf-8')
        fm = frontmatter(text)
        if fm is None:
            errors.append('%s: SKILL.md has no YAML frontmatter' % d.name)
            continue
        name, desc = field(fm, 'name'), field(fm, 'description')
        if not name:
            errors.append('%s: frontmatter missing `name`' % d.name)
        elif name != d.name:
            errors.append('%s: frontmatter name "%s" != folder name' % (d.name, name))
        if not desc:
            errors.append('%s: frontmatter missing `description`' % d.name)
        elif len(desc) < 40:
            warnings.append('%s: description is very short — write it so the agent knows WHEN to use it'
                            % d.name)
        if 'allowed-tools' not in fm:
            warnings.append('%s: no `allowed-tools` declared' % d.name)

    for w in warnings:
        print('::warning::%s' % w)
    for e in errors:
        print('::error::%s' % e)
    print('skills found: %d | errors: %d | warnings: %d' % (count, len(errors), len(warnings)))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else '.'))
