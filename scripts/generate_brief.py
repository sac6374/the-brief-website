#!/usr/bin/env python3
"""
generate_brief.py — The Brief market update generator.

Supports multiple update types with Eastern Time scheduling.

Usage:
    python scripts/generate_brief.py --type morning
    python scripts/generate_brief.py --type midday
    python scripts/generate_brief.py --type close
    python scripts/generate_brief.py --type afterhours
    python scripts/generate_brief.py --type breaking
    python scripts/generate_brief.py --type auto     # detects America/New_York time

Auto-mode windows (ET):
    08:00 → morning     (window 07:30–09:00)
    12:00 → midday      (window 11:30–13:00)
    16:15 → close       (window 15:45–17:15)
    18:30 → afterhours  (window 18:00–19:30)

Required env var: ANTHROPIC_API_KEY
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, date
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic not installed. Run: pip install anthropic")
    sys.exit(1)

try:
    import pytz
except ImportError:
    print("ERROR: pytz not installed. Run: pip install pytz")
    sys.exit(1)

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT               = Path(__file__).parent.parent
BRIEFS_DIR         = ROOT / "briefs"
BREAKING_DIR       = ROOT / "breaking"
INDEX_HTML         = ROOT / "index.html"
ARCHIVE_HTML       = ROOT / "archive.html"
SITEMAP_XML        = ROOT / "sitemap.xml"
SYSTEM_PROMPT_FILE = ROOT / "prompts" / "system_prompt.txt"
RAW_RESPONSE_FILE  = ROOT / "claude_raw_response.txt"
LINKEDIN_DIR       = ROOT / "linkedin"

# ── Timezone ───────────────────────────────────────────────────────────────────
ET = pytz.timezone("America/New_York")

# ── Update type config ─────────────────────────────────────────────────────────
UPDATE_TYPES = ["morning", "midday", "close", "afterhours", "breaking", "auto"]

TYPE_LABELS = {
    "morning":    "Morning Brief",
    "midday":     "Midday Update",
    "close":      "Market Close",
    "afterhours": "After Hours",
    "breaking":   "Breaking",
}

TYPE_BADGE_CSS = {
    "morning":    "badge-morning",
    "midday":     "badge-midday",
    "close":      "badge-close",
    "afterhours": "badge-afterhours",
    "breaking":   "badge-breaking",
}

# ── Existing full-brief required fields (close type) ──────────────────────────
CLOSE_REQUIRED_FIELDS = [
    "date_iso", "date_display", "headline", "alert_strip", "seo_title",
    "meta_description", "issue_kicker", "opening_summary",
    "feature_image_url", "feature_image_alt", "feature_image_caption",
    "feature_image_credit", "feature_image_source_url", "feature_image_type",
    "market_snapshot", "archive_teaser", "homepage_teaser",
    "linkedin_post", "share_text", "article_html",
]

# Required fields for lighter updates
UPDATE_REQUIRED_FIELDS = [
    "publish", "date_iso", "date_display", "headline", "summary",
    "market_snapshot", "key_points", "what_to_watch",
    "archive_teaser", "homepage_teaser",
]

BREAKING_REQUIRED_FIELDS = [
    "publish", "date_iso", "date_display", "headline", "slug",
    "summary", "why_it_matters", "market_impact",
]

# ── Image safety ───────────────────────────────────────────────────────────────
SAFE_IMAGE_TYPES = {"wikimedia", "press", "unsplash", "pexels", "none"}

BLOCKED_IMAGE_DOMAINS = [
    "gettyimages.com", "shutterstock.com", "alamy.com", "istockphoto.com",
    "dreamstime.com", "123rf.com", "depositphotos.com",
    "apimages.com", "ap.org", "reuters.com", "afp.com", "afpforum.com",
    "bloomberg.com", "bloomberg.net", "wsj.com", "dowjones.com", "ft.com",
    "cnbc.com", "nytimes.com", "nyti.ms", "nbcnews.com", "bbc.co.uk", "bbc.com",
    "marketwatch.com", "businessinsider.com", "seekingalpha.com",
    "theatlantic.com", "washingtonpost.com", "economist.com",
]

# ── Inline CSS for full brief pages (close type) ──────────────────────────────
BRIEF_CSS = """
  :root{--ink:#0d1b2a;--paper:#f7f4ef;--paper-2:#ede9df;--rule:#d4cfc4;--red:#b52020;--gold:#a07820;--gold-bg:#faf4e2;--green:#1a6840;--green-bg:#edf7f1;--muted:#7a7268;--muted-2:#a09a90}
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Source Serif 4',Georgia,serif;background:var(--paper);color:var(--ink);font-size:17px;line-height:1.78;-webkit-font-smoothing:antialiased}
  .brief-nav{background:var(--ink);display:flex;align-items:center;justify-content:space-between;padding:0 28px;border-bottom:1px solid rgba(255,255,255,0.07);position:sticky;top:0;z-index:100}
  .brief-nav-brand{font-family:'Playfair Display',Georgia,serif;font-size:18px;font-weight:900;letter-spacing:-.015em;color:#f7f4ef;text-decoration:none;padding:14px 0;flex-shrink:0}
  .brief-nav-links{display:flex;align-items:center;gap:0}
  .brief-nav-links a{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.2em;text-transform:uppercase;color:rgba(247,244,239,0.5);text-decoration:none;padding:10px 14px;transition:color .15s}
  .brief-nav-links a:hover{color:#f7f4ef}
  .brief-nav-links .nav-cta{color:#f7f4ef !important;border:1px solid rgba(247,244,239,0.28);padding:8px 16px;margin-left:6px}
  .brief-nav-links .nav-cta:hover{border-color:rgba(247,244,239,0.6);background:rgba(255,255,255,0.07)}
  .masthead{padding:28px 0 20px;text-align:center;border-bottom:2px solid var(--ink);border-top:3px solid var(--ink)}
  .masthead-eyebrow{font-family:'DM Mono',monospace;font-size:9.5px;letter-spacing:.26em;text-transform:uppercase;color:var(--muted);margin-bottom:9px}
  .masthead-title{font-family:'Playfair Display',Georgia,serif;font-size:clamp(38px,6.5vw,58px);font-weight:900;letter-spacing:-.025em;line-height:.96;margin-bottom:11px}
  .masthead-rule{display:flex;align-items:center;justify-content:center;gap:14px}
  .masthead-rule::before,.masthead-rule::after{content:'';display:block;height:1px;width:48px;background:var(--rule)}
  .masthead-tagline{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted-2)}
  .alert-strip{background:var(--ink);color:var(--paper);padding:9px 20px;display:flex;align-items:center;justify-content:center;gap:10px;font-family:'DM Mono',monospace;font-size:9.5px;letter-spacing:.13em;text-transform:uppercase;flex-wrap:wrap}
  .alert-pip{width:5px;height:5px;border-radius:50%;background:#e05050;flex-shrink:0;animation:blink 1.6s ease-in-out infinite}
  @keyframes blink{0%,100%{opacity:1}50%{opacity:.25}}
  .wrap{max-width:680px;margin:0 auto;padding:0 22px 80px}
  .issue-kicker{font-family:'DM Mono',monospace;font-size:9.5px;letter-spacing:.24em;text-transform:uppercase;color:var(--red);padding:22px 0 8px}
  .issue-headline{font-family:'Playfair Display',Georgia,serif;font-size:clamp(24px,4vw,32px);font-weight:900;line-height:1.12;letter-spacing:-.018em;color:var(--ink);margin-bottom:16px}
  .opening-summary{font-size:15.5px;line-height:1.84;color:#2a2a22;margin-bottom:22px;border-left:3px solid var(--ink);padding-left:16px}
  .feature-img-wrap{margin-bottom:4px;overflow:hidden;background:#e5e1d8}
  .feature-img{width:100%;height:360px;object-fit:cover;display:block}
  @media(max-width:560px){.feature-img{height:220px}}
  .feature-caption-bar{padding:8px 12px 10px;background:var(--paper-2);border:1px solid var(--rule);border-top:none;margin-bottom:20px;display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:4px}
  .feature-caption-text{font-family:'DM Mono',monospace;font-size:9.5px;color:var(--muted);line-height:1.5}
  .feature-credit{font-family:'DM Mono',monospace;font-size:8.5px;color:var(--muted-2);white-space:nowrap;text-decoration:none}
  .feature-fallback{height:1px;background:var(--rule);margin:4px 0 24px}
  .market-snapshot{border:1px solid var(--rule);border-top:2px solid var(--ink);background:var(--paper-2);margin-bottom:8px}
  .market-snapshot-header{display:flex;justify-content:space-between;align-items:center;padding:10px 16px 0}
  .market-snapshot-label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.22em;text-transform:uppercase;color:var(--muted)}
  .market-snapshot-time{font-family:'DM Mono',monospace;font-size:8px;color:var(--muted-2)}
  .market-snapshot-grid{display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid var(--rule);margin-top:8px}
  @media(max-width:420px){.market-snapshot-grid{grid-template-columns:repeat(2,1fr)}}
  .snapshot-cell{padding:12px 14px;border-right:1px solid var(--rule);border-bottom:1px solid var(--rule)}
  .snapshot-cell:nth-child(3n){border-right:none}
  .snapshot-cell:nth-last-child(-n+3){border-bottom:none}
  @media(max-width:420px){.snapshot-cell:nth-child(3n){border-right:1px solid var(--rule)}.snapshot-cell:nth-child(2n){border-right:none}.snapshot-cell:nth-last-child(-n+3){border-bottom:1px solid var(--rule)}.snapshot-cell:nth-last-child(-n+2){border-bottom:none}}
  .snapshot-label{font-family:'DM Mono',monospace;font-size:8px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted-2);margin-bottom:4px}
  .snapshot-value{font-family:'DM Mono',monospace;font-size:17px;font-weight:500;color:var(--ink);margin-bottom:3px;line-height:1}
  .snapshot-change{font-family:'DM Mono',monospace;font-size:11px;font-weight:500}
  .snapshot-change.up{color:var(--green)}.snapshot-change.down{color:var(--red)}.snapshot-change.flat{color:var(--muted)}
  .snapshot-note{font-family:'DM Mono',monospace;font-size:7.5px;color:var(--muted-2);margin-top:3px}
  .toc{border:1px solid var(--rule);border-top:2px solid var(--ink);padding:16px 20px;margin-bottom:8px;background:var(--paper)}
  .toc-label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.22em;text-transform:uppercase;color:var(--muted);margin-bottom:12px}
  .toc-list{list-style:none;padding:0;margin:0;columns:2;column-gap:24px}
  @media(max-width:480px){.toc-list{columns:1}}
  .toc-list li{padding:3px 0;break-inside:avoid}
  .toc-list a{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.04em;color:var(--ink);text-decoration:none;display:flex;align-items:baseline;gap:8px}
  .toc-list a:hover .toc-title{color:var(--red);border-color:var(--red)}
  .toc-num{color:var(--red);font-size:9px;flex-shrink:0;letter-spacing:.08em}
  .toc-title{border-bottom:1px solid var(--rule);padding-bottom:1px;flex:1}
  .smart30{background:var(--ink);color:var(--paper);padding:24px 28px;margin-top:32px;border-top:3px solid var(--gold)}
  .smart30-label{font-family:'DM Mono',monospace;font-size:8.5px;letter-spacing:.24em;text-transform:uppercase;color:rgba(247,244,239,0.45);margin-bottom:12px}
  .smart30 p{font-size:15.5px;line-height:1.80;color:rgba(247,244,239,0.88);margin-bottom:0}
  .section{margin-top:44px;padding-top:22px;border-top:1px solid var(--rule)}
  .section.first{border-top:2px solid var(--ink);margin-top:32px}
  .section-label{font-family:'DM Mono',monospace;font-size:9.5px;letter-spacing:.22em;text-transform:uppercase;color:var(--muted);margin-bottom:8px}
  .section-num{color:var(--red);margin-right:2px}
  h2{font-family:'Playfair Display',Georgia,serif;font-size:clamp(19px,3.2vw,24px);font-weight:700;line-height:1.22;letter-spacing:-.01em;color:var(--ink);margin-bottom:18px}
  .dev-item{padding:0 0 18px 18px;border-left:2px solid var(--rule);margin-bottom:18px}
  .dev-item:last-child{margin-bottom:0;padding-bottom:0}
  .dev-category{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
  .dev-item p{font-size:15px;line-height:1.72}
  p{font-size:15.5px;line-height:1.82;margin-bottom:14px;color:var(--ink)}
  p:last-child{margin-bottom:0}
  em{font-style:italic}strong{font-weight:600}
  a{color:var(--red)}
  .aside{border-left:2px solid var(--rule);padding:3px 0 3px 16px;margin:18px 0;color:var(--muted);font-size:14px;line-height:1.72;font-style:italic}
  .chain{background:var(--paper-2);border-top:2px solid var(--ink);border-left:none;border-right:none;border-bottom:1px solid var(--rule);padding:22px 24px;margin:18px 0}
  .chain-row{display:grid;grid-template-columns:76px 1fr;gap:16px;padding:11px 0;border-bottom:1px solid var(--rule);align-items:start}
  .chain-row:first-child{padding-top:0}.chain-row:last-child{padding-bottom:0;border-bottom:none}
  .chain-label{font-family:'DM Mono',monospace;font-size:8.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted-2);padding-top:2px;line-height:1.5}
  .chain-text{font-family:'DM Mono',monospace;font-size:11.5px;line-height:1.88;color:var(--ink)}
  .arr{color:var(--red);margin:0 4px;font-weight:500}.arr-g{color:var(--green);margin:0 4px;font-weight:500}
  .grid-2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:4px}
  @media(max-width:540px){.grid-2{grid-template-columns:1fr}}
  .grid-card{border:1px solid var(--rule);border-top:2.5px solid var(--ink);padding:16px 17px 18px;background:var(--paper)}
  .card-label{font-family:'DM Mono',monospace;font-size:8.5px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin-bottom:8px}
  .grid-card p{font-size:13px;line-height:1.68;margin-bottom:0}
  .watch{background:var(--gold-bg);border:1px solid rgba(160,120,32,0.3);border-left:3px solid var(--gold);padding:15px 18px;margin-top:14px}
  .watch-label{font-family:'DM Mono',monospace;font-size:8.5px;letter-spacing:.18em;text-transform:uppercase;color:var(--gold);margin-bottom:7px}
  .watch p{font-size:13px;line-height:1.68;margin-bottom:0;color:#5a3f00}
  .sector-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:4px}
  @media(max-width:520px){.sector-grid{grid-template-columns:1fr}}
  .sector-card{border:1px solid var(--rule);padding:14px 16px;background:var(--paper)}
  .sector-card.winning{border-top:3px solid var(--green)}.sector-card.losing{border-top:3px solid var(--red)}.sector-card.mixed{border-top:3px solid var(--gold)}
  .sector-name{font-family:'DM Mono',monospace;font-size:8.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin-bottom:6px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
  .sector-badge{font-size:8px;padding:2px 6px;font-weight:500}
  .badge-win{background:var(--green-bg);color:var(--green)}.badge-lose{background:#fdf2f2;color:var(--red)}.badge-watch{background:var(--gold-bg);color:var(--gold)}
  .sector-card p{font-size:12.5px;line-height:1.65;margin-bottom:0}
  .career-universal{background:var(--ink);color:var(--paper);padding:16px 20px;margin-bottom:14px}
  .career-universal-label{font-family:'DM Mono',monospace;font-size:8.5px;letter-spacing:.2em;text-transform:uppercase;color:rgba(247,244,239,0.45);margin-bottom:8px}
  .career-universal p{font-size:14px;line-height:1.72;margin-bottom:0;font-style:italic;color:rgba(247,244,239,0.88)}
  .career-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .career-grid .career-card:last-child:nth-child(odd){grid-column:1 / -1}
  @media(max-width:520px){.career-grid{grid-template-columns:1fr}}
  .career-card{border:1px solid var(--rule);border-top:2px solid var(--ink);padding:14px 16px 16px;background:var(--paper)}
  .career-path{font-family:'DM Mono',monospace;font-size:8.5px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
  .career-card p{font-size:12.5px;line-height:1.65;margin-bottom:0}
  .interview-box{border:1px solid var(--rule);border-left:3px solid var(--ink);padding:16px 20px;margin-top:6px;background:var(--paper)}
  .interview-box ul{list-style:none;padding:0;margin:0}
  .interview-box li{font-size:14px;line-height:1.70;padding:8px 0 8px 18px;border-bottom:1px solid var(--rule);position:relative}
  .interview-box li::before{content:'→';position:absolute;left:0;color:var(--red);font-family:'DM Mono',monospace;font-size:11px;top:10px}
  .interview-box li:last-child{border-bottom:none}
  .term{border:1px solid var(--rule);padding:22px 24px;margin-top:6px;background:var(--paper)}
  .term-word{font-family:'Playfair Display',Georgia,serif;font-size:20px;font-weight:700;font-style:italic;color:var(--red);margin-bottom:10px}
  .term p{font-size:14.5px;margin-bottom:0}
  .say{background:var(--ink);border-left:none;padding:24px 26px 26px;margin-top:6px}
  .say-context{font-family:'DM Mono',monospace;font-size:8.5px;letter-spacing:.18em;text-transform:uppercase;color:rgba(247,244,239,0.45);display:block;margin-bottom:10px}
  .say p{font-size:15px;line-height:1.82;color:rgba(247,244,239,0.88);font-style:italic;margin-bottom:0}
  .say p::before{content:'"';font-family:'Playfair Display',Georgia,serif;font-size:36px;color:rgba(247,244,239,0.18);line-height:0;vertical-align:-14px;margin-right:4px}
  .sources{margin-top:40px;padding-top:14px;border-top:1px solid var(--rule);font-family:'DM Mono',monospace;font-size:9px;color:var(--muted);line-height:1.9}
  .sources strong{font-weight:500;text-transform:uppercase;letter-spacing:.1em;font-size:8.5px}
  .article-cta{margin-top:40px;background:var(--paper-2);border:1px solid var(--rule);border-top:2px solid var(--ink);padding:24px 26px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
  .article-cta-text{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
  .article-cta-headline{font-family:'Playfair Display',Georgia,serif;font-size:17px;font-weight:700;color:var(--ink);margin-top:4px}
  .btn-cta{display:inline-block;font-family:'DM Mono',monospace;font-size:9.5px;letter-spacing:.2em;text-transform:uppercase;text-decoration:none;padding:12px 24px;background:var(--ink);color:var(--paper);border:1.5px solid var(--ink);white-space:nowrap;transition:background .15s}
  .btn-cta:hover{background:#1a2f45}
"""

# CSS for lighter update pages (morning/midday/afterhours/breaking)
UPDATE_CSS = """
  :root{--ink:#0d1b2a;--paper:#f7f4ef;--paper-2:#ede9df;--rule:#d4cfc4;--red:#b52020;--gold:#a07820;--gold-bg:#faf4e2;--green:#1a6840;--green-bg:#edf7f1;--muted:#7a7268;--muted-2:#a09a90}
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Source Serif 4',Georgia,serif;background:var(--paper);color:var(--ink);font-size:16px;line-height:1.75;-webkit-font-smoothing:antialiased}
  .brief-nav{background:var(--ink);display:flex;align-items:center;justify-content:space-between;padding:0 28px;border-bottom:1px solid rgba(255,255,255,0.07);position:sticky;top:0;z-index:100}
  .brief-nav-brand{font-family:'Playfair Display',Georgia,serif;font-size:18px;font-weight:900;letter-spacing:-.015em;color:#f7f4ef;text-decoration:none;padding:14px 0}
  .brief-nav-links{display:flex;align-items:center}
  .brief-nav-links a{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.2em;text-transform:uppercase;color:rgba(247,244,239,0.5);text-decoration:none;padding:10px 14px;transition:color .15s}
  .brief-nav-links a:hover{color:#f7f4ef}
  .brief-nav-links .nav-cta{color:#f7f4ef !important;border:1px solid rgba(247,244,239,0.28);padding:8px 16px;margin-left:6px}
  .update-header{padding:22px 22px 18px;max-width:680px;margin:0 auto;border-bottom:2px solid var(--ink)}
  .update-type-badge{display:inline-block;font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.22em;text-transform:uppercase;padding:4px 10px;margin-bottom:10px}
  .badge-morning{background:#e8f4fd;color:#1a5276;border:1px solid #aed6f1}
  .badge-midday{background:#fef9e7;color:#7d6608;border:1px solid #f9e79f}
  .badge-close{background:var(--ink);color:var(--paper);border:1px solid var(--ink)}
  .badge-afterhours{background:#f4ecf7;color:#6c3483;border:1px solid #d2b4de}
  .badge-breaking{background:#fdedec;color:var(--red);border:1px solid #f1948a;animation:badge-pulse 2s ease-in-out infinite}
  @keyframes badge-pulse{0%,100%{opacity:1}50%{opacity:.7}}
  .update-time{font-family:'DM Mono',monospace;font-size:9px;color:var(--muted-2);margin-bottom:8px}
  .update-headline{font-family:'Playfair Display',Georgia,serif;font-size:clamp(22px,4vw,30px);font-weight:900;line-height:1.12;letter-spacing:-.018em;color:var(--ink);margin-bottom:12px}
  .update-summary{font-size:15px;line-height:1.80;color:#2a2a22;border-left:3px solid var(--ink);padding-left:14px}
  .wrap{max-width:680px;margin:0 auto;padding:0 22px 60px}
  .market-snapshot{border:1px solid var(--rule);border-top:2px solid var(--ink);background:var(--paper-2);margin:20px 0 8px}
  .market-snapshot-header{display:flex;justify-content:space-between;align-items:center;padding:10px 16px 0}
  .market-snapshot-label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.22em;text-transform:uppercase;color:var(--muted)}
  .market-snapshot-time{font-family:'DM Mono',monospace;font-size:8px;color:var(--muted-2)}
  .market-snapshot-grid{display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid var(--rule);margin-top:8px}
  @media(max-width:420px){.market-snapshot-grid{grid-template-columns:repeat(2,1fr)}}
  .snapshot-cell{padding:10px 12px;border-right:1px solid var(--rule);border-bottom:1px solid var(--rule)}
  .snapshot-cell:nth-child(3n){border-right:none}
  .snapshot-cell:nth-last-child(-n+3){border-bottom:none}
  .snapshot-label{font-family:'DM Mono',monospace;font-size:8px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted-2);margin-bottom:3px}
  .snapshot-value{font-family:'DM Mono',monospace;font-size:15px;font-weight:500;color:var(--ink);margin-bottom:2px;line-height:1}
  .snapshot-change{font-family:'DM Mono',monospace;font-size:10px;font-weight:500}
  .snapshot-change.up{color:var(--green)}.snapshot-change.down{color:var(--red)}.snapshot-change.flat{color:var(--muted)}
  .section-block{margin-top:28px;padding-top:18px;border-top:1px solid var(--rule)}
  .section-label{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:.22em;text-transform:uppercase;color:var(--muted);margin-bottom:10px}
  .key-points{list-style:none;padding:0;margin:0}
  .key-points li{font-size:15px;line-height:1.72;padding:10px 0 10px 20px;border-bottom:1px solid var(--rule);position:relative}
  .key-points li::before{content:'→';position:absolute;left:0;color:var(--red);font-family:'DM Mono',monospace;font-size:11px;top:12px}
  .key-points li:last-child{border-bottom:none}
  .watch-box{background:var(--gold-bg);border:1px solid rgba(160,120,32,0.3);border-left:3px solid var(--gold);padding:14px 16px;margin-top:4px}
  .watch-label{font-family:'DM Mono',monospace;font-size:8.5px;letter-spacing:.18em;text-transform:uppercase;color:var(--gold);margin-bottom:7px}
  .watch-box p{font-size:13.5px;line-height:1.68;margin-bottom:8px;color:#5a3f00}
  .watch-box p:last-child{margin-bottom:0}
  .breaking-impact{background:var(--ink);color:var(--paper);padding:18px 20px;margin-top:20px}
  .breaking-impact-label{font-family:'DM Mono',monospace;font-size:8.5px;letter-spacing:.2em;text-transform:uppercase;color:rgba(247,244,239,0.45);margin-bottom:10px}
  .breaking-impact p{font-size:14px;line-height:1.72;margin-bottom:8px;color:rgba(247,244,239,0.88)}
  .breaking-impact p:last-child{margin-bottom:0}
  .disclaimer{margin-top:28px;padding-top:14px;border-top:1px solid var(--rule);font-family:'DM Mono',monospace;font-size:8.5px;color:var(--muted-2);line-height:1.8}
  .update-cta{margin-top:32px;display:flex;gap:10px;flex-wrap:wrap}
  .btn-dark{display:inline-block;font-family:'DM Mono',monospace;font-size:9.5px;letter-spacing:.18em;text-transform:uppercase;text-decoration:none;padding:11px 22px;background:var(--ink);color:var(--paper);border:1.5px solid var(--ink);white-space:nowrap}
  .btn-outline{display:inline-block;font-family:'DM Mono',monospace;font-size:9.5px;letter-spacing:.18em;text-transform:uppercase;text-decoration:none;padding:11px 22px;border:1.5px solid var(--rule);color:var(--muted);white-space:nowrap}
  p{margin-bottom:12px}p:last-child{margin-bottom:0}
  a{color:var(--red)}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Timezone helpers
# ─────────────────────────────────────────────────────────────────────────────

def now_et() -> datetime:
    return datetime.now(ET)


def determine_update_type():
    """
    Check the current America/New_York time and return the appropriate
    update type, or None if no update is scheduled right now.

    Windows (ET):
        morning:    07:30 – 09:00
        midday:     11:30 – 13:00
        close:      15:45 – 17:15
        afterhours: 18:00 – 19:30
    """
    et = now_et()
    h, m = et.hour, et.minute
    total = h * 60 + m  # minutes since midnight ET

    if 7 * 60 + 30 <= total < 9 * 60:
        return "morning"
    if 11 * 60 + 30 <= total < 13 * 60:
        return "midday"
    if 15 * 60 + 45 <= total < 17 * 60 + 15:
        return "close"
    if 18 * 60 <= total < 19 * 60 + 30:
        return "afterhours"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# HTML helpers (shared with existing code)
# ─────────────────────────────────────────────────────────────────────────────

def render_feature_image(data: dict) -> str:
    url        = data.get("feature_image_url", "").strip()
    alt        = data.get("feature_image_alt", "")
    caption    = data.get("feature_image_caption", "").strip()
    credit     = data.get("feature_image_credit", "").strip()
    source_url = data.get("feature_image_source_url", "").strip()
    img_type   = data.get("feature_image_type", "none")

    if not url or img_type == "none":
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


def render_market_snapshot(snapshot: list, time_label: str = "At Close") -> str:
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
        f'<span class="market-snapshot-time">{time_label}</span>'
        '</div>\n'
        f'  <div class="market-snapshot-grid">\n{cells}  </div>\n'
        '</div>\n'
    )


# ─────────────────────────────────────────────────────────────────────────────
# API call
# ─────────────────────────────────────────────────────────────────────────────

def call_api(system_prompt: str, user_message: str, max_tokens: int = 8000) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    print(f"Calling Anthropic API (claude-sonnet-4-6)...")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=system_prompt,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 12}],
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
        print(f"ERROR: API returned no text content. Stop reason: {response.stop_reason}")
        sys.exit(1)

    print(f"Received {len(text_content)} chars from API.")
    return text_content


def save_raw(raw: str) -> None:
    RAW_RESPONSE_FILE.write_text(raw, encoding="utf-8")
    print(f"Raw response saved to: {RAW_RESPONSE_FILE}")


def extract_json(raw: str) -> dict:
    """
    Robustly extract the first valid JSON object from a Claude response.

    Claude sometimes prepends prose ("Based on my research…") before the JSON
    even when told not to. We try four strategies in order and log each attempt.

    Strategy 1 — whole string is valid JSON.
    Strategy 2 — strip a single markdown code fence, then try.
    Strategy 3 — slice from the FIRST '{' to the LAST '}' (handles trailing prose).
    Strategy 4 — walk character-by-character to find the first balanced '{…}'.
    """
    print(f"[parser] Response preview (first 500 chars): {raw[:500]!r}")

    # ── Strategy 1: whole string ──────────────────────────────────────────────
    try:
        result = json.loads(raw.strip())
        print("[parser] Strategy 1 (raw): SUCCESS")
        return result
    except json.JSONDecodeError:
        print("[parser] Strategy 1 (raw): failed")

    # ── Strategy 2: strip markdown fences ────────────────────────────────────
    stripped = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
    stripped = re.sub(r"\n?```\s*$", "", stripped)
    try:
        result = json.loads(stripped.strip())
        print("[parser] Strategy 2 (strip fences): SUCCESS")
        return result
    except json.JSONDecodeError:
        print("[parser] Strategy 2 (strip fences): failed")

    # ── Strategy 3: first '{' to last '}' ────────────────────────────────────
    # Handles prose prepended OR appended to the JSON blob.
    first_brace = raw.find("{")
    last_brace  = raw.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidate = raw[first_brace:last_brace + 1]
        try:
            result = json.loads(candidate)
            print("[parser] Strategy 3 (first-to-last brace): SUCCESS")
            return result
        except json.JSONDecodeError:
            print("[parser] Strategy 3 (first-to-last brace): failed")

    # ── Strategy 4: balanced bracket walk ────────────────────────────────────
    # Handles cases where there is valid JSON followed by more JSON/text.
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
                            result = json.loads(raw[start:i + 1])
                            print("[parser] Strategy 4 (bracket walk): SUCCESS")
                            return result
                        except json.JSONDecodeError:
                            break
        print("[parser] Strategy 4 (bracket walk): failed")

    # ── All strategies failed ─────────────────────────────────────────────────
    save_raw(raw)
    print("ERROR: Could not parse JSON from Claude response after 4 strategies.")
    print(f"       Response length: {len(raw)} chars")
    print(f"       First 500 chars: {raw[:500]}")
    sys.exit(1)


def _test_parser() -> None:
    """Quick local smoke-test — run with: python scripts/generate_brief.py --test-parser"""
    cases = [
        # Case 1: clean JSON
        ('{"publish": true, "a": 1}', True),
        # Case 2: prose before JSON
        ('I now have sufficient data. Here is the result:\n{"publish": true, "a": 2}', True),
        # Case 3: prose after JSON
        ('{"publish": true, "a": 3}\n\nPlease let me know if you need anything else.', True),
        # Case 4: markdown fences
        ('```json\n{"publish": true, "a": 4}\n```', True),
        # Case 5: prose both sides
        ('Based on my research...\n{"publish": false}\nHope that helps!', True),
        # Case 6: no JSON at all
        ('This is just prose, no JSON here.', False),
    ]
    all_passed = True
    for i, (text, should_succeed) in enumerate(cases, 1):
        try:
            result = extract_json(text)
            if should_succeed:
                print(f"  Case {i}: PASS — parsed key 'publish'={result.get('publish')}")
            else:
                print(f"  Case {i}: FAIL — expected failure but got: {result}")
                all_passed = False
        except SystemExit:
            if not should_succeed:
                print(f"  Case {i}: PASS — correctly rejected non-JSON input")
            else:
                print(f"  Case {i}: FAIL — unexpected parse failure")
                all_passed = False
    print("All parser tests passed." if all_passed else "Some parser tests FAILED.")


# ─────────────────────────────────────────────────────────────────────────────
# Image safety (existing logic, unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def _clear_image(data: dict, reason: str) -> None:
    print(f"WARNING: {reason}. Falling back to no image.")
    data["feature_image_url"] = ""
    data["feature_image_alt"] = ""
    data["feature_image_caption"] = ""
    data["feature_image_credit"] = ""
    data["feature_image_source_url"] = ""
    data["feature_image_type"] = "none"


def validate_image(data: dict) -> None:
    img_type = data.get("feature_image_type", "")
    url = data.get("feature_image_url", "").strip()

    if img_type not in SAFE_IMAGE_TYPES:
        _clear_image(data, f"Unknown feature_image_type '{img_type}'")
        return

    if not url:
        return

    for domain in BLOCKED_IMAGE_DOMAINS:
        if domain in url:
            _clear_image(data, f"Image URL from blocked domain '{domain}'")
            return

    credit = data.get("feature_image_credit", "").strip()
    source_url = data.get("feature_image_source_url", "").strip()

    if not credit:
        _clear_image(data, "feature_image_url set but feature_image_credit is missing")
    elif not source_url:
        _clear_image(data, "feature_image_url set but feature_image_source_url is missing")


# ─────────────────────────────────────────────────────────────────────────────
# CLOSE (full daily brief) — identical to existing behavior
# ─────────────────────────────────────────────────────────────────────────────

def validate_close(data: dict) -> None:
    if "error" in data:
        print(f"ERROR: Claude reported a failure: {data['error']}")
        sys.exit(1)

    IMAGE_OPTIONAL = {
        "feature_image_url", "feature_image_alt", "feature_image_caption",
        "feature_image_credit", "feature_image_source_url",
    }

    def field_missing(f: str) -> bool:
        val = data.get(f)
        if val is None:
            return True
        if f in IMAGE_OPTIONAL:
            return False
        if isinstance(val, str) and not val.strip():
            return True
        return False

    missing = [f for f in CLOSE_REQUIRED_FIELDS if field_missing(f)]
    if missing:
        print(f"ERROR: Response missing required fields: {missing}")
        sys.exit(1)

    validate_image(data)

    snapshot = data.get("market_snapshot", [])
    if not isinstance(snapshot, list) or len(snapshot) < 4:
        print(f"ERROR: market_snapshot must have at least 4 items (got {len(snapshot) if isinstance(snapshot, list) else 'n/a'})")
        sys.exit(1)

    placeholders = {"X,XXX", "XX,XXX", "X.XX", "$XX.XX", "X.X%", ""}
    for item in snapshot:
        if item.get("value", "") in placeholders:
            print(f"ERROR: Placeholder in market_snapshot for '{item.get('label')}': '{item.get('value')}'")
            sys.exit(1)

    if len(data.get("article_html", "")) < 500:
        print(f"ERROR: article_html too short ({len(data.get('article_html',''))} chars).")
        sys.exit(1)

    tags = data.get("tags", [])
    if not isinstance(tags, list) or not tags:
        data["tags"] = ["Rates", "Equities", "Wealth Management"]
    else:
        data["tags"] = [str(t).strip() for t in tags[:3] if str(t).strip()] or ["Rates", "Equities", "Wealth Management"]

    today_iso = date.today().isoformat()
    if data.get("date_iso") != today_iso:
        print(f"WARNING: date_iso overridden to {today_iso}")
        data["date_iso"] = today_iso


def build_close_page(data: dict) -> str:
    date_iso     = data["date_iso"]
    seo_title    = data["seo_title"]
    meta_desc    = data["meta_description"]
    alert_strip  = data["alert_strip"]
    kicker       = data["issue_kicker"]
    headline     = data["headline"]
    opening      = data["opening_summary"]
    article_html = data["article_html"]
    snapshot     = data["market_snapshot"]

    site_url = f"https://readmarketbrief.com/briefs/{date_iso}-close.html"
    share_raw = data["share_text"].replace("{{URL}}", site_url)
    share_encoded = re.sub(r"\s+", "+", share_raw.strip())

    feature_html     = render_feature_image(data)
    market_snap_html = render_market_snapshot(snapshot, "At Close")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{seo_title}</title>
<meta name="description" content="{meta_desc}">
<link rel="canonical" href="{site_url}">
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<link rel="alternate icon" href="../favicon.ico">
<link rel="apple-touch-icon" href="../apple-touch-icon.png">
<link rel="manifest" href="../site.webmanifest">
<meta name="theme-color" content="#0d1b2a">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=DM+Mono:wght@300;400;500&family=Source+Serif+4:ital,opsz,wght@0,8..60,300;0,8..60,400;0,8..60,600;1,8..60,300;1,8..60,400&display=swap" rel="stylesheet">
<style>{BRIEF_CSS}</style>
</head>
<body>
<nav class="brief-nav">
  <a href="../index.html" class="brief-nav-brand">The Brief</a>
  <div class="brief-nav-links">
    <a href="../dashboard.html">Dashboard</a>
    <a href="../archive.html">Archive</a>
    <a href="../subscribe.html" class="nav-cta">Subscribe Free</a>
  </div>
</nav>
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
  <div class="article-cta">
    <div>
      <div class="article-cta-text">Enjoyed this issue?</div>
      <div class="article-cta-headline">Get the next Brief free — every weekday morning.</div>
    </div>
    <a href="../subscribe.html" class="btn-cta">Subscribe Free</a>
  </div>
  <div style="margin-top:20px;display:flex;gap:10px;flex-wrap:wrap">
    <a href="../archive.html" style="flex:1;min-width:140px;display:block;border:1.5px solid var(--ink);color:var(--ink);text-align:center;padding:13px 18px;font-family:'DM Mono',monospace;font-size:9.5px;letter-spacing:.18em;text-transform:uppercase;text-decoration:none">Browse All Issues</a>
    <a href="https://www.linkedin.com/sharing/share-offsite/?url={site_url}" target="_blank" rel="noopener" style="flex:1;min-width:140px;display:block;border:1.5px solid var(--rule);color:var(--muted);text-align:center;padding:13px 18px;font-family:'DM Mono',monospace;font-size:9.5px;letter-spacing:.18em;text-transform:uppercase;text-decoration:none">Share on LinkedIn</a>
  </div>
</div>
</body>
</html>"""


def generate_close(today_iso: str, date_display: str) -> dict:
    if not SYSTEM_PROMPT_FILE.exists():
        print(f"ERROR: System prompt not found at {SYSTEM_PROMPT_FILE}")
        sys.exit(1)

    system_prompt = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    today_fmt = datetime.now(ET).strftime("%A, %B %-d, %Y")

    user_message = (
        f"Today is {today_fmt}. "
        "Use your web_search tool to retrieve today's real market data and news. "
        "Search for: S&P 500 close, Nasdaq close, Dow close, VIX, 10-year Treasury yield, "
        "WTI crude, top movers, major earnings, Fed news, and the 2-3 biggest market stories today. "
        "Also search for a suitable editorial image. "
        "Then produce a complete close-of-day issue of The Brief. "
        "CRITICAL OUTPUT RULE: Your response must be ONLY the JSON object. "
        "Start your response with { and end with }. "
        "No prose before the JSON. No explanation after the JSON. "
        "No markdown. No ```json fences. No commentary. "
        "If data is unavailable use null, not explanatory text."
    )

    raw  = call_api(system_prompt, user_message, max_tokens=16000)
    data = extract_json(raw)
    validate_close(data)
    data["date_iso"]     = today_iso
    data["date_display"] = date_display
    return data


# ─────────────────────────────────────────────────────────────────────────────
# MORNING / MIDDAY / AFTERHOURS — lighter format
# ─────────────────────────────────────────────────────────────────────────────

def build_update_page(data: dict, update_type: str) -> str:
    date_iso    = data["date_iso"]
    headline    = data["headline"]
    summary     = data["summary"]
    snapshot    = data.get("market_snapshot", [])
    key_points  = data.get("key_points", [])
    what_to_watch = data.get("what_to_watch", "")
    site_url    = f"https://readmarketbrief.com/briefs/{date_iso}-{update_type}.html"

    badge_class = TYPE_BADGE_CSS.get(update_type, "badge-close")
    type_label  = TYPE_LABELS.get(update_type, update_type.title())

    et_now = now_et()
    time_str = et_now.strftime("%-I:%M %p ET")

    snap_time = {
        "morning": "Pre-Market",
        "midday":  "Midday",
        "afterhours": "After Hours",
    }.get(update_type, "Current")

    snap_html = render_market_snapshot(snapshot, snap_time) if snapshot else ""

    key_points_html = ""
    if key_points:
        items_html = "\n".join(f"  <li>{pt}</li>" for pt in key_points)
        key_points_html = (
            '<div class="section-block">\n'
            '  <div class="section-label">Key Points</div>\n'
            f'  <ul class="key-points">\n{items_html}\n  </ul>\n'
            '</div>\n'
        )

    watch_html = ""
    if what_to_watch:
        if isinstance(what_to_watch, list):
            items = "\n".join(f"  <p>→ {w}</p>" for w in what_to_watch)
            watch_html = (
                '<div class="section-block">\n'
                '  <div class="watch-box">\n'
                '    <div class="watch-label">What to Watch</div>\n'
                f'{items}\n'
                '  </div>\n'
                '</div>\n'
            )
        else:
            watch_html = (
                '<div class="section-block">\n'
                '  <div class="watch-box">\n'
                '    <div class="watch-label">What to Watch</div>\n'
                f'  <p>{what_to_watch}</p>\n'
                '  </div>\n'
                '</div>\n'
            )

    close_link = f'briefs/{date_iso}-close.html'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{headline} — The Brief</title>
<meta name="description" content="{data.get('archive_teaser', summary)[:160]}">
<link rel="canonical" href="{site_url}">
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<link rel="alternate icon" href="../favicon.ico">
<link rel="apple-touch-icon" href="../apple-touch-icon.png">
<link rel="manifest" href="../site.webmanifest">
<meta name="theme-color" content="#0d1b2a">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=DM+Mono:wght@300;400;500&family=Source+Serif+4:ital,opsz,wght@0,8..60,300;0,8..60,400;0,8..60,600;1,8..60,300&display=swap" rel="stylesheet">
<style>{UPDATE_CSS}</style>
</head>
<body>
<nav class="brief-nav">
  <a href="../index.html" class="brief-nav-brand">The Brief</a>
  <div class="brief-nav-links">
    <a href="../dashboard.html">Dashboard</a>
    <a href="../archive.html">Archive</a>
    <a href="../subscribe.html" class="nav-cta">Subscribe Free</a>
  </div>
</nav>

<div class="update-header">
  <span class="update-type-badge {badge_class}">{type_label}</span>
  <div class="update-time">{data.get('date_display', date_iso)} &nbsp;·&nbsp; {time_str}</div>
  <h1 class="update-headline">{headline}</h1>
  <p class="update-summary">{summary}</p>
</div>

<div class="wrap">
{snap_html}
{key_points_html}
{watch_html}

  <div class="disclaimer">
    Market data may be delayed &nbsp;·&nbsp;
    For informational and educational purposes only. Not investment advice.
  </div>

  <div class="update-cta">
    <a href="../{close_link}" class="btn-dark">Full Close Recap →</a>
    <a href="../archive.html" class="btn-outline">All Issues</a>
    <a href="../subscribe.html" class="btn-outline">Subscribe Free</a>
  </div>
</div>
</body>
</html>"""


def generate_scheduled_update(update_type: str, today_iso: str, date_display: str) -> dict:
    """
    Generate a MORNING or MIDDAY update. These always publish — no conditional logic.
    The workflow runs them on a fixed schedule and they always produce a file.
    """
    assert update_type in ("morning", "midday"), f"generate_scheduled_update called with {update_type}"

    et_now    = now_et()
    today_fmt = et_now.strftime("%A, %B %-d, %Y")
    time_fmt  = et_now.strftime("%-I:%M %p ET")

    type_context = {
        "morning": (
            "This is the MORNING PRE-MARKET brief, published at 8 AM ET before market open. "
            "Always publish — this runs every weekday morning regardless of market conditions. "
            "Cover: overnight macro/geopolitical developments, US futures direction, "
            "global markets (Europe/Asia overnight), rates, oil, crypto, pre-market movers, "
            "and 3-5 key things to watch today. Concise — a quick read before open."
        ),
        "midday": (
            "This is the MIDDAY UPDATE, published at 12 PM ET during the trading session. "
            "Always publish — this runs every weekday at noon. "
            "Cover: how US markets are performing mid-session, biggest movers so far, "
            "key headlines affecting the tape, sector performance, what to watch into the close. "
            "Concise and focused — no filler."
        ),
    }[update_type]

    system_prompt = f"""You are the writer of "The Brief" — a market intelligence newsletter for finance students and early-career professionals.

{type_context}

RULES:
- Use web_search to get real, current market data and news. Do not fabricate numbers.
- If specific data is unavailable, write "unavailable" — never use placeholder values.
- Write in a confident, direct, engaging voice. Not boring. Not textbook.
- Always include: "For informational and educational purposes only. Not investment advice."
- Use wording like "latest available market data" and "market data may be delayed."

OUTPUT FORMAT — STRICTLY ENFORCED:
Your ENTIRE response must be one valid JSON object. Begin with {{ and end with }}.
No prose before the JSON. No explanation after the JSON.
No markdown. No ```json fences. No "Here is the JSON:" prefix.
If a value is unavailable, use null — never a placeholder string.

Return ONLY this JSON object:
{{
  "date_iso": "{today_iso}",
  "date_display": "{date_display}",
  "headline": "Concise, punchy headline",
  "summary": "2-3 sentence opening summary",
  "market_snapshot": [
    {{"label": "S&P 500",   "value": "5,432",   "change": "+0.45%", "direction": "up"}},
    {{"label": "Nasdaq",    "value": "17,234",  "change": "-0.12%", "direction": "down"}},
    {{"label": "10Y Yield", "value": "4.32%",   "change": "+3 bps", "direction": "up"}},
    {{"label": "WTI Crude", "value": "$82.45",  "change": "+0.8%",  "direction": "up"}},
    {{"label": "VIX",       "value": "14.2",    "change": "-0.5",   "direction": "down"}},
    {{"label": "Bitcoin",   "value": "$67,450", "change": "+1.2%",  "direction": "up"}}
  ],
  "key_points": ["Point 1", "Point 2", "Point 3", "Point 4"],
  "what_to_watch": ["Watch item 1", "Watch item 2", "Watch item 3"],
  "archive_teaser": "One sentence for the archive listing.",
  "homepage_teaser": "One sentence teaser for the homepage card."
}}"""

    user_message = (
        f"Today is {today_fmt}. Current time: {time_fmt}. "
        "Search for current market data and the biggest stories. "
        "CRITICAL OUTPUT RULE: Respond with ONLY the JSON object. "
        "Your response must begin with { and end with }. "
        "No prose, no explanation, no markdown, no ```json fences. "
        "If a value is unavailable, use null — not a string like 'unavailable'."
    )

    raw  = call_api(system_prompt, user_message, max_tokens=6000)
    data = extract_json(raw)

    missing = [f for f in UPDATE_REQUIRED_FIELDS if f not in ("publish",) and
               (f not in data or (isinstance(data[f], str) and not data[f].strip()))]
    if missing:
        print(f"WARNING: Missing fields in {update_type} response: {missing}")

    data["date_iso"]     = today_iso
    data["date_display"] = date_display
    return data


def generate_afterhours(today_iso: str, date_display: str):
    """
    Conditional after-hours check. Runs at 6:30 PM ET but only publishes if there
    is genuinely meaningful after-hours market-moving news. Returns None to skip.

    Publish threshold — at least ONE of the following must be true:
    - Major earnings release with significant guidance, beat/miss, or after-hours move > 3%
      from an S&P 500 company
    - A meaningful Fed, Treasury, or macro development after market close
    - A significant geopolitical event with direct and immediate market impact
    - A major M&A announcement, bankruptcy filing, or regulatory action involving a large company
    - A large move in oil, gold, crypto, or rates (>2%) driven by a specific post-close catalyst

    Do NOT publish for:
    - A quiet after-hours session with no significant news
    - Routine small earnings beats/misses from mid/small-cap companies
    - General recap of the day's close (that belongs in the close brief)
    - Vague or speculative news without confirmed market impact
    """
    et_now    = now_et()
    today_fmt = et_now.strftime("%A, %B %-d, %Y")
    time_fmt  = et_now.strftime("%-I:%M %p ET")

    system_prompt = f"""You are the editor of "The Brief" — a finance newsletter for students and early-career professionals.

Your task at 6:30 PM ET: check whether there is meaningful after-hours market-moving news that warrants publishing an after-hours update.

PUBLISH ONLY IF at least one of these conditions is met:
1. A major S&P 500 company reported earnings with a significant beat/miss, major guidance change, or after-hours stock move > 3%
2. A Fed, Treasury, or central bank development occurred after market close (statement, emergency action, major official speech)
3. A geopolitical event with direct and immediate market impact (conflict escalation, major sanctions, trade deal/breakdown)
4. A major M&A announcement, large-scale bankruptcy filing, or significant regulatory action (antitrust, SEC/DOJ enforcement)
5. A large move in oil, gold, crypto, or rates (>2%) driven by a specific confirmed post-close catalyst

DO NOT PUBLISH IF:
- The after-hours session is quiet with no news meeting the above criteria
- Only routine mid/small-cap earnings with no major surprise
- Nothing beyond what was already covered in the close brief
- The "news" is vague, speculative, or unconfirmed

Use web_search to check for after-hours earnings and news right now.

If no meaningful news meets the publish criteria, return ONLY:
{{"publish": false}}

If meaningful news exists, return ONLY a valid JSON object:
{{
  "publish": true,
  "date_iso": "{today_iso}",
  "date_display": "{date_display}",
  "headline": "Concise headline describing the after-hours development",
  "summary": "2-3 sentences on what happened and why it matters",
  "market_snapshot": [
    {{"label": "S&P 500 Futures", "value": "5,432", "change": "+0.2%", "direction": "up"}},
    {{"label": "Nasdaq Futures",  "value": "17,234", "change": "-0.1%", "direction": "down"}},
    {{"label": "10Y Yield",       "value": "4.32%",  "change": "flat",  "direction": "flat"}},
    {{"label": "Bitcoin",         "value": "$67,450", "change": "+1.2%", "direction": "up"}}
  ],
  "key_points": ["Specific point about what moved", "Why it matters", "What to watch tomorrow"],
  "what_to_watch": ["Tomorrow catalyst 1", "Tomorrow catalyst 2"],
  "archive_teaser": "One sentence for the archive.",
  "homepage_teaser": "One sentence teaser for the homepage."
}}

OUTPUT FORMAT — STRICTLY ENFORCED:
Your ENTIRE response must be one valid JSON object. Begin with {{ and end with }}.
No prose before the JSON. No explanation after the JSON. No markdown. No ```json fences.
If nothing meets the publish criteria, return exactly: {{"publish": false}}"""

    user_message = (
        f"Today is {today_fmt}. Current time: {time_fmt}. "
        "Check for meaningful after-hours earnings and market news right now. "
        "Apply the publish criteria strictly. "
        "CRITICAL OUTPUT RULE: Respond with ONLY the JSON object. "
        "Your response must begin with { and end with }. "
        "No prose, no explanation, no markdown, no ```json fences. "
        "If nothing qualifies, return exactly: {\"publish\": false}"
    )

    raw  = call_api(system_prompt, user_message, max_tokens=4000)
    data = extract_json(raw)

    if not data.get("publish", True):
        print("After-hours check: no meaningful news meets publish criteria. Exiting cleanly.")
        return None

    print("After-hours check: meaningful news found — publishing.")

    missing = [f for f in UPDATE_REQUIRED_FIELDS if f not in ("publish",) and
               (f not in data or (isinstance(data[f], str) and not data[f].strip()))]
    if missing:
        print(f"WARNING: Missing fields in afterhours response: {missing}")

    data["date_iso"]     = today_iso
    data["date_display"] = date_display
    return data


# ─────────────────────────────────────────────────────────────────────────────
# BREAKING NEWS
# ─────────────────────────────────────────────────────────────────────────────

def build_breaking_page(data: dict) -> str:
    date_iso      = data["date_iso"]
    headline      = data["headline"]
    slug          = data["slug"]
    summary       = data["summary"]
    why_matters   = data["why_it_matters"]
    market_impact = data.get("market_impact", "")
    time_str      = data.get("time_et", now_et().strftime("%-I:%M %p ET"))
    date_display  = data.get("date_display", date_iso)

    et_now = now_et()
    file_time = et_now.strftime("%H%M")
    site_url = f"https://readmarketbrief.com/breaking/{date_iso}-{file_time}-{slug}.html"

    impact_html = ""
    if market_impact:
        impact_html = (
            '<div class="breaking-impact">\n'
            '  <div class="breaking-impact-label">Market Impact</div>\n'
            f'  <p>{market_impact}</p>\n'
            '</div>\n'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BREAKING: {headline} — The Brief</title>
<meta name="description" content="{summary[:160]}">
<link rel="canonical" href="{site_url}">
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<link rel="alternate icon" href="../favicon.ico">
<link rel="apple-touch-icon" href="../apple-touch-icon.png">
<link rel="manifest" href="../site.webmanifest">
<meta name="theme-color" content="#0d1b2a">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=DM+Mono:wght@300;400;500&family=Source+Serif+4:ital,opsz,wght@0,8..60,300;0,8..60,400;0,8..60,600&display=swap" rel="stylesheet">
<style>{UPDATE_CSS}</style>
</head>
<body>
<nav class="brief-nav">
  <a href="../index.html" class="brief-nav-brand">The Brief</a>
  <div class="brief-nav-links">
    <a href="../dashboard.html">Dashboard</a>
    <a href="../archive.html">Archive</a>
    <a href="../subscribe.html" class="nav-cta">Subscribe Free</a>
  </div>
</nav>

<div class="update-header">
  <span class="update-type-badge badge-breaking">⚡ Breaking</span>
  <div class="update-time">{date_display} &nbsp;·&nbsp; {time_str}</div>
  <h1 class="update-headline">{headline}</h1>
  <p class="update-summary">{summary}</p>
</div>

<div class="wrap">
  <div class="section-block">
    <div class="section-label">Why It Matters</div>
    <p>{why_matters}</p>
  </div>
{impact_html}
  <div class="disclaimer">
    Market data may be delayed &nbsp;·&nbsp;
    For informational and educational purposes only. Not investment advice.
  </div>
  <div class="update-cta">
    <a href="../archive.html" class="btn-dark">Full Archive</a>
    <a href="../subscribe.html" class="btn-outline">Subscribe Free</a>
  </div>
</div>
</body>
</html>"""


def generate_breaking(today_iso: str, date_display: str):
    et_now    = now_et()
    today_fmt = et_now.strftime("%A, %B %-d, %Y")
    time_fmt  = et_now.strftime("%-I:%M %p ET")

    system_prompt = """You are the editor of "The Brief" — a finance newsletter for students and early-career professionals.

Your task: determine if there is GENUINELY MAJOR market-moving news right now that warrants a breaking alert.

Breaking-worthy events ONLY:
- Fed emergency decision or highly unexpected FOMC action
- CPI/jobs data shock (major deviation from expectations)
- S&P 500 move > 2% intraday
- Major geopolitical escalation with direct market impact
- Bank failure or financial crisis development
- Massive earnings surprise from top-5 market cap company
- Major regulatory action (antitrust, SEC enforcement on large scale)
- Significant M&A, bankruptcy, or major corporate event from S&P 500 constituent

NOT breaking-worthy:
- Normal market moves
- Routine earnings results
- Expected Fed decisions
- Standard economic data within expectations
- General news without immediate market impact

Search for current news. If nothing genuinely breaking, return {"publish": false}.

If breaking news exists, return:
{
  "publish": true,
  "date_iso": "YYYY-MM-DD",
  "date_display": "Day, Month D, YYYY",
  "headline": "Breaking headline",
  "slug": "short-url-slug",
  "time_et": "H:MM AM/PM ET",
  "summary": "2-3 sentence summary of what happened",
  "why_it_matters": "Why this matters for markets and finance professionals",
  "market_impact": "Specific market impact if known (indices, sectors, specific stocks)"
}"""

    user_message = (
        f"Today is {today_fmt}. Current time: {time_fmt}. "
        "Search for any genuinely major breaking market news right now. "
        "CRITICAL OUTPUT RULE: Respond with ONLY the JSON object. "
        "Your response must begin with { and end with }. "
        "No prose, no explanation, no markdown, no ```json fences. "
        "If nothing qualifies, return exactly: {\"publish\": false}"
    )

    raw  = call_api(system_prompt, user_message, max_tokens=3000)
    data = extract_json(raw)

    if not data.get("publish", True):
        print("No breaking news warranting publication. Exiting cleanly.")
        return None

    for field in BREAKING_REQUIRED_FIELDS:
        if field not in data:
            print(f"ERROR: Breaking response missing field: {field}")
            sys.exit(1)

    data["date_iso"]     = today_iso
    data["date_display"] = date_display
    return data


# ─────────────────────────────────────────────────────────────────────────────
# File writing & site updates
# ─────────────────────────────────────────────────────────────────────────────

def save_linkedin(data: dict, date_iso: str) -> None:
    LINKEDIN_DIR.mkdir(exist_ok=True)
    site_url = f"https://readmarketbrief.com/briefs/{date_iso}-close.html"
    copy = data.get("linkedin_post", "").replace("{{URL}}", site_url)
    if copy.strip():
        out = LINKEDIN_DIR / f"{date_iso}.txt"
        out.write_text(copy, encoding="utf-8")
        print(f"LinkedIn copy saved: {out}")


def update_index_close(data: dict, date_iso: str) -> None:
    """Update homepage with the close/main brief card."""
    content = INDEX_HTML.read_text(encoding="utf-8")

    tags = data.get("tags", ["Rates", "Equities", "Wealth Management"])
    tag_html = "".join(f'<span class="tag">{t}</span>' for t in tags[:3])

    snap = data.get("market_snapshot", [])[:3]
    mini_rows = ""
    for item in snap:
        direction = item.get("direction", "flat")
        arrow = "▲" if direction == "up" else ("▼" if direction == "down" else "—")
        mini_rows += (
            f'        <div class="mini-cell">'
            f'<div class="mini-label">{item["label"]}</div>'
            f'<div class="mini-value">{item["value"]}</div>'
            f'<div class="mini-change {direction}">{arrow} {item["change"]}</div>'
            f'</div>\n'
        )
    mini_html = f'      <div class="mini-snapshot">\n{mini_rows}      </div>\n' if mini_rows else ""

    brief_path = f"briefs/{date_iso}-close.html"

    new_block = (
        "    <!-- LATEST_BRIEF_START -->\n"
        "    <div class=\"latest-card\">\n"
        "      <div class=\"latest-card-header\">\n"
        "        <span class=\"latest-label\">Today's Brief</span>\n"
        f"        <span class=\"latest-date\">{data['date_display']}</span>\n"
        "      </div>\n"
        "      <div class=\"latest-card-body\">\n"
        f"        <div class=\"latest-title\">{data['headline']}</div>\n"
        f"        <p class=\"latest-teaser\">{data.get('homepage_teaser','')}</p>\n"
        f"        <div class=\"tag-row\">{tag_html}</div>\n"
        "      </div>\n"
        f"{mini_html}"
        "      <div class=\"latest-card-footer\">\n"
        f"        <a href=\"{brief_path}\" class=\"btn btn-dark\">Read Full Issue &rarr;</a>\n"
        "      </div>\n"
        "    </div>\n"
        "    <!-- LATEST_BRIEF_END -->"
    )

    # Also update the hero button
    updated = re.sub(
        r'href="briefs/[\d\-]+(?:-close)?\.html"(\s+class="btn btn-outline-white">Read Today\'s Brief)',
        f'href="{brief_path}"\\1',
        content,
    )

    updated = re.sub(
        r"<!-- LATEST_BRIEF_START -->.*?<!-- LATEST_BRIEF_END -->",
        lambda _: new_block,
        updated,
        flags=re.DOTALL,
    )

    if updated == content:
        print("WARNING: LATEST_BRIEF markers not found in index.html.")
    else:
        INDEX_HTML.write_text(updated, encoding="utf-8")
        print("index.html updated (close).")


def update_index_morning(data: dict, date_iso: str) -> None:
    """Update homepage hero link to the morning brief."""
    content = INDEX_HTML.read_text(encoding="utf-8")
    brief_path = f"briefs/{date_iso}-morning.html"
    updated = re.sub(
        r'href="briefs/[\d\-]+(?:-\w+)?\.html"(\s+class="btn btn-outline-white">Read Today\'s Brief)',
        f'href="{brief_path}"\\1',
        content,
    )
    if updated != content:
        INDEX_HTML.write_text(updated, encoding="utf-8")
        print("index.html hero updated (morning).")


def update_index_breaking(data: dict, date_iso: str, filename: str) -> None:
    """Add/update breaking news banner in index.html."""
    content = INDEX_HTML.read_text(encoding="utf-8")
    breaking_url = f"breaking/{filename}"
    headline = data["headline"]

    banner = (
        "<!-- BREAKING_BANNER_START -->\n"
        "<div style=\"background:#b52020;color:#fff;padding:10px 20px;text-align:center;"
        "font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.14em;"
        "text-transform:uppercase;display:flex;align-items:center;justify-content:center;"
        "gap:12px;flex-wrap:wrap\">\n"
        "  <span style=\"animation:blink 1.2s ease-in-out infinite;display:inline-block\">"
        "&#9889; BREAKING</span>\n"
        f"  <a href=\"{breaking_url}\" style=\"color:#fff;text-decoration:underline;"
        f"font-size:11px;letter-spacing:.04em;text-transform:none\">{headline}</a>\n"
        "</div>\n"
        "<!-- BREAKING_BANNER_END -->"
    )

    if "<!-- BREAKING_BANNER_START -->" in content:
        updated = re.sub(
            r"<!-- BREAKING_BANNER_START -->.*?<!-- BREAKING_BANNER_END -->",
            banner,
            content,
            flags=re.DOTALL,
        )
    else:
        # Inject after <body> tag
        updated = content.replace("<body>", f"<body>\n{banner}", 1)

    if updated != content:
        INDEX_HTML.write_text(updated, encoding="utf-8")
        print("index.html updated (breaking banner).")


def update_archive(data: dict, date_iso: str, update_type: str, url_path: str) -> None:
    content = ARCHIVE_HTML.read_text(encoding="utf-8")
    parts = date_iso.split("-")
    month_abbr = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(parts[1])]
    day, year = int(parts[2]), parts[0]

    badge_class = TYPE_BADGE_CSS.get(update_type, "badge-close")
    type_label  = TYPE_LABELS.get(update_type, update_type.title())
    headline    = data.get("headline", "Market Update")
    teaser      = data.get("archive_teaser", data.get("summary", ""))

    badge_html = (
        f'<span style="display:inline-block;font-family:\'DM Mono\',monospace;'
        f'font-size:8px;letter-spacing:.16em;text-transform:uppercase;'
        f'padding:2px 8px;margin-bottom:5px;border-radius:2px;" '
        f'class="{badge_class}">{type_label}</span>'
    )

    new_item = (
        f"\n    <li class=\"archive-item\">\n"
        f"      <div class=\"archive-date\">{month_abbr} {day}<br>{year}</div>\n"
        f"      <div>\n"
        f"        {badge_html}\n"
        f"        <a class=\"archive-title\" href=\"{url_path}\">{headline}</a>\n"
        f"        <p class=\"archive-teaser\">{teaser}</p>\n"
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
        print(f"archive.html updated ({update_type}).")


def update_sitemap(url: str) -> None:
    content = SITEMAP_XML.read_text(encoding="utf-8")
    if url in content:
        return
    new_entry = f"  <url>\n    <loc>{url}</loc>\n  </url>\n"
    updated = content.replace("</urlset>", new_entry + "</urlset>")
    SITEMAP_XML.write_text(updated, encoding="utf-8")
    print(f"sitemap.xml updated: {url}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="The Brief — market update generator")
    parser.add_argument(
        "--test-parser",
        action="store_true",
        help="Run JSON parser smoke-tests and exit.",
    )
    parser.add_argument(
        "--type",
        choices=UPDATE_TYPES,
        default="auto",
        help="Update type to generate (default: auto)",
    )
    args = parser.parse_args()

    if args.test_parser:
        print("=== JSON Parser Smoke Tests ===")
        _test_parser()
        sys.exit(0)

    update_type = args.type

    et_now = now_et()
    today_iso    = et_now.strftime("%Y-%m-%d")
    date_display = et_now.strftime("%A, %B %-d, %Y")

    print(f"=== The Brief — {update_type.upper()} Generator ===")
    print(f"Eastern Time: {et_now.strftime('%Y-%m-%d %H:%M %Z')}")

    # Auto-detect update type from ET schedule
    if update_type == "auto":
        detected = determine_update_type()
        if detected is None:
            print(f"No update scheduled at {et_now.strftime('%H:%M ET')}. Exiting cleanly.")
            sys.exit(0)
        update_type = detected
        print(f"Auto-detected update type: {update_type}")

    BRIEFS_DIR.mkdir(exist_ok=True)
    BREAKING_DIR.mkdir(exist_ok=True)

    # ── Close (full daily brief) ──────────────────────────────────────────────
    if update_type == "close":
        data = generate_close(today_iso, date_display)
        filename = f"{today_iso}-close.html"
        out_path = BRIEFS_DIR / filename
        if out_path.exists():
            print(f"WARNING: {out_path} already exists. Overwriting.")
        out_path.write_text(build_close_page(data), encoding="utf-8")
        print(f"Written: {out_path}")
        save_linkedin(data, today_iso)
        update_index_close(data, today_iso)
        update_archive(data, today_iso, "close", f"briefs/{filename}")
        update_sitemap(f"https://readmarketbrief.com/briefs/{filename}")

    # ── Morning / Midday — always publish ────────────────────────────────────
    elif update_type in ("morning", "midday"):
        data = generate_scheduled_update(update_type, today_iso, date_display)

        filename = f"{today_iso}-{update_type}.html"
        out_path = BRIEFS_DIR / filename
        if out_path.exists():
            print(f"WARNING: {out_path} already exists. Overwriting.")
        out_path.write_text(build_update_page(data, update_type), encoding="utf-8")
        print(f"Written: {out_path}")

        if update_type == "morning":
            update_index_morning(data, today_iso)

        update_archive(data, today_iso, update_type, f"briefs/{filename}")
        update_sitemap(f"https://readmarketbrief.com/briefs/{filename}")

    # ── Afterhours — conditional: only publish if meaningful news ─────────────
    elif update_type == "afterhours":
        data = generate_afterhours(today_iso, date_display)
        if data is None:
            print("No after-hours post published. No files changed.")
            sys.exit(0)  # Clean exit — workflow will not commit anything

        filename = f"{today_iso}-afterhours.html"
        out_path = BRIEFS_DIR / filename
        if out_path.exists():
            print(f"WARNING: {out_path} already exists. Overwriting.")
        out_path.write_text(build_update_page(data, "afterhours"), encoding="utf-8")
        print(f"Written: {out_path}")

        update_archive(data, today_iso, "afterhours", f"briefs/{filename}")
        update_sitemap(f"https://readmarketbrief.com/briefs/{filename}")

    # ── Breaking ──────────────────────────────────────────────────────────────
    elif update_type == "breaking":
        data = generate_breaking(today_iso, date_display)
        if data is None:
            sys.exit(0)  # Clean exit — nothing breaking

        file_time = et_now.strftime("%H%M")
        slug      = data.get("slug", "market-alert")
        slug      = re.sub(r"[^a-z0-9-]", "", slug.lower().replace(" ", "-"))[:40]
        filename  = f"{today_iso}-{file_time}-{slug}.html"

        out_path = BREAKING_DIR / filename
        out_path.write_text(build_breaking_page(data), encoding="utf-8")
        print(f"Written: {out_path}")

        update_index_breaking(data, today_iso, filename)
        update_archive(data, today_iso, "breaking", f"breaking/{filename}")
        update_sitemap(f"https://readmarketbrief.com/breaking/{filename}")

    print(f"=== Done: {update_type} ===")


if __name__ == "__main__":
    main()
