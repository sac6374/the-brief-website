/* Read Market Brief — Market Dashboard
   Only calls /api/market-data — no API keys in this file. */
'use strict';

/* ── Labels / display tickers ───────────────────────────────────── */
const LABEL = {
  SPX:'S&P 500', IXIC:'Nasdaq', DJI:'Dow Jones', RUT:'Russell 2000', VIX:'CBOE VIX',
  AAPL:'Apple', MSFT:'Microsoft', NVDA:'NVIDIA', AMZN:'Amazon',
  GOOGL:'Alphabet', META:'Meta', TSLA:'Tesla',
  'BTC/USD':'Bitcoin', 'ETH/USD':'Ethereum', 'XRP/USD':'XRP', 'SOL/USD':'Solana',
  'XAU/USD':'Gold', 'XAG/USD':'Silver', 'XCU/USD':'Copper',
  'WTI/USD':'WTI Crude', 'BRNT/USD':'Brent Crude', 'NG/USD':'Natural Gas',
  'EUR/USD':'Euro / Dollar', 'USD/JPY':'Dollar / Yen',
  'GBP/USD':'Sterling / Dollar', DXY:'US Dollar Index', 'USD/CAD':'Dollar / CAD',
  US10Y:'US 10Y Treasury', US2Y:'US 2Y Treasury',
};

// Clean short ticker for the left column
const TICK = {
  'BTC/USD':'BTC',   'ETH/USD':'ETH',   'XRP/USD':'XRP',   'SOL/USD':'SOL',
  'XAU/USD':'GOLD',  'XAG/USD':'SILVER','XCU/USD':'COPPER',
  'WTI/USD':'WTI',   'BRNT/USD':'BRENT','NG/USD':'NAT GAS',
  'EUR/USD':'EUR/USD','USD/JPY':'USD/JPY','GBP/USD':'GBP/USD',
  'USD/CAD':'USD/CAD', DXY:'DXY',
};

/* ── Formatting ─────────────────────────────────────────────────── */
function decimals(price, sym) {
  if (price == null) return 2;
  if (/BTC/.test(sym) || price > 10000) return 0;
  if (price > 9) return 2;
  if (price > 0.9) return 4;
  return 6;
}
function fmt(v, sym) {
  if (v == null) return '—';
  const d = decimals(v, sym);
  return v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
}
function fmtPct(pct) {
  if (pct == null) return null;
  const s = pct >= 0 ? '+' : '';
  return `${s}${Math.abs(pct) < 0.01 ? pct.toFixed(3) : pct.toFixed(2)}%`;
}
function tsFmt(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('en-US',
    { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

/* ── DOM helpers ────────────────────────────────────────────────── */
const $  = id => document.getElementById(id);
const dir = pct => pct == null ? 'flat' : pct >= 0 ? 'up' : 'dn';

/* ── Skeletons ──────────────────────────────────────────────────── */
function skels(n) {
  return Array(n).fill(0).map(() =>
    `<div class="dc-skel-row">
      <div class="dc-skel dc-skel-name"></div>
      <div class="dc-skel dc-skel-sm"></div>
      <div class="dc-skel dc-skel-pill"></div>
    </div>`).join('');
}

/* ── Data rows ──────────────────────────────────────────────────── */

// Name-only row: full name | price | pill (indices, forex, commodities, energy, bonds)
function rowHTMLName(item) {
  const name = LABEL[item.symbol] || item.name || item.symbol;
  if (item.unavailable) {
    return `<div class="dc-row">
      <span class="dc-name-main">${name}</span>
      <span class="dc-price">—</span>
      <span class="dc-pill flat">N/A</span>
    </div>`;
  }
  const price = fmt(item.price, item.symbol);
  const pct   = fmtPct(item.pct);
  const d     = dir(item.pct);
  return `<div class="dc-row">
    <span class="dc-name-main">${name}</span>
    <span class="dc-price">${price}</span>
    <span class="dc-pill ${d}">${pct || '—'}</span>
  </div>`;
}

// Ticker row: ticker | price | pill (MAG7, crypto)
function rowHTMLTick(item) {
  const tick = TICK[item.symbol] || item.symbol;
  if (item.unavailable) {
    return `<div class="dc-row">
      <span class="dc-tick">${tick}</span>
      <span class="dc-price">—</span>
      <span class="dc-pill flat">N/A</span>
    </div>`;
  }
  const price = fmt(item.price, item.symbol);
  const pct   = fmtPct(item.pct);
  const d     = dir(item.pct);
  return `<div class="dc-row">
    <span class="dc-tick">${tick}</span>
    <span class="dc-price">${price}</span>
    <span class="dc-pill ${d}">${pct || '—'}</span>
  </div>`;
}

function paint(id, items, style = 'name') {
  const el = $(id);
  if (!el) return;
  if (!items || !items.length) { el.innerHTML = `<div class="dc-err">Data unavailable</div>`; return; }
  const fn = style === 'tick' ? rowHTMLTick : rowHTMLName;
  el.innerHTML = items.map(fn).join('');
}

function setTs(id, ts) {
  const el = $(id);
  if (el && ts) el.textContent = `Updated ${tsFmt(ts)}`;
}

/* ── Bonds card ─────────────────────────────────────────────────── */
function renderBonds(bonds, ts) {
  const el = $('bonds-rows');
  if (!el) return;
  if (!bonds || !bonds.available) {
    el.innerHTML = `<div class="dc-unavail">
      <div class="dc-unavail-label">Treasury yield data unavailable</div>
      <div class="dc-unavail-note">US 10Y and 2Y yields are not provided by this data source. Yield commentary is in every issue of The Brief.</div>
    </div>`;
    return;
  }
  el.innerHTML = bonds.items.map(rowHTMLName).join('');
  if (bonds.spread != null) {
    el.insertAdjacentHTML('beforeend', `
      <div class="dc-spread">
        <span class="dc-spread-label">10Y – 2Y Spread</span>
        <span class="dc-spread-val">${bonds.spread >= 0 ? '+' : ''}${bonds.spread.toFixed(3)}%</span>
      </div>`);
  }
  setTs('ts-bonds', ts);
}

/* ── Sentiment gauge ────────────────────────────────────────────── */
function renderSentiment(sentiment, ts) {
  const el = $('sentiment-panel');
  if (!el) return;
  if (!sentiment) { el.innerHTML = `<div class="dc-err">Sentiment unavailable</div>`; return; }

  const { score, vix } = sentiment;
  let label, color, desc;
  if      (score >= 80) { label='Extreme Greed'; color='#22c55e'; desc='Markets calm. Low VIX signals high complacency — historically a caution signal.'; }
  else if (score >= 60) { label='Greed';         color='#86efac'; desc='Risk appetite above average. Equities broadly well-bid.'; }
  else if (score >= 40) { label='Neutral';        color='#fbbf24'; desc='Near the historical average. No strong directional bias.'; }
  else if (score >= 20) { label='Fear';           color='#fb923c'; desc='Elevated uncertainty. Investors increasing defensive positioning.'; }
  else                  { label='Extreme Fear';   color='#ef4444'; desc='High market stress. Sharp daily moves and elevated volatility likely.'; }

  // 5-zone colored semicircle gauge
  const cx = 95, cy = 95, r = 74;
  const toRad = a => (a * Math.PI) / 180;
  const zones = [
    { c:'#ef4444', a1:180, a2:144 },
    { c:'#fb923c', a1:144, a2:108 },
    { c:'#fbbf24', a1:108, a2: 72 },
    { c:'#86efac', a1: 72, a2: 36 },
    { c:'#22c55e', a1: 36, a2:  0 },
  ];
  const arc = (a1, a2) => {
    const x1 = cx + r * Math.cos(toRad(a1)), y1 = cy - r * Math.sin(toRad(a1));
    const x2 = cx + r * Math.cos(toRad(a2)), y2 = cy - r * Math.sin(toRad(a2));
    return `M${x1},${y1} A${r},${r} 0 0 1 ${x2},${y2}`;
  };

  const needleA = 180 - (score / 100) * 180;
  const nx = cx + (r - 8) * Math.cos(toRad(needleA));
  const ny = cy - (r - 8) * Math.sin(toRad(needleA));

  el.innerHTML = `
    <svg class="dc-gauge-svg" viewBox="0 0 190 108" xmlns="http://www.w3.org/2000/svg">
      <path d="M${cx-r},${cy} A${r},${r} 0 0 1 ${cx+r},${cy}"
        stroke="rgba(255,255,255,0.05)" stroke-width="9" fill="none" stroke-linecap="butt"/>
      ${zones.map(z => `<path d="${arc(z.a1,z.a2)}" stroke="${z.c}" stroke-width="9" fill="none" stroke-linecap="butt" opacity="0.8"/>`).join('')}
      <line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" stroke="#fff" stroke-width="2" stroke-linecap="round" opacity="0.85"/>
      <circle cx="${cx}" cy="${cy}" r="4" fill="${color}"/>
      <circle cx="${cx}" cy="${cy}" r="1.8" fill="#0f1117"/>
      <text x="8"   y="106" font-size="7" fill="rgba(255,255,255,0.2)" font-family="monospace">Fear</text>
      <text x="155" y="106" font-size="7" fill="rgba(255,255,255,0.2)" font-family="monospace">Greed</text>
    </svg>
    <div class="dc-gauge-num" style="color:${color}">${score}</div>
    <div class="dc-gauge-lbl" style="color:${color}">${label}</div>
    <div class="dc-gauge-desc">${desc}</div>
    <div class="dc-gauge-note">Proxy from VIX${vix != null ? ` (${vix.toFixed(2)})` : ''} · Not the CNN Fear &amp; Greed Index</div>`;
  setTs('ts-sentiment', ts);
}

/* ── Overview ───────────────────────────────────────────────────── */
async function loadOverview() {
  const COUNTS = { 'indices-rows':5, 'mag7-rows':7, 'crypto-rows':4,
                   'commodities-rows':3, 'energy-rows':3, 'forex-rows':5 };
  Object.entries(COUNTS).forEach(([id, n]) => {
    const el = $(id); if (el) el.innerHTML = skels(n);
  });

  const statusEl  = $('db-status');
  const updatedEl = $('db-updated');

  try {
    const res  = await fetch('/api/market-data?type=overview');
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'API error');
    const ts = data.timestamp;

    paint('indices-rows',     data.indices,     'name'); setTs('ts-indices',     ts);
    paint('mag7-rows',        data.mag7,        'tick'); setTs('ts-mag7',        ts);
    paint('crypto-rows',      data.crypto,      'tick'); setTs('ts-crypto',      ts);
    paint('commodities-rows', data.commodities, 'name'); setTs('ts-commodities', ts);
    paint('energy-rows',      data.energy,      'name'); setTs('ts-energy',      ts);
    paint('forex-rows',       data.forex,       'name'); setTs('ts-forex',       ts);

    renderBonds(data.bonds, ts);
    renderSentiment(data.sentiment, ts);

    if (statusEl) { statusEl.className = 'db-status live'; statusEl.textContent = 'Market data loaded'; }
    if (updatedEl && ts) updatedEl.textContent = `As of ${tsFmt(ts)} · May be delayed`;

  } catch (_) {
    ['indices-rows','mag7-rows','crypto-rows','commodities-rows','energy-rows','forex-rows'].forEach(id => {
      const el = $(id); if (el) el.innerHTML = `<div class="dc-err">Data unavailable — try refreshing</div>`;
    });
    const sp = $('sentiment-panel'); if (sp) sp.innerHTML = `<div class="dc-err">Unavailable</div>`;
    const br = $('bonds-rows');      if (br) br.innerHTML = `<div class="dc-err">Unavailable</div>`;
    if (statusEl) { statusEl.className = 'db-status error'; statusEl.textContent = 'Market data unavailable'; }
  }
}

/* ── Chart ──────────────────────────────────────────────────────── */
const RANGES = {
  '1D':  { interval:'5min',  outputsize:80  },
  '5D':  { interval:'1h',    outputsize:40  },
  '1M':  { interval:'1day',  outputsize:23  },
  '3M':  { interval:'1day',  outputsize:66  },
  '6M':  { interval:'1day',  outputsize:130 },
  'YTD': { interval:'1day',  outputsize:180 },
  '1Y':  { interval:'1day',  outputsize:252 },
  '5Y':  { interval:'1week', outputsize:260 },
  'MAX': { interval:'1week', outputsize:520 },
};

let chartInst  = null;
let activeRange = '1Y';
let activeSym   = null;

async function fetchChart(symbol, range) {
  const { interval, outputsize } = RANGES[range] || RANGES['1Y'];
  const res  = await fetch(`/api/market-data?type=chart&symbol=${encodeURIComponent(symbol)}&interval=${interval}&outputsize=${outputsize}`);
  const data = await res.json();
  if (!res.ok || data.error) throw new Error(data.error || 'Chart unavailable');
  return data.values || [];
}

function drawChart(values, isUp) {
  const canvas = $('stock-chart');
  if (!canvas) return;
  if (chartInst) { chartInst.destroy(); chartInst = null; }
  const ctx   = canvas.getContext('2d');
  const color = isUp ? '#22c55e' : '#ef4444';
  const grad  = ctx.createLinearGradient(0, 0, 0, 280);
  grad.addColorStop(0, isUp ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)');
  grad.addColorStop(1, 'rgba(0,0,0,0)');

  chartInst = new Chart(ctx, {
    type: 'line',
    data: {
      labels: values.map(v => v.t),
      datasets: [{ data: values.map(v => v.c), borderColor: color, borderWidth: 1.5,
        fill: true, backgroundColor: grad, pointRadius: 0, tension: 0.2 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: 250 },
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1e2333', borderColor: 'rgba(255,255,255,0.08)', borderWidth: 1,
          titleColor: 'rgba(226,232,244,0.5)', bodyColor: '#e2e8f4',
          titleFont: { family: "'DM Mono', monospace", size: 10 },
          bodyFont:  { family: "'DM Mono', monospace", size: 12 },
          callbacks: {
            title: i => i[0]?.label || '',
            label: i => `  ${i.raw != null ? i.raw.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}) : '—'}`,
          },
        },
      },
      scales: {
        x: {
          display: true,
          ticks: { color:'rgba(226,232,244,0.2)', font:{family:"'DM Mono',monospace",size:9}, maxTicksLimit:6, maxRotation:0 },
          grid:  { color:'rgba(255,255,255,0.03)' },
          border:{ color:'transparent' },
        },
        y: {
          display: true, position: 'right',
          ticks: { color:'rgba(226,232,244,0.2)', font:{family:"'DM Mono',monospace",size:9},
            maxTicksLimit:5, callback: v => v.toLocaleString('en-US',{maximumFractionDigits:2}) },
          grid:  { color:'rgba(255,255,255,0.03)' },
          border:{ color:'transparent' },
        },
      },
    },
  });
}

async function loadChart(symbol, range) {
  const box = $('chart-box');
  if (!box) return;
  let overlay = box.querySelector('.dq-chart-overlay');
  if (!overlay) { overlay = document.createElement('div'); overlay.className = 'dq-chart-overlay'; box.appendChild(overlay); }
  overlay.textContent = 'Loading chart…';
  overlay.style.display = 'flex';

  document.querySelectorAll('.dq-range-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.range === range));

  try {
    const values = await fetchChart(symbol, range);
    overlay.style.display = 'none';
    if (!values.length) { overlay.textContent = 'Chart data unavailable'; overlay.style.display = 'flex'; return; }
    const isUp = values[values.length-1]?.c >= values[0]?.c;
    drawChart(values, isUp);
  } catch {
    overlay.textContent = 'Chart data unavailable';
    overlay.style.display = 'flex';
  }
}

/* ── Stock lookup ───────────────────────────────────────────────── */
async function lookupStock(symbol) {
  const result = $('search-result');
  if (!result) return;
  result.innerHTML = `<div class="db-search-loading">Looking up ${symbol}…</div>`;
  activeSym = symbol;

  try {
    const res  = await fetch(`/api/market-data?type=quote&symbol=${encodeURIComponent(symbol)}`);
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Symbol not found');

    const d     = dir(data.pct);
    const pct   = fmtPct(data.pct);
    const dec   = decimals(data.price, data.symbol);
    const fmtQ  = v => v != null ? v.toLocaleString('en-US',{minimumFractionDigits:dec,maximumFractionDigits:dec}) : '—';
    const sign  = (data.change || 0) >= 0 ? '+' : '';
    const chgAbs = data.change != null
      ? `${sign}${Math.abs(data.change).toFixed(dec > 2 ? 4 : 2)}` : null;

    const rangeBtns = Object.keys(RANGES).map(r =>
      `<button class="dq-range-btn${r===activeRange?' active':''}" data-range="${r}">${r}</button>`
    ).join('');

    const stats = [
      ['Open',       fmtQ(data.open)],
      ['Day High',   fmtQ(data.high)],
      ['Day Low',    fmtQ(data.low)],
      ['Prev Close', fmtQ(data.prev_close)],
      ['52W High',   fmtQ(data.wk52_high)],
      ['52W Low',    fmtQ(data.wk52_low)],
      ['Market Cap', '—'],
      ['P/E Ratio',  '—'],
    ];

    result.innerHTML = `
      <div class="dq-top">
        <div>
          <span class="dq-sym">${data.symbol}</span>
          ${data.name ? `<span class="dq-name">${data.name}</span>` : ''}
        </div>
        ${data.exchange ? `<span class="dq-exch">${data.exchange}</span>` : ''}
      </div>
      <div class="dq-main">
        <span class="dq-price">${fmtQ(data.price)}</span>
        ${chgAbs && pct ? `<span class="dq-chg ${d}">${chgAbs} &nbsp; ${pct}</span>` : ''}
      </div>
      <div class="dq-range" id="range-bar">${rangeBtns}</div>
      <div class="dq-chartbox" id="chart-box">
        <canvas id="stock-chart"></canvas>
        <div class="dq-chart-overlay">Loading chart…</div>
      </div>
      <div class="dq-stats">
        ${stats.map(([l,v]) => `<div class="dq-stat"><div class="dq-stat-label">${l}</div><div class="dq-stat-val">${v}</div></div>`).join('')}
      </div>
      <div style="margin-top:12px;font-family:'DM Mono',monospace;font-size:8px;letter-spacing:.08em;color:rgba(226,232,244,0.2);text-align:center;">
        Market data may be delayed &middot; Not investment advice
      </div>`;

    $('range-bar')?.addEventListener('click', e => {
      const btn = e.target.closest('.dq-range-btn');
      if (!btn) return;
      activeRange = btn.dataset.range;
      loadChart(activeSym, activeRange);
    });

    await loadChart(symbol, activeRange);

  } catch (err) {
    result.innerHTML = `<div class="dc-err">${err.message || 'Symbol not found or unavailable'}</div>`;
  }
}

/* ── Search init ────────────────────────────────────────────────── */
function initSearch() {
  const input = $('search-input');
  const btn   = $('search-go');
  if (!input || !btn) return;
  const go = () => {
    const sym = input.value.trim().toUpperCase().replace(/[^A-Z0-9./-]/g,'').slice(0,12);
    if (sym) { activeRange = '1Y'; lookupStock(sym); }
  };
  btn.addEventListener('click', go);
  input.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
}

/* ── Boot ───────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  loadOverview();
  initSearch();
});
