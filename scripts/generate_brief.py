#!/usr/bin/env python3
"""
generate_brief.py — The Brief daily issue generator.

Calls the Anthropic API with web search enabled, generates a JSON brief,
wraps the article HTML in a full page shell, and updates index.html + archive.html.

Usage:
    python scripts/generate_brief.py

Required environment variable:
    ANTHROPIC_API_KEY

Exits with code 1 (and saves claude_raw_response.txt) if:
    - ANTHROPIC_API_KEY is missing
    - API call fails for any reason
    - Response contains no usable text
    - JSON cannot be parsed
    - Any required field is missing
    - Claude signals data was unavailable (error field in response)
"""

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

# ── Dependency check ───────────────────────────────────────────────────────────
try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
BRIEFS_DIR = ROOT / "briefs"
INDEX_HTML = ROOT / "index.html"
ARCHIVE_HTML = ROOT / "archive.html"
SYSTEM_PROMPT_FILE = ROOT / "prompts" / "system_prompt.txt"
RAW_RESPONSE_FILE = ROOT / "claude_raw_response.txt"
LINKEDIN_DIR = ROOT / "linkedin"

# ── Required JSON fields ───────────────────────────────────────────────────────
REQUIRED_FIELDS = [
    "date_iso",
    "date_display",
    "headline",
    "alert_strip",
    "seo_title",
    "meta_description",
    "archive_teaser",
    "homepage_teaser",
    "linkedin_post",
    "share_text",
    "article_html",
]

# ── Inline CSS for brief pages (self-contained, no external stylesheet) ────────
BRIEF_CSS = """
  :root{--ink:#111010;--paper:#f7f3ec;--paper-2:#ede8df;--rule:#d5cfc4;--red:#b02020;--gold:#8a6710;--gold-bg:#faf4e4;--green:#1a5432;--green-bg:#edf6f1;--muted:#7a7168;--muted-2:#a09585}
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Source Serif 4',Georgia,serif;background:var(--paper);color:var(--ink);font-size:17px;line-height:1.78;-webkit-font-smoothing:antialiased}
  .masthead{padding:36px 0 24px;text-align:center;border-bottom:2.5px solid var(--ink);border-top:4px solid var(--ink)}
  .masthead-eyebrow{font-family:'DM Mono',monospace;font-size:10.5px;letter-spacing:.22em;text-transform:uppercase;color:var(--muted);margin-bottom:12px}
  .masthead-title{font-family:'Playfair Display',Georgia,serif;font-size:clamp(44px,8vw,72px);font-weight:900;letter-spacing:-.025em;line-height:.95;margin-bottom:12px}
  .masthead-rule{display:flex;align-items:center;justify-content:center;gap:14px}
  .masthead-rule::before,.masthead-rule::after{content:'';display:block;height:1px;width:60px;background:var(--rule)}
  .masthead-tagline{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted-2)}
  .alert-strip{background:var(--ink);color:var(--paper);padding:10px 20px;display:flex;align-items:center;justify-content:center;gap:10px;font-family:'DM Mono',monospace;font-size:10.5px;letter-spacing:.14em;text-transform:uppercase}
  .alert-pip{width:6px;height:6px;border-radius:50%;background:#e05050;flex-shrink:0;animation:blink 1.6s ease-in-out infinite}
  @keyframes blink{0%,100%{opacity:1}50%{opacity:.25}}
  .wrap{max-width:680px;margin:0 auto;padding:0 22px 72px}
  .dateline{display:flex;justify-content:space-between;padding:14px 0;border-bottom:1px solid var(--rule);font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
  .ticker{display:grid;grid-template-columns:repeat(5,1fr);border-bottom:1px solid var(--rule)}
  .ticker-cell{padding:12px 10px;border-right:1px solid var(--rule);text-align:center}
  .ticker-cell:last-child{border-right:none}
  .t-label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin-bottom:4px}
  .t-val{font-family:'DM Mono',monospace;font-size:13px;font-weight:500;color:var(--ink);margin-bottom:2px}
  .t-chg{font-family:'DM Mono',monospace;font-size:10px;font-weight:500}
  .t-note{font-family:'DM Mono',monospace;font-size:7.5px;color:var(--muted-2);margin-top:2px}
  .down{color:var(--red)}.up{color:var(--green)}
  .toc{border:1px solid var(--rule);border-top:2px solid var(--ink);padding:16px 20px;margin-top:16px}
  .toc-label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.2em;text-transform:uppercase;color:var(--muted);margin-bottom:10px}
  .toc-list{list-style:none;padding:0;margin:0;columns:2;column-gap:24px}
  @media(max-width:480px){.toc-list{columns:1}}
  .toc-list li{padding:3px 0;break-inside:avoid}
  .toc-list a{font-family:'DM Mono',monospace;font-size:10.5px;letter-spacing:.04em;color:var(--ink);text-decoration:none;display:flex;align-items:baseline;gap:7px}
  .toc-list a:hover .toc-title{color:var(--red);border-color:var(--red)}
  .toc-num{color:var(--red);font-size:9px;flex-shrink:0;letter-spacing:.08em}
  .toc-title{border-bottom:1px solid var(--rule);padding-bottom:1px}
  .smart30{background:var(--ink);color:var(--paper);padding:20px 26px}
  .smart30-label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.2em;text-transform:uppercase;color:#888;margin-bottom:10px}
  .smart30 p{font-size:15.5px;line-height:1.75;color:#ede8df;margin-bottom:0}
  .section{margin-top:40px;padding-top:20px;border-top:1px solid var(--rule)}
  .section.first{border-top:2px solid var(--ink);margin-top:32px}
  .section-label{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.22em;text-transform:uppercase;color:var(--muted);margin-bottom:7px}
  .section-num{color:var(--red)}
  h2{font-family:'Playfair Display',Georgia,serif;font-size:clamp(19px,3.2vw,24px);font-weight:700;line-height:1.22;letter-spacing:-.01em;color:var(--ink);margin-bottom:18px}
  .dev-item{padding:0 0 18px 18px;border-left:2px solid var(--ink);margin-bottom:18px}
  .dev-item:last-child{margin-bottom:0;padding-bottom:0}
  .dev-category{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin-bottom:5px}
  .dev-item p{font-size:15px;line-height:1.70}
  p{font-size:16px;line-height:1.80;margin-bottom:14px;color:var(--ink)}
  p:last-child{margin-bottom:0}
  em{font-style:italic}strong{font-weight:600}
  .aside{border-left:2px solid var(--rule);padding:3px 0 3px 16px;margin:18px 0;color:var(--muted);font-size:14px;line-height:1.70;font-style:italic}
  .chain{background:var(--paper-2);border-top:2px solid var(--ink);border-bottom:1px solid var(--rule);padding:20px 24px;margin:18px 0}
  .chain-row{display:grid;grid-template-columns:68px 1fr;gap:14px;padding:10px 0;border-bottom:1px solid var(--rule);align-items:start}
  .chain-row:first-child{padding-top:0}.chain-row:last-child{padding-bottom:0;border-bottom:none}
  .chain-label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);padding-top:2px;line-height:1.5}
  .chain-text{font-family:'DM Mono',monospace;font-size:11.5px;line-height:1.85;color:var(--ink)}
  .arr{color:var(--red);margin:0 3px}.arr-g{color:var(--green);margin:0 3px}
  .grid-2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:4px}
  @media(max-width:540px){.grid-2{grid-template-columns:1fr}}
  .grid-card{border:1px solid var(--rule);border-top:2.5px solid var(--ink);padding:16px 16px 18px;background:var(--paper)}
  .card-label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin-bottom:8px}
  .grid-card p{font-size:13px;line-height:1.66;margin-bottom:0}
  .watch{background:var(--gold-bg);border:1px solid #dfc98a;border-left:2.5px solid var(--gold);padding:15px 18px;margin-top:12px}
  .watch-label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--gold);margin-bottom:7px}
  .watch p{font-size:13px;line-height:1.66;margin-bottom:0;color:#5a3f00}
  .sector-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:4px}
  @media(max-width:520px){.sector-grid{grid-template-columns:1fr}}
  .sector-card{border:1px solid var(--rule);padding:13px 15px;background:var(--paper)}
  .sector-card.winning{border-top:2.5px solid var(--green)}.sector-card.losing{border-top:2.5px solid var(--red)}.sector-card.mixed{border-top:2.5px solid var(--gold)}
  .sector-name{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin-bottom:5px;display:flex;align-items:center;gap:5px;flex-wrap:wrap}
  .sector-badge{font-size:8px;padding:1px 5px;border-radius:2px;font-weight:500}
  .badge-win{background:var(--green-bg);color:var(--green)}.badge-lose{background:#fdf2f2;color:var(--red)}.badge-watch{background:var(--gold-bg);color:var(--gold)}
  .sector-card p{font-size:12.5px;line-height:1.63;margin-bottom:0}
  .career-universal{background:var(--paper-2);border-top:2px solid var(--ink);border-bottom:1px solid var(--rule);padding:14px 18px;margin-bottom:14px}
  .career-universal-label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
  .career-universal p{font-size:13.5px;line-height:1.68;margin-bottom:0;font-style:italic;color:var(--ink)}
  .career-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .career-grid .career-card:last-child:nth-child(odd){grid-column:1 / -1}
  @media(max-width:520px){.career-grid{grid-template-columns:1fr}}
  .career-card{border:1px solid var(--rule);padding:13px 15px 15px;background:var(--paper)}
  .career-path{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin-bottom:5px}
  .career-card p{font-size:12.5px;line-height:1.63;margin-bottom:0}
  .interview-box{border:1px solid var(--rule);border-left:2.5px solid var(--ink);padding:16px 20px;margin-top:6px}
  .interview-box ul{list-style:none;padding:0;margin:0}
  .interview-box li{font-size:14px;line-height:1.68;padding:7px 0 7px 16px;border-bottom:1px solid var(--rule);position:relative}
  .interview-box li::before{content:'→';position:absolute;left:0;color:var(--red);font-family:'DM Mono',monospace;font-size:10px;top:10px}
  .interview-box li:last-child{border-bottom:none}
  .term{border:1px solid var(--rule);padding:20px 24px 22px;margin-top:6px}
  .term-word{font-family:'Playfair Display',Georgia,serif;font-size:20px;font-weight:700;font-style:italic;color:var(--red);margin-bottom:9px}
  .term p{font-size:14.5px;margin-bottom:0}
  .say{background:var(--green-bg);border:1px solid #b2d9c3;border-left:2.5px solid var(--green);padding:18px 22px 20px;margin-top:6px}
  .say-context{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:var(--green);display:block;margin-bottom:6px}
  .say p{font-size:14.5px;line-height:1.76;color:#0e3324;font-style:italic;margin-bottom:0}
  .sources{margin-top:36px;padding-top:14px;border-top:1px solid var(--rule);font-family:'DM Mono',monospace;font-size:9.5px;color:var(--muted);line-height:1.8}
  .sources strong{font-weight:500;text-transform:uppercase;letter-spacing:.1em;font-size:8.5px}
  .footer{margin-top:24px;padding-top:16px;border-top:2px solid var(--ink);text-align:center;font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);line-height:1.9}
"""


def load_system_prompt() -> str:
    if not SYSTEM_PROMPT_FILE.exists():
        print(f"ERROR: System prompt not found at {SYSTEM_PROMPT_FILE}")
        sys.exit(1)
    return SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")


def call_api(system_prompt: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    today = date.today().strftime("%A, %B %-d, %Y")

    user_message = (
        f"Today is {today}. "
        "Use your web_search tool first to retrieve today's real market data and news. "
        "Search for: S&P 500 close, Nasdaq close, VIX, 10-year Treasury yield, WTI crude, "
        "Brent crude, top movers, major earnings, Fed news, and the 2-3 biggest market stories today. "
        "Then produce a complete issue of The Brief following the system prompt exactly. "
        "Return ONLY the JSON object. No markdown fences. No text before or after the JSON."
    )

    print(f"Calling Anthropic API (claude-sonnet-4-6) for {today}...")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=16000,
            system=system_prompt,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 12}],
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIConnectionError as e:
        print(f"ERROR: Could not connect to Anthropic API: {e}")
        sys.exit(1)
    except anthropic.AuthenticationError:
        print("ERROR: Invalid ANTHROPIC_API_KEY. Check your GitHub secret.")
        sys.exit(1)
    except anthropic.RateLimitError:
        print("ERROR: Anthropic API rate limit hit. Try again later.")
        sys.exit(1)
    except anthropic.APIStatusError as e:
        print(f"ERROR: Anthropic API error {e.status_code}: {e.message}")
        sys.exit(1)

    # Collect all text blocks (model may produce multiple after tool use)
    text_parts = [block.text for block in response.content if block.type == "text"]
    text_content = "\n".join(text_parts).strip()

    if not text_content:
        print("ERROR: API returned no text content.")
        print(f"Stop reason: {response.stop_reason}")
        print(f"Content block types: {[b.type for b in response.content]}")
        sys.exit(1)

    print(f"Received {len(text_content)} chars from API.")
    return text_content


def save_raw_response(raw: str) -> None:
    RAW_RESPONSE_FILE.write_text(raw, encoding="utf-8")
    print(f"Raw Claude response saved to: {RAW_RESPONSE_FILE}")


def extract_json(raw: str) -> dict:
    """
    Robustly extract the first valid JSON object from a Claude response.
    Handles:
    - Plain JSON
    - JSON wrapped in ```json ... ``` fences
    - JSON with preamble/postamble text
    - Multiple text blocks concatenated
    """
    original = raw

    # Strategy 1: try the whole string as-is (ideal case)
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip a single code fence wrapping the whole response
    stripped = raw.strip()
    stripped = re.sub(r"^```(?:json)?\s*\n?", "", stripped)
    stripped = re.sub(r"\n?```\s*$", "", stripped)
    try:
        return json.loads(stripped.strip())
    except json.JSONDecodeError:
        pass

    # Strategy 3: find the first { ... } JSON object in the text
    # Handles cases where Claude added preamble like "Here is the JSON:"
    match = re.search(r"\{", raw)
    if match:
        start = match.start()
        # Walk forward to find the matching closing brace
        depth = 0
        in_string = False
        escape_next = False
        for i, ch in enumerate(raw[start:], start):
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
            if not in_string:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = raw[start : i + 1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break

    # All strategies failed — save raw response and exit
    save_raw_response(original)
    print("ERROR: Could not parse JSON from Claude response.")
    print("       The raw response has been saved to claude_raw_response.txt")
    print("       First 500 chars of response:")
    print(original[:500])
    sys.exit(1)


def validate(data: dict) -> None:
    # Check if Claude reported a data failure
    if "error" in data:
        print(f"ERROR: Claude reported a failure: {data['error']}")
        sys.exit(1)

    # Check all required fields
    def field_missing(f: str) -> bool:
        val = data.get(f)
        if val is None:
            return True
        if isinstance(val, str) and not val.strip():
            return True
        return False

    missing = [f for f in REQUIRED_FIELDS if field_missing(f)]
    if missing:
        print(f"ERROR: Response is missing required fields: {missing}")
        print("       Fields present:", list(data.keys()))
        sys.exit(1)

    # Sanity check: article_html must have actual content
    article_html = data.get("article_html", "")
    if len(article_html) < 500:
        print(f"ERROR: article_html is suspiciously short ({len(article_html)} chars). Content was not generated.")
        sys.exit(1)

    # Sanity check: article_html must not contain placeholder text
    placeholders = ["X,XXX", "XX,XXX", "$XX.XX", "YOUR_DATA_HERE", "PLACEHOLDER"]
    found = [p for p in placeholders if p in article_html]
    if found:
        print(f"ERROR: article_html contains placeholder text: {found}. Real data was not retrieved.")
        sys.exit(1)

    # Fix date_iso if model got it wrong
    today_iso = date.today().isoformat()
    if data.get("date_iso") != today_iso:
        print(f"WARNING: date_iso '{data.get('date_iso')}' does not match today '{today_iso}'. Overriding.")
        data["date_iso"] = today_iso


def build_page(data: dict) -> str:
    date_iso = data["date_iso"]
    seo_title = data["seo_title"]
    meta_desc = data["meta_description"]
    alert_strip = data["alert_strip"]
    article_html = data["article_html"]
    share_text = data["share_text"].replace("{{URL}}", f"https://thebrieffinance.com/briefs/{date_iso}.html")
    share_text_encoded = re.sub(r"\s+", "+", share_text.strip())
    site_url = f"https://thebrieffinance.com/briefs/{date_iso}.html"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{seo_title}</title>
<meta name="description" content="{meta_desc}">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=DM+Mono:wght@300;400;500&family=Source+Serif+4:ital,opsz,wght@0,8..60,300;0,8..60,400;0,8..60,600;1,8..60,300;1,8..60,400&display=swap" rel="stylesheet">
<style>{BRIEF_CSS}</style>
</head>
<body>

<div style="background:#111010;padding:10px 0;text-align:center">
  <a href="../index.html" style="font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#f7f3ec;text-decoration:none;opacity:.7">← The Brief Home</a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="../archive.html" style="font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#f7f3ec;text-decoration:none;opacity:.7">Archive</a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="../subscribe.html" style="font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#f7f3ec;text-decoration:none;opacity:.7">Subscribe</a>
</div>

<div class="masthead">
  <div class="masthead-eyebrow">Daily Market Intelligence</div>
  <div class="masthead-title">The Brief</div>
  <div class="masthead-rule"><span class="masthead-tagline">Finance students &amp; early-career professionals</span></div>
</div>

<div class="alert-strip">
  <div class="alert-pip"></div>
  {alert_strip}
</div>

<div class="wrap">
{article_html}

  <div style="margin-top:32px;border-top:2px solid #111010;padding-top:28px;display:flex;flex-direction:column;gap:12px">
    <div style="display:flex;gap:12px;flex-wrap:wrap">
      <a href="../subscribe.html" style="flex:1;min-width:160px;display:block;background:#111010;color:#f7f3ec;text-align:center;padding:14px 20px;font-family:'DM Mono',monospace;font-size:10.5px;letter-spacing:.18em;text-transform:uppercase;text-decoration:none">Subscribe — It's Free</a>
      <a href="../archive.html" style="flex:1;min-width:160px;display:block;border:1px solid #111010;color:#111010;text-align:center;padding:14px 20px;font-family:'DM Mono',monospace;font-size:10.5px;letter-spacing:.18em;text-transform:uppercase;text-decoration:none">Browse All Issues</a>
    </div>
    <div style="text-align:center;font-family:'DM Mono',monospace;font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:#7a7168">
      Share on
      <a href="https://www.linkedin.com/sharing/share-offsite/?url={site_url}" target="_blank" rel="noopener" style="color:#111010;margin-left:6px">LinkedIn</a>
      &nbsp;·&nbsp;
      <a href="https://twitter.com/intent/tweet?text={share_text_encoded}" target="_blank" rel="noopener" style="color:#111010">X / Twitter</a>
    </div>
  </div>
</div>

</body>
</html>"""


def save_linkedin(data: dict, date_iso: str) -> None:
    LINKEDIN_DIR.mkdir(exist_ok=True)
    site_url = f"https://thebrieffinance.com/briefs/{date_iso}.html"
    copy = data["linkedin_post"].replace("{{URL}}", site_url)
    out = LINKEDIN_DIR / f"{date_iso}.txt"
    out.write_text(copy, encoding="utf-8")
    print(f"LinkedIn copy saved: {out}")


def update_index(data: dict, date_iso: str) -> None:
    content = INDEX_HTML.read_text(encoding="utf-8")
    teaser = data["homepage_teaser"]
    headline = data["headline"]
    date_display = data["date_display"]

    new_block = (
        "  <!-- LATEST_BRIEF_START -->\n"
        "  <div class=\"section\">\n"
        "    <div class=\"section-label\">Latest Issue</div>\n"
        "    <div class=\"latest-card\">\n"
        "      <div class=\"latest-label\">Most Recent Brief</div>\n"
        f"      <div class=\"latest-date\">{date_display}</div>\n"
        f"      <div class=\"latest-title\">{headline}</div>\n"
        f"      <p class=\"latest-teaser\">{teaser}</p>\n"
        f"      <a href=\"briefs/{date_iso}.html\" class=\"btn btn-dark\">Read Full Issue &rarr;</a>\n"
        "    </div>\n"
        "  </div>\n"
        "  <!-- LATEST_BRIEF_END -->"
    )

    # Use a lambda to avoid re.sub interpreting backslashes in the replacement
    updated = re.sub(
        r"<!-- LATEST_BRIEF_START -->.*?<!-- LATEST_BRIEF_END -->",
        lambda _: new_block,
        content,
        flags=re.DOTALL,
    )

    if updated == content:
        print("WARNING: LATEST_BRIEF_START/END markers not found in index.html. Homepage not updated.")
    else:
        INDEX_HTML.write_text(updated, encoding="utf-8")
        print("index.html updated.")


def update_archive(data: dict, date_iso: str) -> None:
    content = ARCHIVE_HTML.read_text(encoding="utf-8")
    parts = date_iso.split("-")
    month_abbr = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(parts[1])]
    day = int(parts[2])
    year = parts[0]
    teaser = data["archive_teaser"]
    headline = data["headline"]

    new_item = (
        f"\n    <li class=\"archive-item\">\n"
        f"      <div class=\"archive-date\">{month_abbr} {day}<br>{year}</div>\n"
        f"      <div>\n"
        f"        <a class=\"archive-title\" href=\"briefs/{date_iso}.html\">{headline}</a>\n"
        f"        <p class=\"archive-teaser\">{teaser}</p>\n"
        f"      </div>\n"
        f"    </li>\n"
    )

    # Use a lambda to safely inject the new item without backslash interpretation
    updated = re.sub(
        r"(<!-- ARCHIVE_LIST_START -->\s*<ul[^>]*>)",
        lambda m: m.group(0) + new_item,
        content,
        flags=re.DOTALL,
    )

    if updated == content:
        print("WARNING: ARCHIVE_LIST_START marker not found in archive.html. Archive not updated.")
    else:
        ARCHIVE_HTML.write_text(updated, encoding="utf-8")
        print("archive.html updated.")


def main() -> None:
    print("=== The Brief — Daily Generator ===")

    if not SYSTEM_PROMPT_FILE.exists():
        print(f"ERROR: System prompt not found at {SYSTEM_PROMPT_FILE}")
        sys.exit(1)

    system_prompt = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    raw = call_api(system_prompt)
    data = extract_json(raw)
    validate(data)

    date_iso = data["date_iso"]
    out_path = BRIEFS_DIR / f"{date_iso}.html"

    if out_path.exists():
        print(f"WARNING: {out_path} already exists. Overwriting.")

    html = build_page(data)
    out_path.write_text(html, encoding="utf-8")
    print(f"Brief written: {out_path}")

    save_linkedin(data, date_iso)
    update_index(data, date_iso)
    update_archive(data, date_iso)

    print("=== Done. ===")


if __name__ == "__main__":
    main()
