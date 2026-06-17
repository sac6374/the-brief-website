#!/usr/bin/env python3
"""
generate_brief.py — The Brief daily issue generator.

Calls the Anthropic API with web search enabled, generates a structured JSON brief,
renders it into an HTML page, and updates index.html + archive.html.

Usage:
    python scripts/generate_brief.py

Required environment variable:
    ANTHROPIC_API_KEY

The script exits with a non-zero code if:
    - The API key is missing
    - The API call fails
    - The response does not contain valid JSON
    - The JSON is missing required fields
    - Market data appears to be fabricated (basic sanity checks)

It will NOT write any files if generation fails.
"""

import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

# ── Dependency check ──────────────────────────────────────────────────────────
try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
PROMPTS_DIR = ROOT / "prompts"
BRIEFS_DIR = ROOT / "briefs"
INDEX_HTML = ROOT / "index.html"
ARCHIVE_HTML = ROOT / "archive.html"
SYSTEM_PROMPT_FILE = PROMPTS_DIR / "system_prompt.txt"

# ── Required JSON fields ──────────────────────────────────────────────────────
REQUIRED_FIELDS = [
    "date_iso", "date_display", "headline", "alert_strip",
    "ticker", "smart30",
    "s01_headline", "s01_items",
    "s02_headline", "s02_body_html", "s02_aside",
    "s03_chains",
    "s04_cards", "s04_watch_label", "s04_watch_body",
    "s05_sectors",
    "s06_universal", "s06_cards",
    "s07_bullets",
    "s08_term", "s08_body_html",
    "s09_quote",
    "sources", "linkedin_copy", "teaser",
]


def load_system_prompt() -> str:
    if not SYSTEM_PROMPT_FILE.exists():
        print(f"ERROR: System prompt not found at {SYSTEM_PROMPT_FILE}")
        sys.exit(1)
    return SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")


def call_api(system_prompt: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    today = date.today().strftime("%A, %B %-d, %Y")

    user_message = (
        f"Today is {today}. "
        "Use your web search tool to retrieve today's real market data and news stories, "
        "then produce a complete issue of The Brief following the system prompt instructions exactly. "
        "Search for: today's S&P 500 close, Nasdaq close, VIX, 10-year Treasury yield, WTI crude, "
        "Brent crude, top market movers, major earnings, any Fed news, and the top 2-3 market-moving stories. "
        "Return ONLY the JSON object described in the system prompt. No markdown fences, no commentary."
    )

    print(f"Calling Anthropic API (claude-sonnet-4-6) for {today}...")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            system=system_prompt,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
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

    # Extract text content from response
    text_content = ""
    for block in response.content:
        if block.type == "text":
            text_content += block.text

    if not text_content.strip():
        print("ERROR: API returned no text content. The model may have only used tools without producing output.")
        sys.exit(1)

    return text_content


def parse_json(raw: str) -> dict:
    # Strip markdown code fences if present
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse JSON from API response: {e}")
        print("--- Raw response (first 2000 chars) ---")
        print(raw[:2000])
        sys.exit(1)

    return data


def validate(data: dict) -> None:
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        print(f"ERROR: API response is missing required fields: {missing}")
        sys.exit(1)

    # Basic sanity: date_iso must match today
    today_iso = date.today().isoformat()
    if data.get("date_iso") != today_iso:
        print(f"WARNING: date_iso in response ({data.get('date_iso')}) does not match today ({today_iso}).")
        print("Overriding with today's date.")
        data["date_iso"] = today_iso

    # Sanity check ticker — at least 3 entries required
    ticker = data.get("ticker", [])
    if len(ticker) < 3:
        print("ERROR: ticker data has fewer than 3 entries. Market data may be missing.")
        sys.exit(1)

    # Reject placeholder-looking values
    for t in ticker:
        val = t.get("value", "")
        if val in ("X,XXX", "XX,XXX", "X.XX", "$XX.XX", ""):
            print(f"ERROR: Ticker '{t.get('label')}' has a placeholder value '{val}'. Real data not retrieved.")
            sys.exit(1)


def esc(s: str) -> str:
    """HTML-escape a plain string."""
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def render_html(data: dict) -> str:
    d = data
    date_iso = d["date_iso"]
    date_display = esc(d["date_display"])
    headline = esc(d["headline"])

    # Ticker HTML
    ticker_html = ""
    for t in d["ticker"]:
        direction_class = "up" if t.get("direction") == "up" else ("down" if t.get("direction") == "down" else "")
        ticker_html += f"""
    <div class="ticker-cell">
      <div class="t-label">{esc(t['label'])}</div>
      <div class="t-val">{esc(t['value'])}</div>
      <div class="t-chg {direction_class}">{esc(t['change'])}</div>
      <div class="t-note">{esc(t.get('note', ''))}</div>
    </div>"""

    # TOC HTML
    toc_html = ""
    for item in d.get("toc", []):
        toc_html += f"""      <li><a href="#s{item['num']}"><span class="toc-num">{esc(item['num'])}</span><span class="toc-title">{esc(item['title'])}</span></a></li>\n"""

    # s01 items
    s01_html = ""
    for item in d["s01_items"]:
        s01_html += f"""    <div class="dev-item">
      <div class="dev-category">{esc(item['category'])}</div>
      {item['body_html']}
    </div>\n"""

    # s03 chains
    s03_html = ""
    for chain in d["s03_chains"]:
        s03_html += f"""      <div class="chain-row">
        <div class="chain-label">{esc(chain['label'])}</div>
        <div class="chain-text">{chain['text_html']}</div>
      </div>\n"""

    # s04 cards
    s04_cards_html = ""
    for card in d["s04_cards"]:
        s04_cards_html += f"""      <div class="grid-card">
        <div class="card-label">{esc(card['label'])}</div>
        <p>{esc(card['body'])}</p>
      </div>\n"""

    # s05 sectors
    s05_html = ""
    for sector in d["s05_sectors"]:
        s05_html += f"""      <div class="sector-card {sector.get('card_class', '')}">
        <div class="sector-name">{esc(sector['name'])} <span class="sector-badge {sector.get('badge_class', '')}">{esc(sector.get('badge', ''))}</span></div>
        <p>{esc(sector['body'])}</p>
      </div>\n"""

    # s06 cards
    s06_cards_html = ""
    for card in d["s06_cards"]:
        s06_cards_html += f"""      <div class="career-card">
        <div class="career-path">{esc(card['path'])}</div>
        <p>{esc(card['body'])}</p>
      </div>\n"""

    # s07 bullets
    s07_html = ""
    for bullet in d["s07_bullets"]:
        s07_html += f"        <li>{bullet}</li>\n"

    site_url = f"https://thebrieffinance.com/briefs/{date_iso}.html"
    linkedin_encoded = d.get("linkedin_copy", "").replace("{{URL}}", site_url)
    share_text_encoded = f"Today%27s+The+Brief%3A+{headline[:60].replace(' ', '+')}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Brief — {date_display}</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=DM+Mono:wght@300;400;500&family=Source+Serif+4:ital,opsz,wght@0,8..60,300;0,8..60,400;0,8..60,600;1,8..60,300;1,8..60,400&display=swap" rel="stylesheet">
<style>
  :root{{--ink:#111010;--paper:#f7f3ec;--paper-2:#ede8df;--rule:#d5cfc4;--red:#b02020;--gold:#8a6710;--gold-bg:#faf4e4;--green:#1a5432;--green-bg:#edf6f1;--muted:#7a7168;--muted-2:#a09585}}
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Source Serif 4',Georgia,serif;background:var(--paper);color:var(--ink);font-size:17px;line-height:1.78;-webkit-font-smoothing:antialiased}}
  .masthead{{padding:36px 0 24px;text-align:center;border-bottom:2.5px solid var(--ink);border-top:4px solid var(--ink)}}
  .masthead-eyebrow{{font-family:'DM Mono',monospace;font-size:10.5px;letter-spacing:.22em;text-transform:uppercase;color:var(--muted);margin-bottom:12px}}
  .masthead-title{{font-family:'Playfair Display',Georgia,serif;font-size:clamp(44px,8vw,72px);font-weight:900;letter-spacing:-.025em;line-height:.95;margin-bottom:12px}}
  .masthead-rule{{display:flex;align-items:center;justify-content:center;gap:14px}}
  .masthead-rule::before,.masthead-rule::after{{content:'';display:block;height:1px;width:60px;background:var(--rule)}}
  .masthead-tagline{{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted-2)}}
  .alert-strip{{background:var(--ink);color:var(--paper);padding:10px 20px;display:flex;align-items:center;justify-content:center;gap:10px;font-family:'DM Mono',monospace;font-size:10.5px;letter-spacing:.14em;text-transform:uppercase}}
  .alert-pip{{width:6px;height:6px;border-radius:50%;background:#e05050;flex-shrink:0;animation:blink 1.6s ease-in-out infinite}}
  @keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.25}}}}
  .wrap{{max-width:680px;margin:0 auto;padding:0 22px 72px}}
  .dateline{{display:flex;justify-content:space-between;padding:14px 0;border-bottom:1px solid var(--rule);font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}}
  .ticker{{display:grid;grid-template-columns:repeat(5,1fr);border-bottom:1px solid var(--rule)}}
  .ticker-cell{{padding:12px 10px;border-right:1px solid var(--rule);text-align:center}}
  .ticker-cell:last-child{{border-right:none}}
  .t-label{{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin-bottom:4px}}
  .t-val{{font-family:'DM Mono',monospace;font-size:13px;font-weight:500;color:var(--ink);margin-bottom:2px}}
  .t-chg{{font-family:'DM Mono',monospace;font-size:10px;font-weight:500}}
  .t-note{{font-family:'DM Mono',monospace;font-size:7.5px;color:var(--muted-2);margin-top:2px}}
  .down{{color:var(--red)}}.up{{color:var(--green)}}
  .toc{{border:1px solid var(--rule);border-top:2px solid var(--ink);padding:16px 20px;margin-top:16px}}
  .toc-label{{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.2em;text-transform:uppercase;color:var(--muted);margin-bottom:10px}}
  .toc-list{{list-style:none;padding:0;margin:0;columns:2;column-gap:24px}}
  @media(max-width:480px){{.toc-list{{columns:1}}}}
  .toc-list li{{padding:3px 0;break-inside:avoid}}
  .toc-list a{{font-family:'DM Mono',monospace;font-size:10.5px;letter-spacing:.04em;color:var(--ink);text-decoration:none;display:flex;align-items:baseline;gap:7px}}
  .toc-list a:hover .toc-title{{color:var(--red);border-color:var(--red)}}
  .toc-num{{color:var(--red);font-size:9px;flex-shrink:0;letter-spacing:.08em}}
  .toc-title{{border-bottom:1px solid var(--rule);padding-bottom:1px}}
  .smart30{{background:var(--ink);color:var(--paper);padding:20px 26px}}
  .smart30-label{{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.2em;text-transform:uppercase;color:#888;margin-bottom:10px}}
  .smart30 p{{font-size:15.5px;line-height:1.75;color:#ede8df;margin-bottom:0}}
  .section{{margin-top:40px;padding-top:20px;border-top:1px solid var(--rule)}}
  .section.first{{border-top:2px solid var(--ink);margin-top:32px}}
  .section-label{{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.22em;text-transform:uppercase;color:var(--muted);margin-bottom:7px}}
  .section-num{{color:var(--red)}}
  h2{{font-family:'Playfair Display',Georgia,serif;font-size:clamp(19px,3.2vw,24px);font-weight:700;line-height:1.22;letter-spacing:-.01em;color:var(--ink);margin-bottom:18px}}
  .dev-item{{padding:0 0 18px 18px;border-left:2px solid var(--ink);margin-bottom:18px}}
  .dev-item:last-child{{margin-bottom:0;padding-bottom:0}}
  .dev-category{{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin-bottom:5px}}
  .dev-item p{{font-size:15px;line-height:1.70}}
  p{{font-size:16px;line-height:1.80;margin-bottom:14px;color:var(--ink)}}
  p:last-child{{margin-bottom:0}}
  em{{font-style:italic}}strong{{font-weight:600}}
  .aside{{border-left:2px solid var(--rule);padding:3px 0 3px 16px;margin:18px 0;color:var(--muted);font-size:14px;line-height:1.70;font-style:italic}}
  .chain{{background:var(--paper-2);border-top:2px solid var(--ink);border-bottom:1px solid var(--rule);padding:20px 24px;margin:18px 0}}
  .chain-row{{display:grid;grid-template-columns:68px 1fr;gap:14px;padding:10px 0;border-bottom:1px solid var(--rule);align-items:start}}
  .chain-row:first-child{{padding-top:0}}.chain-row:last-child{{padding-bottom:0;border-bottom:none}}
  .chain-label{{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);padding-top:2px;line-height:1.5}}
  .chain-text{{font-family:'DM Mono',monospace;font-size:11.5px;line-height:1.85;color:var(--ink)}}
  .arr{{color:var(--red);margin:0 3px}}.arr-g{{color:var(--green);margin:0 3px}}
  .grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:4px}}
  @media(max-width:540px){{.grid-2{{grid-template-columns:1fr}}}}
  .grid-card{{border:1px solid var(--rule);border-top:2.5px solid var(--ink);padding:16px 16px 18px;background:var(--paper)}}
  .card-label{{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin-bottom:8px}}
  .grid-card p{{font-size:13px;line-height:1.66;margin-bottom:0}}
  .watch{{background:var(--gold-bg);border:1px solid #dfc98a;border-left:2.5px solid var(--gold);padding:15px 18px;margin-top:12px}}
  .watch-label{{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--gold);margin-bottom:7px}}
  .watch p{{font-size:13px;line-height:1.66;margin-bottom:0;color:#5a3f00}}
  .sector-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:4px}}
  @media(max-width:520px){{.sector-grid{{grid-template-columns:1fr}}}}
  .sector-card{{border:1px solid var(--rule);padding:13px 15px;background:var(--paper)}}
  .sector-card.winning{{border-top:2.5px solid var(--green)}}.sector-card.losing{{border-top:2.5px solid var(--red)}}.sector-card.mixed{{border-top:2.5px solid var(--gold)}}
  .sector-name{{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin-bottom:5px;display:flex;align-items:center;gap:5px;flex-wrap:wrap}}
  .sector-badge{{font-size:8px;padding:1px 5px;border-radius:2px;font-weight:500}}
  .badge-win{{background:var(--green-bg);color:var(--green)}}.badge-lose{{background:#fdf2f2;color:var(--red)}}.badge-watch{{background:var(--gold-bg);color:var(--gold)}}
  .sector-card p{{font-size:12.5px;line-height:1.63;margin-bottom:0}}
  .career-universal{{background:var(--paper-2);border-top:2px solid var(--ink);border-bottom:1px solid var(--rule);padding:14px 18px;margin-bottom:14px}}
  .career-universal-label{{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}}
  .career-universal p{{font-size:13.5px;line-height:1.68;margin-bottom:0;font-style:italic;color:var(--ink)}}
  .career-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
  .career-grid .career-card:last-child:nth-child(odd){{grid-column:1 / -1}}
  @media(max-width:520px){{.career-grid{{grid-template-columns:1fr}}}}
  .career-card{{border:1px solid var(--rule);padding:13px 15px 15px;background:var(--paper)}}
  .career-path{{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin-bottom:5px}}
  .career-card p{{font-size:12.5px;line-height:1.63;margin-bottom:0}}
  .interview-box{{border:1px solid var(--rule);border-left:2.5px solid var(--ink);padding:16px 20px;margin-top:6px}}
  .interview-box ul{{list-style:none;padding:0;margin:0}}
  .interview-box li{{font-size:14px;line-height:1.68;padding:7px 0 7px 16px;border-bottom:1px solid var(--rule);position:relative}}
  .interview-box li::before{{content:'→';position:absolute;left:0;color:var(--red);font-family:'DM Mono',monospace;font-size:10px;top:10px}}
  .interview-box li:last-child{{border-bottom:none}}
  .term{{border:1px solid var(--rule);padding:20px 24px 22px;margin-top:6px}}
  .term-word{{font-family:'Playfair Display',Georgia,serif;font-size:20px;font-weight:700;font-style:italic;color:var(--red);margin-bottom:9px}}
  .term p{{font-size:14.5px;margin-bottom:0}}
  .say{{background:var(--green-bg);border:1px solid #b2d9c3;border-left:2.5px solid var(--green);padding:18px 22px 20px;margin-top:6px}}
  .say-context{{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:var(--green);display:block;margin-bottom:6px}}
  .say p{{font-size:14.5px;line-height:1.76;color:#0e3324;font-style:italic;margin-bottom:0}}
  .sources{{margin-top:36px;padding-top:14px;border-top:1px solid var(--rule);font-family:'DM Mono',monospace;font-size:9.5px;color:var(--muted);line-height:1.8}}
  .sources strong{{font-weight:500;text-transform:uppercase;letter-spacing:.1em;font-size:8.5px}}
  .footer{{margin-top:24px;padding-top:16px;border-top:2px solid var(--ink);text-align:center;font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);line-height:1.9}}
</style>
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
  {esc(d['alert_strip'])}
</div>

<div class="wrap">
  <div class="dateline">
    <span>{date_display}</span>
    <span>5-minute read</span>
  </div>

  <div class="ticker">{ticker_html}
  </div>

  <nav class="toc">
    <div class="toc-label">In this edition</div>
    <ul class="toc-list">
{toc_html}    </ul>
  </nav>

  <div class="smart30" id="s00">
    <div class="smart30-label">Smart in 30 Seconds</div>
    <p>{esc(d['smart30'])}</p>
  </div>

  <div class="section first" id="s01">
    <div class="section-label"><span class="section-num">01 —</span> What Moved Markets Today</div>
    <h2>{esc(d['s01_headline'])}</h2>
{s01_html}  </div>

  <div class="section" id="s02">
    <div class="section-label"><span class="section-num">02 —</span> Why It Mattered</div>
    <h2>{esc(d['s02_headline'])}</h2>
    {d['s02_body_html']}
    <div class="aside">{esc(d['s02_aside'])}</div>
  </div>

  <div class="section" id="s03">
    <div class="section-label"><span class="section-num">03 —</span> The Chain Reaction</div>
    <h2>Follow the logic.</h2>
    <div class="chain">
{s03_html}    </div>
  </div>

  <div class="section" id="s04">
    <div class="section-label"><span class="section-num">04 —</span> What It Means</div>
    <h2>Breaking it down.</h2>
    <div class="grid-2">
{s04_cards_html}    </div>
    <div class="watch">
      <div class="watch-label">{esc(d['s04_watch_label'])}</div>
      <p>{esc(d['s04_watch_body'])}</p>
    </div>
  </div>

  <div class="section" id="s05">
    <div class="section-label"><span class="section-num">05 —</span> Market Sector Lens</div>
    <h2>Who's moving and why.</h2>
    <div class="sector-grid">
{s05_html}    </div>
  </div>

  <div class="section" id="s06">
    <div class="section-label"><span class="section-num">06 —</span> Finance Career Lens</div>
    <h2>What people in finance are actually thinking about today.</h2>
    <div class="career-universal">
      <div class="career-universal-label">For everyone in finance</div>
      <p>{esc(d['s06_universal'])}</p>
    </div>
    <div class="career-grid">
{s06_cards_html}    </div>
  </div>

  <div class="section" id="s07">
    <div class="section-label"><span class="section-num">07 —</span> Why This Matters for Interviews This Week</div>
    <h2>What to actually use in a conversation.</h2>
    <div class="interview-box">
      <ul>
{s07_html}      </ul>
    </div>
  </div>

  <div class="section" id="s08">
    <div class="section-label"><span class="section-num">08 —</span> Term of the Day</div>
    <div class="term">
      <div class="term-word">{esc(d['s08_term'])}</div>
      {d['s08_body_html']}
    </div>
  </div>

  <div class="section" id="s09">
    <div class="section-label"><span class="section-num">09 —</span> Say This Today</div>
    <div class="say">
      <span class="say-context">{esc(d.get('s09_context', 'For an interview, coffee chat, or networking call'))}</span>
      <p>"{esc(d['s09_quote'])}"</p>
    </div>
  </div>

  <div class="sources">
    <strong>Sources</strong><br>
    {esc(d['sources'])}
  </div>

  <div class="footer">
    The Brief &nbsp;·&nbsp; Daily Market Intelligence · {date_display}<br>
    Not investment advice &nbsp;·&nbsp; For educational purposes only
  </div>

  <div style="margin-top:32px;border-top:2px solid #111010;padding-top:28px;display:flex;flex-direction:column;gap:12px">
    <div style="display:flex;gap:12px;flex-wrap:wrap">
      <a href="../subscribe.html" style="flex:1;min-width:160px;display:block;background:#111010;color:#f7f3ec;text-align:center;padding:14px 20px;font-family:'DM Mono',monospace;font-size:10.5px;letter-spacing:.18em;text-transform:uppercase;text-decoration:none">Subscribe — It's Free</a>
      <a href="../archive.html" style="flex:1;min-width:160px;display:block;border:1px solid #111010;color:#111010;text-align:center;padding:14px 20px;font-family:'DM Mono',monospace;font-size:10.5px;letter-spacing:.18em;text-transform:uppercase;text-decoration:none">Browse All Issues</a>
    </div>
    <div style="text-align:center;font-family:'DM Mono',monospace;font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;color:#7a7168">
      Share on
      <a href="https://www.linkedin.com/sharing/share-offsite/?url={site_url}" target="_blank" rel="noopener" style="color:#111010;margin-left:6px">LinkedIn</a>
      &nbsp;·&nbsp;
      <a href="https://twitter.com/intent/tweet?text={share_text_encoded}&url={site_url}" target="_blank" rel="noopener" style="color:#111010">X / Twitter</a>
    </div>
  </div>
</div>
</body>
</html>"""

    return html


def save_linkedin_copy(data: dict, date_iso: str) -> None:
    linkedin_dir = ROOT / "linkedin"
    linkedin_dir.mkdir(exist_ok=True)
    site_url = f"https://thebrieffinance.com/briefs/{date_iso}.html"
    copy = data.get("linkedin_copy", "").replace("{{URL}}", site_url)
    out_file = linkedin_dir / f"{date_iso}.txt"
    out_file.write_text(copy, encoding="utf-8")
    print(f"LinkedIn copy saved: {out_file}")


def update_index(data: dict, date_iso: str) -> None:
    content = INDEX_HTML.read_text(encoding="utf-8")
    date_parts = date_iso.split("-")
    month_names = ["", "January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    month = month_names[int(date_parts[1])]
    day = int(date_parts[2])
    year = date_parts[0]

    new_latest = f"""  <!-- LATEST_BRIEF_START -->
  <div class="section">
    <div class="section-label">Latest Issue</div>
    <div class="latest-card">
      <div class="latest-label">Most Recent Brief</div>
      <div class="latest-date">{data['date_display']}</div>
      <div class="latest-title">{data['headline']}</div>
      <p class="latest-teaser">{data['teaser']}</p>
      <a href="briefs/{date_iso}.html" class="btn btn-dark">Read Full Issue →</a>
    </div>
  </div>
  <!-- LATEST_BRIEF_END -->"""

    updated = re.sub(
        r"<!-- LATEST_BRIEF_START -->.*?<!-- LATEST_BRIEF_END -->",
        new_latest,
        content,
        flags=re.DOTALL,
    )
    INDEX_HTML.write_text(updated, encoding="utf-8")
    print("index.html updated.")


def update_archive(data: dict, date_iso: str) -> None:
    content = ARCHIVE_HTML.read_text(encoding="utf-8")
    date_parts = date_iso.split("-")
    month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    month_abbr = month_names[int(date_parts[1])]
    day = int(date_parts[2])
    year = date_parts[0]

    new_item = f"""
    <li class="archive-item">
      <div class="archive-date">{month_abbr} {day}<br>{year}</div>
      <div>
        <a class="archive-title" href="briefs/{date_iso}.html">{data['headline']}</a>
        <p class="archive-teaser">{data['teaser']}</p>
      </div>
    </li>
"""

    updated = content.replace(
        "<!-- ARCHIVE_LIST_START -->\n  <ul class=\"archive-list\" style=\"margin-top:8px\">",
        f"<!-- ARCHIVE_LIST_START -->\n  <ul class=\"archive-list\" style=\"margin-top:8px\">{new_item}",
    )
    ARCHIVE_HTML.write_text(updated, encoding="utf-8")
    print("archive.html updated.")


def main() -> None:
    print("=== The Brief — Daily Generator ===")

    system_prompt = load_system_prompt()
    raw = call_api(system_prompt)
    data = parse_json(raw)
    validate(data)

    date_iso = data["date_iso"]
    out_path = BRIEFS_DIR / f"{date_iso}.html"

    if out_path.exists():
        print(f"WARNING: {out_path} already exists. Overwriting.")

    html = render_html(data)
    out_path.write_text(html, encoding="utf-8")
    print(f"Brief written: {out_path}")

    save_linkedin_copy(data, date_iso)
    update_index(data, date_iso)
    update_archive(data, date_iso)

    print("=== Done. All files updated. ===")


if __name__ == "__main__":
    main()
