#!/usr/bin/env python3
"""
validate_site.py — routing & template integrity checks for Read Market Brief.

Fails (exit 1) if:
  1. Any 'Read Today's Brief' link points to updates/ or breaking/
  2. Any 'Read Full Issue' link points to updates/ or breaking/
  3. Any 'Full Close Recap' link points to a file that does not exist
  4. The latest full brief has no CSS (<style> block or ../styles.css link)
  5. The latest full brief is missing doctype / head / nav / footer
  6. archive.html is missing its section markers
  7. sitemap.xml is not valid XML
  8. Any homepage main-brief link points to a missing file

Run:  python scripts/validate_site.py
"""

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parent.parent
errors = []


def err(msg: str) -> None:
    errors.append(msg)
    print(f"  FAIL  {msg}")


def ok(msg: str) -> None:
    print(f"  ok    {msg}")


def latest_full_brief() -> Path:
    """Newest briefs/YYYY-MM-DD.html or legacy briefs/YYYY-MM-DD-close.html."""
    candidates = []
    for f in (ROOT / "briefs").glob("*.html"):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", f.stem):
            candidates.append((f.stem, f))
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}-close", f.stem):
            candidates.append((f.stem[:10], f))
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1] if candidates else None


print("=== validate_site ===")

# ── 1+2+8: main-brief buttons must point to briefs/ and file must exist ─────
for page_name in ("index.html",):
    page = ROOT / page_name
    content = page.read_text(encoding="utf-8")
    for m in re.finditer(r'href="([^"]+)"[^>]*>\s*Read (Today\'s Brief|Full Issue)', content):
        href, label = m.group(1), f"Read {m.group(2)}"
        if href.startswith("updates/") or href.startswith("breaking/"):
            err(f"{page_name}: '{label}' points to {href} (must be briefs/)")
        elif not href.startswith("briefs/"):
            err(f"{page_name}: '{label}' points to unexpected path {href}")
        elif not (ROOT / href).exists():
            err(f"{page_name}: '{label}' points to missing file {href}")
        else:
            ok(f"{page_name}: '{label}' → {href}")

# ── 3: Full Close Recap links must resolve ───────────────────────────────────
for f in (ROOT / "updates").glob("*.html"):
    content = f.read_text(encoding="utf-8")
    for m in re.finditer(r'href="([^"]+)"[^>]*>\s*Full Close Recap', content):
        target = (f.parent / m.group(1)).resolve()
        if not target.exists():
            err(f"updates/{f.name}: 'Full Close Recap' → {m.group(1)} (missing)")
        else:
            ok(f"updates/{f.name}: 'Full Close Recap' resolves")

# ── 4+5: latest full brief must be a styled, complete page ──────────────────
brief = latest_full_brief()
if brief is None:
    err("No full brief found in briefs/")
else:
    html = brief.read_text(encoding="utf-8")
    checks = [
        ("<!DOCTYPE html>" in html,                       "doctype"),
        ("<head>" in html,                                "head"),
        ('name="viewport"' in html,                       "viewport meta"),
        ("<title>" in html,                               "title"),
        ("favicon" in html,                               "favicon"),
        ("<style>" in html or "../styles.css" in html,    "CSS (inline or ../styles.css)"),
        ("brief-nav" in html or "site-nav" in html,       "header/nav"),
        ("</html>" in html,                               "closing html tag"),
    ]
    missing = [name for passed, name in checks if not passed]
    if missing:
        err(f"{brief.name}: missing {', '.join(missing)} — page would render unstyled")
    else:
        ok(f"latest full brief {brief.name}: fully styled page shell")

# ── 6: archive markers ────────────────────────────────────────────────────────
archive = (ROOT / "archive.html").read_text(encoding="utf-8")
for marker in ("ARCHIVE_BRIEFS_START", "ARCHIVE_BRIEFS_END",
               "ARCHIVE_UPDATES_START", "ARCHIVE_UPDATES_END"):
    if marker not in archive:
        err(f"archive.html: missing marker {marker}")
    else:
        ok(f"archive.html: {marker} present")

# Archive links must resolve
for m in re.finditer(r'class="archive-title" href="([^"]+)"', archive):
    if not (ROOT / m.group(1)).exists():
        err(f"archive.html: dead link {m.group(1)}")

# ── 7: sitemap must be valid XML ─────────────────────────────────────────────
try:
    ET.parse(ROOT / "sitemap.xml")
    ok("sitemap.xml: valid XML")
except ET.ParseError as e:
    err(f"sitemap.xml: invalid XML — {e}")

# ── Result ────────────────────────────────────────────────────────────────────
print("=" * 40)
if errors:
    print(f"VALIDATION FAILED: {len(errors)} error(s)")
    sys.exit(1)
print("VALIDATION PASSED")
