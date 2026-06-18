#!/usr/bin/env python3
"""
generate_brief.py — The Brief daily issue generator.

Calls the Anthropic API with web search enabled, generates a structured JSON brief,
wraps it in a full HTML page, and updates index.html + archive.html.

Required env var: ANTHROPIC_API_KEY

Exits with code 1 (saves claude_raw_response.txt) on any failure.
Never writes files if generation or validation fails.
"""

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT               = Path(__file__).parent.parent
BRIEFS_DIR         = ROOT / "briefs"
INDEX_HTML         = ROOT / "index.html"
ARCHIVE_HTML       = ROOT / "archive.html"
SYSTEM_PROMPT_FILE = ROOT / "prompts" / "system_prompt.txt"
RAW_RESPONSE_FILE  = ROOT / "claude_raw_response.txt"
LINKEDIN_DIR       = ROOT / "linkedin"

# ── Required JSON fields ───────────────────────────────────────────────────────
REQUIRED_FIELDS = [
    "date_iso",
    "date_display",
    "headline",
    "alert_strip",
    "seo_title",
    "meta_description",
    "issue_kicker",
    "opening_summary",
    "feature_image_url",      # empty string "" if no safe image available
    "feature_image_alt",
    "feature_image_caption",
    "feature_image_credit",
    "feature_image_source_url",
    "feature_image_type",     # "wikimedia" | "press" | "unsplash" | "pexels" | "none"
    "market_snapshot",
    "archive_teaser",
    "homepage_teaser",
    "linkedin_post",
    "share_text",
    "article_html",
]

# ── Safe image source types ────────────────────────────────────────────────────
SAFE_IMAGE_TYPES = {"wikimedia", "press", "unsplash", "pexels", "none"}

# ── Domains that must never supply images ──────────────────────────────────────
# Copyrighted news/photo agencies and stock libraries that do not grant reuse rights.
BLOCKED_IMAGE_DOMAINS = [
    # Stock / rights-managed photo agencies
    "gettyimages.com", "shutterstock.com", "alamy.com",
    "istockphoto.com", "dreamstime.com", "123rf.com", "depositphotos.com",
    # News wire / agency photo services
    "apimages.com", "ap.org",
    "reuters.com",          # also catches reuters.com/resizer
    "afp.com", "afpforum.com",
    # Financial & business news with proprietary photo desks
    "bloomberg.com", "bloomberg.net",
    "wsj.com", "dowjones.com",
    "ft.com",
    "cnbc.com",
    "nytimes.com", "nyti.ms",
    "nbcnews.com",
    "bbc.co.uk", "bbc.com",
    "marketwatch.com",
    "businessinsider.com",
    "seekingalpha.com",
    "theatlantic.com",
    "washingtonpost.com",
    "economist.com",
]

# ── Full inline CSS for brief pages ───────────────────────────────────────────
BRIEF_CSS = """
  :root{--ink:#111010;--paper:#f7f3ec;--paper-2:#ede8df;--rule:#d5cfc4;--red:#b02020;--gold:#8a6710;--gold-bg:#faf4e4;--green:#1a5432;--green-bg:#edf6f1;--muted:#7a7168;--muted-2:#a09585}
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Source Serif 4',Georgia,serif;background:var(--paper);color:var(--ink);font-size:17px;line-height:1.78;-webkit-font-smoothing:antialiased}
  .site-nav-bar{background:#111010;padding:10px 0;text-align:center;border-bottom:1px solid #222}
  .site-nav-bar a{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:#f7f3ec;text-decoration:none;opacity:.65;transition:opacity .15s}
  .site-nav-bar a:hover{opacity:1}
  .site-nav-bar .nav-sep{color:#444;margin:0 10px}
  .masthead{padding:32px 0 22px;text-align:center;border-bottom:2.5px solid var(--ink);border-top:4px solid var(--ink)}
  .masthead-eyebrow{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.24em;text-transform:uppercase;color:var(--muted);margin-bottom:10px}
  .masthead-title{font-family:'Playfair Display',Georgia,serif;font-size:clamp(40px,7vw,62px);font-weight:900;letter-spacing:-.025em;line-height:.95;margin-bottom:12px}
  .masthead-rule{display:flex;align-items:center;justify-content:center;gap:14px}
  .masthead-rule::before,.masthead-rule::after{content:'';display:block;height:1px;width:52px;background:var(--rule)}
  .masthead-tagline{font-family:'DM Mono',monospace;font-size:9.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted-2)}
  .alert-strip{background:var(--ink);color:var(--paper);padding:9px 20px;display:flex;align-items:center;justify-content:center;gap:10px;font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.13em;text-transform:uppercase;flex-wrap:wrap}
  .alert-pip{width:5px;height:5px;border-radius:50%;background:#e05050;flex-shrink:0;animation:blink 1.6s ease-in-out infinite}
  @keyframes blink{0%,100%{opacity:1}50%{opacity:.25}}
  .wrap{max-width:680px;margin:0 auto;padding:0 22px 72px}
  .issue-kicker{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.22em;text-transform:uppercase;color:var(--red);padding:22px 0 8px}
  .issue-headline{font-family:'Playfair Display',Georgia,serif;font-size:clamp(26px,5vw,40px);font-weight:900;line-height:1.08;letter-spacing:-.02em;color:var(--ink);margin-bottom:16px}
  .opening-summary{font-size:16px;line-height:1.82;color:#2e2b27;margin-bottom:22px;border-left:3px solid var(--ink);padding-left:16px}
  .feature-img-wrap{margin-bottom:4px;overflow:hidden;background:#e8e3db}
  .feature-img{width:100%;height:360px;object-fit:cover;display:block}
  @media(max-width:560px){.feature-img{height:220px}}
  .feature-caption-bar{padding:8px 12px 10px;background:var(--paper-2);border:1px solid var(--rule);border-top:none;margin-bottom:18px;display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:4px}
  .feature-caption-text{font-family:'DM Mono',monospace;font-size:9.5px;color:var(--muted);line-height:1.5}
  .feature-credit{font-family:'DM Mono',monospace;font-size:8.5px;color:var(--muted-2);white-space:nowrap}
  .feature-fallback{height:4px;background:var(--ink);margin-bottom:22px}
  .market-snapshot{border:1px solid var(--rule);border-top:2px solid var(--ink);background:var(--paper-2);margin-bottom:8px}
  .market-snapshot-header{display:flex;justify-content:space-between;align-items:center;padding:10px 16px 0}
  .market-snapshot-label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.2em;text-transform:uppercase;color:var(--muted)}
  .market-snapshot-time{font-family:'DM Mono',monospace;font-size:8.5px;color:var(--muted-2)}
  .market-snapshot-grid{display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid var(--rule);margin-top:8px}
  @media(max-width:420px){.market-snapshot-grid{grid-template-columns:repeat(2,1fr)}}
  .snapshot-cell{padding:11px 14px;border-right:1px solid var(--rule);border-bottom:1px solid var(--rule)}
  .snapshot-cell:nth-child(3n){border-right:none}
  .snapshot-cell:nth-last-child(-n+3){border-bottom:none}
  @media(max-width:420px){.snapshot-cell:nth-child(3n){border-right:1px solid var(--rule)}.snapshot-cell:nth-child(2n){border-right:none}.snapshot-cell:nth-last-child(-n+3){border-bottom:1px solid var(--rule)}.snapshot-cell:nth-last-child(-n+2){border-bottom:none}}
  .snapshot-label{font-family:'DM Mono',monospace;font-size:8.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin-bottom:4px}
  .snapshot-value{font-family:'DM Mono',monospace;font-size:16px;font-weight:500;color:var(--ink);margin-bottom:2px;line-height:1}
  .snapshot-change{font-family:'DM Mono',monospace;font-size:11px;font-weight:500}
  .snapshot-change.up{color:var(--green)}.snapshot-change.down{color:var(--red)}.snapshot-change.flat{color:var(--muted)}
  .snapshot-note{font-family:'DM Mono',monospace;font-size:7.5px;color:var(--muted-2);margin-top:3px}
  .toc{border:1px solid var(--rule);border-top:2px solid var(--ink);padding:16px 20px;margin-bottom:8px}
  .toc-label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.2em;text-transform:uppercase;color:var(--muted);margin-bottom:10px}
  .toc-list{list-style:none;padding:0;margin:0;columns:2;column-gap:24px}
  @media(max-width:480px){.toc-list{columns:1}}
  .toc-list li{padding:3px 0;break-inside:avoid}
  .toc-list a{font-family:'DM Mono',monospace;font-size:10.5px;letter-spacing:.04em;color:var(--ink);text-decoration:none;display:flex;align-items:baseline;gap:7px}
  .toc-list a:hover .toc-title{color:var(--red);border-color:var(--red)}
  .toc-num{color:var(--red);font-size:9px;flex-shrink:0;letter-spacing:.08em}
  .toc-title{border-bottom:1px solid var(--rule);padding-bottom:1px}
  .smart30{background:var(--ink);color:var(--paper);padding:20px 26px;margin-top:32px}
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


def render_feature_image(data: dict) -> str:
    """Return HTML for the editorial feature image, or a minimal fallback rule."""
    url        = data.get("feature_image_url", "").strip()
    alt        = data.get("feature_image_alt", "")
    caption    = data.get("feature_image_caption", "").strip()
    credit     = data.get("feature_image_credit", "").strip()
    source_url = data.get("feature_image_source_url", "").strip()
    img_type   = data.get("feature_image_type", "none")

    if not url or img_type == "none":
        # Minimal 4px ink rule — not the main visual, just a clean separator
        return '<div class="feature-fallback"></div>\n'

    credit_html = ""
    if credit:
        if source_url:
            credit_html = f'<a href="{source_url}" target="_blank" rel="noopener" class="feature-credit">{credit}</a>'
        else:
            credit_html = f'<span class="feature-credit">{credit}</span>'

    caption_bar = ""
    if caption or credit_html:
        caption_bar = (
            f'<div class="feature-caption-bar">'
            f'<span class="feature-caption-text">{caption}</span>'
            f'{credit_html}'
            f'</div>\n'
        )

    return (
        f'<div class="feature-img-wrap">\n'
        f'  <img src="{url}" alt="{alt}" class="feature-img" loading="lazy"'
        f' onerror="this.closest(\'.feature-img-wrap\').style.display=\'none\'">\n'
        f'</div>\n'
        f'{caption_bar}'
    )


def render_market_snapshot(snapshot: list) -> str:
    """Render a structured market_snapshot list into HTML."""
    cells = ""
    for item in snapshot:
        direction = item.get("direction", "flat")
        arrow = "▲" if direction == "up" else ("▼" if direction == "down" else "—")
        note = item.get("note", "")
        note_html = f'<div class="snapshot-note">{note}</div>' if note else ""
        cells += (
            f'<div class="snapshot-cell">'
            f'<div class="snapshot-label">{item["label"]}</div>'
            f'<div class="snapshot-value">{item["value"]}</div>'
            f'<div class="snapshot-change {direction}">{arrow} {item["change"]}</div>'
            f'{note_html}'
            f'</div>\n'
        )
    return (
        '<div class="market-snapshot">\n'
        '  <div class="market-snapshot-header">'
        '<span class="market-snapshot-label">Market Snapshot</span>'
        '<span class="market-snapshot-time">At Close</span>'
        '</div>\n'
        f'  <div class="market-snapshot-grid">\n{cells}  </div>\n'
        '</div>\n'
    )


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
        "Search for: S&P 500 close, Nasdaq close, Dow close, VIX, 10-year Treasury yield, "
        "WTI crude, Brent crude, top movers, major earnings, Fed news, and the 2-3 biggest "
        "market stories today. Also search for a suitable editorial image from Wikimedia Commons, "
        "official press/government sources, Unsplash, or Pexels that matches today's main story. "
        "Then produce a complete issue of The Brief. "
        "Return ONLY the JSON object. No markdown fences. No text before or after the JSON."
    )

    print(f"Calling Anthropic API (claude-sonnet-4-6) for {today}...")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=16000,
            system=system_prompt,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 15}],
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIConnectionError as e:
        print(f"ERROR: Could not connect to Anthropic API: {e}")
        sys.exit(1)
    except anthropic.AuthenticationError:
        print("ERROR: Invalid ANTHROPIC_API_KEY.")
        sys.exit(1)
    except anthropic.RateLimitError:
        print("ERROR: Anthropic API rate limit hit.")
        sys.exit(1)
    except anthropic.APIStatusError as e:
        print(f"ERROR: Anthropic API error {e.status_code}: {e.message}")
        sys.exit(1)

    text_parts = [block.text for block in response.content if block.type == "text"]
    text_content = "\n".join(text_parts).strip()

    if not text_content:
        print("ERROR: API returned no text content.")
        print(f"Stop reason: {response.stop_reason}")
        sys.exit(1)

    print(f"Received {len(text_content)} chars from API.")
    return text_content


def save_raw_response(raw: str) -> None:
    RAW_RESPONSE_FILE.write_text(raw, encoding="utf-8")
    print(f"Raw Claude response saved to: {RAW_RESPONSE_FILE}")


def extract_json(raw: str) -> dict:
    """Robustly extract the first valid JSON object from a Claude response."""
    original = raw

    # Strategy 1: whole string is valid JSON
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip a single markdown code fence
    stripped = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
    stripped = re.sub(r"\n?```\s*$", "", stripped)
    try:
        return json.loads(stripped.strip())
    except json.JSONDecodeError:
        pass

    # Strategy 3: find first { and walk to matching }
    match = re.search(r"\{", raw)
    if match:
        start = match.start()
        depth, in_string, escape_next = 0, False, False
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
                        try:
                            return json.loads(raw[start : i + 1])
                        except json.JSONDecodeError:
                            break

    save_raw_response(original)
    print("ERROR: Could not parse JSON from Claude response.")
    print("       Raw response saved to claude_raw_response.txt")
    print("       First 500 chars:", original[:500])
    sys.exit(1)


def validate(data: dict) -> None:
    if "error" in data:
        print(f"ERROR: Claude reported a failure: {data['error']}")
        sys.exit(1)

    # All image fields are optional when no safe image is available
    IMAGE_OPTIONAL_FIELDS = {
        "feature_image_url", "feature_image_alt", "feature_image_caption",
        "feature_image_credit", "feature_image_source_url",
    }

    def field_missing(f: str) -> bool:
        val = data.get(f)
        if val is None:
            return True
        if f in IMAGE_OPTIONAL_FIELDS:
            return False   # empty string is fine — means no image
        if isinstance(val, str) and not val.strip():
            return True
        return False

    missing = [f for f in REQUIRED_FIELDS if field_missing(f)]
    if missing:
        print(f"ERROR: Response is missing required fields: {missing}")
        print("       Fields present:", list(data.keys()))
        sys.exit(1)

    # ── Image safety checks ────────────────────────────────────────────────────
    def _clear_image(reason: str) -> None:
        print(f"WARNING: {reason}. Falling back to no image.")
        data["feature_image_url"]        = ""
        data["feature_image_alt"]        = ""
        data["feature_image_caption"]    = ""
        data["feature_image_credit"]     = ""
        data["feature_image_source_url"] = ""
        data["feature_image_type"]       = "none"

    img_type   = data.get("feature_image_type", "")
    url        = data.get("feature_image_url", "").strip()
    credit     = data.get("feature_image_credit", "").strip()
    source_url = data.get("feature_image_source_url", "").strip()

    # 1. Type must be a known safe value
    if img_type not in SAFE_IMAGE_TYPES:
        _clear_image(f"Unknown feature_image_type '{img_type}'")

    # Re-read after possible clear
    url        = data.get("feature_image_url", "").strip()
    img_type   = data.get("feature_image_type", "none")
    credit     = data.get("feature_image_credit", "").strip()
    source_url = data.get("feature_image_source_url", "").strip()

    if url:
        # 2. Blocked domain check
        for domain in BLOCKED_IMAGE_DOMAINS:
            if domain in url:
                _clear_image(f"Image URL from blocked domain '{domain}'")
                break

    url    = data.get("feature_image_url", "").strip()
    credit = data.get("feature_image_credit", "").strip()
    source_url = data.get("feature_image_source_url", "").strip()

    if url:
        # 3. Credit is required whenever a URL is provided
        if not credit:
            _clear_image("feature_image_url set but feature_image_credit is missing")

        # 4. Source URL is required whenever a URL is provided
        elif not source_url:
            _clear_image("feature_image_url set but feature_image_source_url is missing")

    # market_snapshot must be a list with real data
    snapshot = data.get("market_snapshot", [])
    if not isinstance(snapshot, list) or len(snapshot) < 4:
        print(f"ERROR: market_snapshot must be a list of at least 4 items "
              f"(got {type(snapshot).__name__}, len={len(snapshot) if isinstance(snapshot, list) else 'n/a'})")
        sys.exit(1)
    placeholders = {"X,XXX", "XX,XXX", "X.XX", "$XX.XX", "X.X%", ""}
    for item in snapshot:
        if item.get("value", "") in placeholders:
            print(f"ERROR: Placeholder value in market_snapshot for "
                  f"'{item.get('label')}': '{item.get('value')}'")
            sys.exit(1)

    # article_html must have real content
    article_html = data.get("article_html", "")
    if len(article_html) < 500:
        print(f"ERROR: article_html is suspiciously short ({len(article_html)} chars).")
        sys.exit(1)

    # date override if wrong
    today_iso = date.today().isoformat()
    if data.get("date_iso") != today_iso:
        print(f"WARNING: date_iso '{data.get('date_iso')}' overridden to '{today_iso}'.")
        data["date_iso"] = today_iso


def build_page(data: dict) -> str:
    date_iso    = data["date_iso"]
    seo_title   = data["seo_title"]
    meta_desc   = data["meta_description"]
    alert_strip = data["alert_strip"]
    kicker      = data["issue_kicker"]
    headline    = data["headline"]
    opening     = data["opening_summary"]
    article_html = data["article_html"]
    snapshot    = data["market_snapshot"]

    site_url = f"https://thebrieffinance.com/briefs/{date_iso}.html"
    share_raw = data["share_text"].replace("{{URL}}", site_url)
    share_encoded = re.sub(r"\s+", "+", share_raw.strip())

    feature_html     = render_feature_image(data)
    market_snap_html = render_market_snapshot(snapshot)

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

<div class="site-nav-bar">
  <a href="../index.html">&#8592; The Brief</a>
  <span class="nav-sep">·</span>
  <a href="../archive.html">Archive</a>
  <span class="nav-sep">·</span>
  <a href="../subscribe.html">Subscribe</a>
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
  <div class="issue-kicker">{kicker}</div>
  <h1 class="issue-headline">{headline}</h1>
  <p class="opening-summary">{opening}</p>

{feature_html}
{market_snap_html}

{article_html}

  <div style="margin-top:40px;border-top:2px solid #111010;padding-top:28px;display:flex;flex-direction:column;gap:12px">
    <div style="display:flex;gap:12px;flex-wrap:wrap">
      <a href="../subscribe.html" style="flex:1;min-width:160px;display:block;background:#111010;color:#f7f3ec;text-align:center;padding:14px 20px;font-family:'DM Mono',monospace;font-size:10.5px;letter-spacing:.18em;text-transform:uppercase;text-decoration:none">Subscribe — It's Free</a>
      <a href="../archive.html" style="flex:1;min-width:160px;display:block;border:1.5px solid #111010;color:#111010;text-align:center;padding:14px 20px;font-family:'DM Mono',monospace;font-size:10.5px;letter-spacing:.18em;text-transform:uppercase;text-decoration:none">Browse All Issues</a>
    </div>
    <div style="text-align:center;font-family:'DM Mono',monospace;font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:#7a7168">
      Share on
      <a href="https://www.linkedin.com/sharing/share-offsite/?url={site_url}" target="_blank" rel="noopener" style="color:#111010;margin-left:6px">LinkedIn</a>
      &nbsp;·&nbsp;
      <a href="https://twitter.com/intent/tweet?text={share_encoded}" target="_blank" rel="noopener" style="color:#111010">X / Twitter</a>
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
    new_block = (
        "  <!-- LATEST_BRIEF_START -->\n"
        "  <div class=\"section\">\n"
        "    <div class=\"section-label\">Latest Issue</div>\n"
        "    <div class=\"latest-card\">\n"
        "      <div class=\"latest-label\">Most Recent Brief</div>\n"
        f"      <div class=\"latest-date\">{data['date_display']}</div>\n"
        f"      <div class=\"latest-title\">{data['headline']}</div>\n"
        f"      <p class=\"latest-teaser\">{data['homepage_teaser']}</p>\n"
        f"      <a href=\"briefs/{date_iso}.html\" class=\"btn btn-dark\">Read Full Issue &rarr;</a>\n"
        "    </div>\n"
        "  </div>\n"
        "  <!-- LATEST_BRIEF_END -->"
    )
    updated = re.sub(
        r"<!-- LATEST_BRIEF_START -->.*?<!-- LATEST_BRIEF_END -->",
        lambda _: new_block,
        content,
        flags=re.DOTALL,
    )
    if updated == content:
        print("WARNING: LATEST_BRIEF_START/END not found in index.html.")
    else:
        INDEX_HTML.write_text(updated, encoding="utf-8")
        print("index.html updated.")


def update_archive(data: dict, date_iso: str) -> None:
    content = ARCHIVE_HTML.read_text(encoding="utf-8")
    parts = date_iso.split("-")
    month_abbr = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(parts[1])]
    day, year = int(parts[2]), parts[0]
    new_item = (
        f"\n    <li class=\"archive-item\">\n"
        f"      <div class=\"archive-date\">{month_abbr} {day}<br>{year}</div>\n"
        f"      <div>\n"
        f"        <a class=\"archive-title\" href=\"briefs/{date_iso}.html\">{data['headline']}</a>\n"
        f"        <p class=\"archive-teaser\">{data['archive_teaser']}</p>\n"
        f"      </div>\n"
        f"    </li>\n"
    )
    updated = re.sub(
        r"(<!-- ARCHIVE_LIST_START -->\s*<ul[^>]*>)",
        lambda m: m.group(0) + new_item,
        content,
        flags=re.DOTALL,
    )
    if updated == content:
        print("WARNING: ARCHIVE_LIST_START not found in archive.html.")
    else:
        ARCHIVE_HTML.write_text(updated, encoding="utf-8")
        print("archive.html updated.")


def main() -> None:
    print("=== The Brief — Daily Generator ===")

    if not SYSTEM_PROMPT_FILE.exists():
        print(f"ERROR: System prompt not found at {SYSTEM_PROMPT_FILE}")
        sys.exit(1)

    system_prompt = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    raw  = call_api(system_prompt)
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
