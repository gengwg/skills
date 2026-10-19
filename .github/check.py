#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ["pyyaml"]
# ///
"""Repo consistency checks: skill frontmatter, README table, plugin versions."""
import json, re, sys
from pathlib import Path

import yaml

root = Path(__file__).resolve().parent.parent
errors = []

readme = (root / "README.md").read_text()
skills = sorted(p.parent for p in root.glob("*/SKILL.md"))
for d in skills:
    text = (d / "SKILL.md").read_text()
    fm = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not fm:
        errors.append(f"{d.name}: SKILL.md has no frontmatter")
        continue
    try:
        fields = yaml.safe_load(fm.group(1))
    except yaml.YAMLError as e:
        errors.append(f"{d.name}: frontmatter is not valid YAML: {e}")
        continue
    if fields.get("name") != d.name:
        errors.append(f"{d.name}: frontmatter name is {fields.get('name')!r}")
    if not fields.get("description"):
        errors.append(f"{d.name}: empty description")
    if f"[{d.name}]({d.name}/SKILL.md)" not in readme:
        errors.append(f"{d.name}: missing from README table")

plugin = json.loads((root / ".claude-plugin/plugin.json").read_text())
market = json.loads((root / ".claude-plugin/marketplace.json").read_text())
market_versions = {p["version"] for p in market["plugins"]}
if market_versions != {plugin["version"]}:
    errors.append(f"version mismatch: plugin.json {plugin['version']}, marketplace.json {sorted(market_versions)}")

print("\n".join(errors) or f"ok: {len(skills)} skills")
sys.exit(1 if errors else 0)
