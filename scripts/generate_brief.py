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
ROOT = Path(__file__).parent.parent
BRIEFS_DIR        = ROOT / "briefs"
INDEX_HTML        = ROOT / "index.html"
ARCHIVE_HTML      = ROOT / "archive.html"
SYSTEM_PROMPT_FILE = ROOT / "prompts" / "system_prompt.txt"
RAW_RESPONSE_FILE = ROOT / "claude_raw_response.txt"
LINKEDIN_DIR      = ROOT / "linkedin"

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
    "feature_theme",
    "feature_image_alt",
    "market_snapshot",
    "archive_teaser",
    "homepage_teaser",
    "linkedin_post",
    "share_text",
    "article_html",
]

# ── Feature theme SVG art ──────────────────────────────────────────────────────
# Each entry: background color + inline SVG content for a 680×200 viewBox.
# All art is pure SVG — no external resources, no copyright issues.
FEATURE_THEMES = {
    "market-dashboard": {
        "label": "Market Dashboard",
        "bg": "#0d0d0d",
        "svg": """
  <line x1="0" y1="60" x2="680" y2="60" stroke="#222" stroke-width="1"/>
  <line x1="0" y1="120" x2="680" y2="120" stroke="#222" stroke-width="1"/>
  <line x1="0" y1="170" x2="680" y2="170" stroke="#222" stroke-width="1"/>
  <line x1="136" y1="0" x2="136" y2="200" stroke="#1a1a1a" stroke-width="1"/>
  <line x1="272" y1="0" x2="272" y2="200" stroke="#1a1a1a" stroke-width="1"/>
  <line x1="408" y1="0" x2="408" y2="200" stroke="#1a1a1a" stroke-width="1"/>
  <line x1="544" y1="0" x2="544" y2="200" stroke="#1a1a1a" stroke-width="1"/>
  <polyline points="0,165 60,155 110,160 170,138 230,143 290,118 350,124 410,96 460,104 520,74 580,80 640,52 680,44"
            fill="none" stroke="#22c55e" stroke-width="2.5" stroke-linejoin="round"/>
  <polygon points="0,165 60,155 110,160 170,138 230,143 290,118 350,124 410,96 460,104 520,74 580,80 640,52 680,44 680,200 0,200"
           fill="#22c55e" fill-opacity="0.07"/>
  <circle cx="520" cy="74" r="3.5" fill="#22c55e"/>
  <circle cx="640" cy="52" r="3.5" fill="#22c55e"/>
  <circle cx="680" cy="44" r="5" fill="#22c55e"/>
  <polyline points="0,155 100,148 200,152 300,144 400,138 500,130 620,120 680,118"
            fill="none" stroke="#22c55e" stroke-width="1" opacity="0.25" stroke-dasharray="3,4"/>""",
    },
    "fed-rates": {
        "label": "Fed & Rates",
        "bg": "#060e1a",
        "svg": """
  <line x1="0" y1="50" x2="680" y2="50" stroke="#0d1f33" stroke-width="1"/>
  <line x1="0" y1="100" x2="680" y2="100" stroke="#0d1f33" stroke-width="1"/>
  <line x1="0" y1="150" x2="680" y2="150" stroke="#0d1f33" stroke-width="1"/>
  <path d="M 40,165 C 120,165 200,130 320,100 S 500,72 640,65"
        fill="none" stroke="#60a5fa" stroke-width="2.5" stroke-linejoin="round"/>
  <polygon points="40,165 120,165 200,130 320,100 500,72 640,65 680,64 680,200 0,200"
           fill="#60a5fa" fill-opacity="0.07"/>
  <path d="M 40,130 C 140,128 260,126 380,130 S 540,138 640,142"
        fill="none" stroke="#60a5fa" stroke-width="1.2" stroke-dasharray="5,4" opacity="0.35"/>
  <line x1="140" y1="30" x2="140" y2="185" stroke="#f59e0b" stroke-width="1" stroke-dasharray="4,3" opacity="0.55"/>
  <text x="146" y="48" fill="#f59e0b" font-size="9" font-family="monospace" opacity="0.75">FOMC</text>
  <line x1="390" y1="30" x2="390" y2="185" stroke="#f59e0b" stroke-width="1" stroke-dasharray="4,3" opacity="0.35"/>
  <text x="396" y="48" fill="#f59e0b" font-size="9" font-family="monospace" opacity="0.5">NEXT</text>""",
    },
    "earnings": {
        "label": "Earnings Season",
        "bg": "#080808",
        "svg": """
  <line x1="0" y1="170" x2="680" y2="170" stroke="#1e1e1e" stroke-width="1"/>
  <line x1="0" y1="120" x2="680" y2="120" stroke="#1a1a1a" stroke-width="1"/>
  <line x1="0" y1="70" x2="680" y2="70" stroke="#1a1a1a" stroke-width="1"/>
  <rect x="45" y="118" width="32" height="52" fill="#1e293b" rx="1"/>
  <rect x="45" y="95"  width="32" height="75" fill="#22c55e" rx="1" opacity="0.85"/>
  <rect x="125" y="125" width="32" height="45" fill="#1e293b" rx="1"/>
  <rect x="125" y="102" width="32" height="68" fill="#22c55e" rx="1" opacity="0.85"/>
  <rect x="205" y="110" width="32" height="60" fill="#1e293b" rx="1"/>
  <rect x="205" y="122" width="32" height="48" fill="#ef4444" rx="1" opacity="0.75"/>
  <rect x="285" y="105" width="32" height="65" fill="#1e293b" rx="1"/>
  <rect x="285" y="85"  width="32" height="85" fill="#22c55e" rx="1" opacity="0.85"/>
  <rect x="365" y="115" width="32" height="55" fill="#1e293b" rx="1"/>
  <rect x="365" y="92"  width="32" height="78" fill="#22c55e" rx="1" opacity="0.85"/>
  <rect x="445" y="108" width="32" height="62" fill="#1e293b" rx="1"/>
  <rect x="445" y="118" width="32" height="52" fill="#ef4444" rx="1" opacity="0.65"/>
  <rect x="525" y="100" width="32" height="70" fill="#1e293b" rx="1"/>
  <rect x="525" y="80"  width="32" height="90" fill="#22c55e" rx="1" opacity="0.85"/>
  <rect x="605" y="112" width="32" height="58" fill="#1e293b" rx="1"/>
  <rect x="605" y="90"  width="32" height="80" fill="#22c55e" rx="1" opacity="0.85"/>
  <polyline points="61,88 141,95 221,115 301,78 381,85 461,110 541,73 621,83"
            fill="none" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="5,3" opacity="0.6"/>""",
    },
    "oil-commodities": {
        "label": "Oil & Commodities",
        "bg": "#0a0800",
        "svg": """
  <line x1="0" y1="60" x2="680" y2="60" stroke="#1e1600" stroke-width="1"/>
  <line x1="0" y1="110" x2="680" y2="110" stroke="#1e1600" stroke-width="1"/>
  <line x1="0" y1="160" x2="680" y2="160" stroke="#1e1600" stroke-width="1"/>
  <polyline points="0,90 50,75 100,60 150,48 200,68 250,52 300,80 350,100 400,115 450,108 500,132 560,148 620,158 680,165"
            fill="none" stroke="#f59e0b" stroke-width="2.5" stroke-linejoin="round"/>
  <polygon points="0,90 50,75 100,60 150,48 200,68 250,52 300,80 350,100 400,115 450,108 500,132 560,148 620,158 680,165 680,200 0,200"
           fill="#f59e0b" fill-opacity="0.07"/>
  <polyline points="0,145 80,138 170,130 270,125 370,128 470,133 580,140 680,148"
            fill="none" stroke="#fb923c" stroke-width="1.2" opacity="0.4"/>
  <circle cx="150" cy="48" r="3.5" fill="#f59e0b"/>
  <line x1="150" y1="20" x2="150" y2="48" stroke="#f59e0b" stroke-width="1" stroke-dasharray="3,2" opacity="0.5"/>
  <text x="155" y="36" fill="#f59e0b" font-size="9" font-family="monospace" opacity="0.7">PEAK</text>""",
    },
    "geopolitics": {
        "label": "Geopolitics",
        "bg": "#03030e",
        "svg": """
  <ellipse cx="340" cy="100" rx="190" ry="85" fill="none" stroke="#1e1b4b" stroke-width="1" opacity="0.9"/>
  <ellipse cx="340" cy="100" rx="120" ry="85" fill="none" stroke="#1e1b4b" stroke-width="1" opacity="0.65"/>
  <ellipse cx="340" cy="100" rx="50" ry="85" fill="none" stroke="#1e1b4b" stroke-width="1" opacity="0.4"/>
  <line x1="150" y1="100" x2="530" y2="100" stroke="#1e1b4b" stroke-width="1" opacity="0.9"/>
  <line x1="340" y1="15" x2="340" y2="185" stroke="#1e1b4b" stroke-width="1" opacity="0.9"/>
  <line x1="170" y1="50" x2="510" y2="50" stroke="#1e1b4b" stroke-width="0.6" opacity="0.5"/>
  <line x1="170" y1="150" x2="510" y2="150" stroke="#1e1b4b" stroke-width="0.6" opacity="0.5"/>
  <circle cx="225" cy="82" r="5" fill="#818cf8" opacity="0.9"/>
  <circle cx="225" cy="82" r="13" fill="none" stroke="#818cf8" stroke-width="1" opacity="0.35"/>
  <circle cx="470" cy="68" r="5" fill="#818cf8" opacity="0.9"/>
  <circle cx="470" cy="68" r="13" fill="none" stroke="#818cf8" stroke-width="1" opacity="0.35"/>
  <circle cx="390" cy="138" r="4" fill="#818cf8" opacity="0.65"/>
  <circle cx="300" cy="55" r="3" fill="#818cf8" opacity="0.5"/>
  <line x1="225" y1="82" x2="470" y2="68" stroke="#818cf8" stroke-width="0.8" stroke-dasharray="5,4" opacity="0.45"/>
  <line x1="470" y1="68" x2="390" y2="138" stroke="#818cf8" stroke-width="0.8" stroke-dasharray="5,4" opacity="0.45"/>
  <line x1="225" y1="82" x2="300" y2="55" stroke="#818cf8" stroke-width="0.8" stroke-dasharray="5,4" opacity="0.3"/>""",
    },
    "sector-rotation": {
        "label": "Sector Rotation",
        "bg": "#040609",
        "svg": """
  <path d="M 340,100 L 340,28 A 72,72 0 0,1 402,136 Z" fill="#22c55e" opacity="0.82"/>
  <path d="M 340,100 L 402,136 A 72,72 0 0,1 278,136 Z" fill="#ef4444" opacity="0.72"/>
  <path d="M 340,100 L 278,136 A 72,72 0 0,1 278,64 Z" fill="#f59e0b" opacity="0.78"/>
  <path d="M 340,100 L 278,64 A 72,72 0 0,1 340,28 Z" fill="#60a5fa" opacity="0.72"/>
  <circle cx="340" cy="100" r="34" fill="#040609"/>
  <text x="356" y="64" fill="#22c55e" font-size="9" font-family="monospace" opacity="0.9">TECH</text>
  <text x="382" y="132" fill="#ef4444" font-size="9" font-family="monospace" opacity="0.9">ENRG</text>
  <text x="272" y="148" fill="#f59e0b" font-size="9" font-family="monospace" opacity="0.9">FIN</text>
  <text x="274" y="72" fill="#60a5fa" font-size="9" font-family="monospace" opacity="0.9">HLTH</text>
  <path d="M 340,100 m 46,0 a 46,46 0 0,0 -46,-46" fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="1.5"/>
  <polygon points="296,52 302,62 290,62" fill="rgba(255,255,255,0.35)"/>
  <circle cx="160" cy="100" r="28" fill="none" stroke="#1e293b" stroke-width="1"/>
  <circle cx="520" cy="100" r="28" fill="none" stroke="#1e293b" stroke-width="1"/>
  <text x="140" y="94" fill="#94a3b8" font-size="8" font-family="monospace" opacity="0.6">SECTOR</text>
  <text x="141" y="106" fill="#94a3b8" font-size="8" font-family="monospace" opacity="0.6">WEIGHT</text>
  <text x="498" y="94" fill="#94a3b8" font-size="8" font-family="monospace" opacity="0.6">PRICE</text>
  <text x="499" y="106" fill="#94a3b8" font-size="8" font-family="monospace" opacity="0.6">RETURN</text>""",
    },
    "banking": {
        "label": "Banking & Credit",
        "bg": "#060606",
        "svg": """
  <line x1="0" y1="170" x2="680" y2="170" stroke="#1e1e1e" stroke-width="1"/>
  <line x1="0" y1="120" x2="680" y2="120" stroke="#181818" stroke-width="1"/>
  <line x1="0" y1="70" x2="680" y2="70" stroke="#141414" stroke-width="1"/>
  <rect x="40"  y="65"  width="44" height="105" fill="#1e293b" rx="1"/>
  <rect x="40"  y="65"  width="44" height="65"  fill="#334155" rx="1"/>
  <rect x="118" y="80"  width="44" height="90"  fill="#1e293b" rx="1"/>
  <rect x="118" y="80"  width="44" height="52"  fill="#334155" rx="1"/>
  <rect x="196" y="55"  width="44" height="115" fill="#1e293b" rx="1"/>
  <rect x="196" y="55"  width="44" height="72"  fill="#334155" rx="1"/>
  <rect x="274" y="72"  width="44" height="98"  fill="#1e293b" rx="1"/>
  <rect x="274" y="72"  width="44" height="58"  fill="#334155" rx="1"/>
  <rect x="352" y="60"  width="44" height="110" fill="#1e293b" rx="1"/>
  <rect x="352" y="60"  width="44" height="68"  fill="#334155" rx="1"/>
  <rect x="430" y="78"  width="44" height="92"  fill="#1e293b" rx="1"/>
  <rect x="430" y="120" width="44" height="50"  fill="#ef4444" rx="1" opacity="0.65"/>
  <rect x="508" y="68"  width="44" height="102" fill="#1e293b" rx="1"/>
  <rect x="508" y="68"  width="44" height="62"  fill="#334155" rx="1"/>
  <rect x="586" y="75"  width="44" height="95"  fill="#1e293b" rx="1"/>
  <rect x="586" y="75"  width="44" height="55"  fill="#334155" rx="1"/>
  <polyline points="62,80 140,88 218,72 296,84 374,76 452,92 530,80 608,85"
            fill="none" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="5,3" opacity="0.6"/>""",
    },
    "tech": {
        "label": "Tech & AI",
        "bg": "#02020c",
        "svg": """
  <circle cx="170" cy="100" r="6" fill="#a78bfa"/>
  <circle cx="340" cy="58"  r="8" fill="#a78bfa"/>
  <circle cx="340" cy="142" r="6" fill="#a78bfa"/>
  <circle cx="510" cy="100" r="8" fill="#a78bfa"/>
  <circle cx="255" cy="162" r="4" fill="#a78bfa" opacity="0.6"/>
  <circle cx="425" cy="48"  r="4" fill="#a78bfa" opacity="0.6"/>
  <circle cx="95"  cy="52"  r="4" fill="#a78bfa" opacity="0.5"/>
  <circle cx="585" cy="158" r="4" fill="#a78bfa" opacity="0.5"/>
  <circle cx="600" cy="60"  r="3" fill="#a78bfa" opacity="0.4"/>
  <line x1="170" y1="100" x2="340" y2="58"  stroke="#a78bfa" stroke-width="1.2" opacity="0.5"/>
  <line x1="170" y1="100" x2="340" y2="142" stroke="#a78bfa" stroke-width="1.2" opacity="0.5"/>
  <line x1="340" y1="58"  x2="510" y2="100" stroke="#a78bfa" stroke-width="1.8" opacity="0.65"/>
  <line x1="340" y1="142" x2="510" y2="100" stroke="#a78bfa" stroke-width="1.8" opacity="0.65"/>
  <line x1="340" y1="58"  x2="340" y2="142" stroke="#a78bfa" stroke-width="0.8" opacity="0.3"/>
  <line x1="95"  y1="52"  x2="170" y2="100" stroke="#a78bfa" stroke-width="0.8" opacity="0.3"/>
  <line x1="425" y1="48"  x2="340" y2="58"  stroke="#a78bfa" stroke-width="0.8" opacity="0.3"/>
  <line x1="255" y1="162" x2="340" y2="142" stroke="#a78bfa" stroke-width="0.8" opacity="0.3"/>
  <line x1="585" y1="158" x2="510" y2="100" stroke="#a78bfa" stroke-width="0.8" opacity="0.3"/>
  <line x1="600" y1="60"  x2="510" y2="100" stroke="#a78bfa" stroke-width="0.8" opacity="0.25"/>
  <circle cx="340" cy="58"  r="20" fill="none" stroke="#a78bfa" stroke-width="0.6" opacity="0.25"/>
  <circle cx="510" cy="100" r="20" fill="none" stroke="#a78bfa" stroke-width="0.6" opacity="0.25"/>""",
    },
}

# ── Additional CSS for new visual components ───────────────────────────────────
NEW_CSS = """
  .issue-kicker{font-family:'DM Mono',monospace;font-size:10px;letter-spacing:.24em;text-transform:uppercase;color:var(--muted);padding:20px 0 10px;border-bottom:1px solid var(--rule)}
  .issue-headline{font-family:'Playfair Display',Georgia,serif;font-size:clamp(24px,5vw,38px);font-weight:900;line-height:1.1;letter-spacing:-.022em;color:var(--ink);margin:16px 0 14px}
  .opening-summary{font-size:16.5px;line-height:1.78;color:#3d3830;border-left:3px solid var(--ink);padding-left:18px;margin-bottom:24px;font-style:italic}
  .feature-visual{position:relative;overflow:hidden;height:180px;margin-bottom:20px}
  .feature-visual svg{position:absolute;top:0;left:0;width:100%;height:100%}
  .feature-visual-label{position:absolute;bottom:12px;left:16px;font-family:'DM Mono',monospace;font-size:8.5px;letter-spacing:.22em;text-transform:uppercase;color:rgba(255,255,255,0.45);z-index:1}
  .feature-visual-alt{position:absolute;top:12px;right:14px;font-family:'DM Mono',monospace;font-size:8px;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,0.2)}
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
"""

# ── Full inline CSS for brief pages ───────────────────────────────────────────
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
""" + NEW_CSS


def render_feature_card(theme: str, alt: str) -> str:
    """Return an HTML feature card with pure-SVG abstract art for the given theme."""
    config = FEATURE_THEMES.get(theme, FEATURE_THEMES["market-dashboard"])
    label = config["label"]
    bg = config["bg"]
    svg_inner = config["svg"]
    return (
        f'<div class="feature-visual" style="background:{bg}">\n'
        f'  <svg viewBox="0 0 680 200" xmlns="http://www.w3.org/2000/svg" '
        f'preserveAspectRatio="xMidYMid slice" aria-hidden="true">\n'
        f'{svg_inner}\n'
        f'  </svg>\n'
        f'  <div class="feature-visual-label">{label}</div>\n'
        f'  <div class="feature-visual-alt">{alt}</div>\n'
        f'</div>\n'
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
        "market stories today. Then produce a complete issue of The Brief. "
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

    # market_snapshot must be a list with real data
    snapshot = data.get("market_snapshot", [])
    if not isinstance(snapshot, list) or len(snapshot) < 4:
        print(f"ERROR: market_snapshot must be a list of at least 4 items (got {type(snapshot).__name__}, len={len(snapshot) if isinstance(snapshot, list) else 'n/a'})")
        sys.exit(1)
    placeholders = {"X,XXX", "XX,XXX", "X.XX", "$XX.XX", "X.X%", ""}
    for item in snapshot:
        if item.get("value", "") in placeholders:
            print(f"ERROR: Placeholder value in market_snapshot for '{item.get('label')}': '{item.get('value')}'")
            sys.exit(1)

    # feature_theme must be a known key
    valid_themes = set(FEATURE_THEMES.keys())
    theme = data.get("feature_theme", "")
    if theme not in valid_themes:
        print(f"WARNING: Unknown feature_theme '{theme}'. Falling back to 'market-dashboard'.")
        data["feature_theme"] = "market-dashboard"

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
    date_iso       = data["date_iso"]
    seo_title      = data["seo_title"]
    meta_desc      = data["meta_description"]
    alert_strip    = data["alert_strip"]
    kicker         = data["issue_kicker"]
    headline       = data["headline"]
    opening        = data["opening_summary"]
    feature_theme  = data["feature_theme"]
    feature_alt    = data["feature_image_alt"]
    article_html   = data["article_html"]
    snapshot       = data["market_snapshot"]

    site_url = f"https://thebrieffinance.com/briefs/{date_iso}.html"
    share_raw = data["share_text"].replace("{{URL}}", site_url)
    share_encoded = re.sub(r"\s+", "+", share_raw.strip())

    feature_card_html  = render_feature_card(feature_theme, feature_alt)
    market_snap_html   = render_market_snapshot(snapshot)

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
  <div class="issue-kicker">{kicker}</div>
  <h1 class="issue-headline">{headline}</h1>
  <p class="opening-summary">{opening}</p>

{feature_card_html}
{market_snap_html}

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
