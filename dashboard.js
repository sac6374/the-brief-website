/* Read Market Brief — Market Dashboard
   Calls only /api/market-data (Cloudflare Pages Function proxy).
   No API keys. No hardcoded prices. Chart.js loaded in HTML. */

'use strict';

/* ── Labels & display tickers ────────────────────────────────────── */
const LABELS = {
  SPX: 'S&P 500', IXIC: 'Nasdaq Composite', DJI: 'Dow Jones',
  RUT: 'Russell 2000', VIX: 'CBOE VIX',
  AAPL: 'Apple', MSFT: 'Microsoft', NVDA: 'NVIDIA', AMZN: 'Amazon',
  GOOGL: 'Alphabet', META: 'Meta', TSLA: 'Tesla',
  'BTC/USD': 'Bitcoin', 'ETH/USD': 'Ethereum',
  'XRP/USD': 'XRP', 'SOL/USD': 'Solana',
  'XAU/USD': 'Gold', 'XAG/USD': 'Silver', 'XCU/USD': 'Copper',
  'WTI/USD': 'WTI Crude Oil', 'BRNT/USD': 'Brent Crude Oil', 'NG/USD': 'Natural Gas',
  'EUR/USD': 'Euro / Dollar', 'USD/JPY': 'Dollar / Yen',
  'GBP/USD': 'Sterling / Dollar', 'DXY': 'US Dollar Index', 'USD/CAD': 'Dollar / CAD',
  US10Y: 'US 10Y Treasury', US2Y: 'US 2Y Treasury',
};

// Clean short tickers shown in the row's primary left column
const TICK = {
  'BTC/USD': 'BTC',   'ETH/USD': 'ETH',   'XRP/USD': 'XRP',   'SOL/USD': 'SOL',
  'XAU/USD': 'GOLD',  'XAG/USD': 'SILVER', 'XCU/USD': 'COPPER',
  'WTI/USD': 'WTI',   'BRNT/USD': 'BRENT', 'NG/USD': 'NAT GAS',
  'EUR/USD': 'EUR/USD', 'USD/JPY': 'USD/JPY', 'GBP/USD': 'GBP/USD',
  'USD/CAD': 'USD/CAD', DXY: 'DXY',
};

/* ── Formatting ──────────────────────────────────────────────────── */
function decimals(price, sym) {
  if (price == null) return 2;
  if (/BTC/.test(sym) || price > 10000) return 0;
  if (price > 999) return 2;
  if (price > 9)   return 2;
  if (price > 0.9) return 4;
  return 6;
}
function fmt(price, sym) {
  if (price == null) return '—';
  const d = decimals(price, sym);
  return price.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
}
function fmtPct(pct) {
  if (pct == null) return null;
  const s = pct >= 0 ? '+' : '';
  return `${s}${Math.abs(pct) < 0.01 ? pct.toFixed(3) : pct.toFixed(2)}%`;
}
function fmtLarge(n) {
  if (n == null) return '—';
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6)  return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toLocaleString()}`;
}
function tsFmt(ts) {
  if (!ts) return '';
  return new Date(ts).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

/* ── DOM helpers ─────────────────────────────────────────────────── */
function el(id) { return document.getElementById(id); }
function pillDir(pct) { return pct == null ? 'flat' : pct >= 0 ? 'up' : 'dn'; }

/* ── Skeleton ────────────────────────────────────────────────────── */
function skeletons(n) {
  return Array(n).fill(0).map(() =>
    `<div class="dskel-row">
      <div class="dskel" style="width:58%"></div>
      <div class="dskel dskel-sm"></div>
      <div class="dskel dskel-sm"></div>
    </div>`
  ).join('');
}

/* ── Row HTML ────────────────────────────────────────────────────── */
function rowHTML(item) {
  const tick  = TICK[item.symbol] || item.symbol;
  const name  = LABELS[item.symbol] || item.name || item.symbol;
  if (item.unavailable) {
    return `<div class="drow">
      <div class="drow-tick">${tick}</div>
      <div class="drow-name">${name}</div>
      <div class="drow-price">—</div>
      <div class="dpill flat">N/A</div>
    </div>`;
  }
  const price = fmt(item.price, item.symbol);
  const pct   = fmtPct(item.pct);
  const dir   = pillDir(item.pct);
  return `<div class="drow">
    <div class="drow-tick">${tick}</div>
    <div class="drow-name">${name}</div>
    <div class="drow-price">${price}</div>
    <div class="dpill ${dir}">${pct || '—'}</div>
  </div>`;
}

function paint(id, items) {
  const node = el(id);
  if (!node) return;
  if (!items || !items.length) { node.innerHTML = `<div class="derr">Data unavailable</div>`; return; }
  node.innerHTML = items.map(rowHTML).join('');
}

function setTs(id, ts) {
  const node = el(id);
  if (node && ts) node.textContent = `Updated ${tsFmt(ts)}`;
}

/* ── Bonds card ──────────────────────────────────────────────────── */
function renderBonds(bonds, ts) {
  const node = el('bonds-rows');
  if (!node) return;
  if (!bonds || !bonds.available) {
    node.innerHTML = `<div class="dunavail">
      <div class="dunavail-label">Treasury yield data unavailable</div>
      <div class="dunavail-note">US 10Y and 2Y yields are not provided by this data source. Yield commentary is included in every issue of The Brief.</div>
    </div>`;
    return;
  }
  node.innerHTML = bonds.items.map(rowHTML).join('');
  if (bonds.spread != null) {
    node.insertAdjacentHTML('beforeend', `
      <div class="dbonds-spread">
        <span class="dbonds-spread-label">10Y – 2Y Spread</span>
        <span class="dbonds-spread-val">${bonds.spread >= 0 ? '+' : ''}${bonds.spread.toFixed(3)}%</span>
      </div>`);
  }
  setTs('ts-bonds', ts);
}

/* ── Sentiment gauge ─────────────────────────────────────────────── */
function renderSentiment(sentiment, ts) {
  const node = el('sentiment-panel');
  if (!node) return;
  if (!sentiment) { node.innerHTML = `<div class="derr">Sentiment data unavailable</div>`; return; }

  const { score, vix } = sentiment;

  let label, color, desc;
  if      (score >= 80) { label = 'Extreme Greed'; color = '#34d399'; desc = 'Markets calm. Complacency risk elevated as VIX sits historically low.'; }
  else if (score >= 60) { label = 'Greed';         color = '#86efac'; desc = 'Risk appetite above average. Equities generally well-bid.'; }
  else if (score >= 40) { label = 'Neutral';        color = '#fbbf24'; desc = 'Near historical average. No strong directional bias.'; }
  else if (score >= 20) { label = 'Fear';           color = '#fb923c'; desc = 'Elevated uncertainty. Defensive positioning increasing.'; }
  else                  { label = 'Extreme Fear';   color = '#f87171'; desc = 'Significant market stress. Sharp moves and volatility expected.'; }

  const cx = 100, cy = 105, r = 78;
  const toRad = (a) => (a * Math.PI) / 180;

  // Needle: 180° = left (Extreme Fear), 0° = right (Extreme Greed)
  const needleAngle = 180 - (score / 100) * 180;
  const nx = cx + (r - 10) * Math.cos(toRad(needleAngle));
  const ny = cy - (r - 10) * Math.sin(toRad(needleAngle));

  // Build 5 colored arc segments (each 36° = 180°/5 zones)
  const zones = [
    { color: '#f87171', from: 180, to: 144 }, // 0–20: Extreme Fear
    { color: '#fb923c', from: 144, to: 108 }, // 20–40: Fear
    { color: '#fbbf24', from: 108, to:  72 }, // 40–60: Neutral
    { color: '#86efac', from:  72, to:  36 }, // 60–80: Greed
    { color: '#34d399', from:  36, to:   0 }, // 80–100: Extreme Greed
  ];

  function arcPath(fromDeg, toDeg) {
    const x1 = cx + r * Math.cos(toRad(fromDeg));
    const y1 = cy - r * Math.sin(toRad(fromDeg));
    const x2 = cx + r * Math.cos(toRad(toDeg));
    const y2 = cy - r * Math.sin(toRad(toDeg));
    return `M${x1},${y1} A${r},${r} 0 0 1 ${x2},${y2}`;
  }

  const arcPaths = zones.map(z =>
    `<path d="${arcPath(z.from, z.to)}" stroke="${z.color}" stroke-width="9" fill="none" stroke-linecap="butt" opacity="0.75"/>`
  ).join('');

  node.innerHTML = `
    <div class="dgauge-svg-wrap">
      <svg viewBox="0 0 200 115" xmlns="http://www.w3.org/2000/svg">
        <!-- Dim track -->
        <path d="M${cx-r},${cy} A${r},${r} 0 0 1 ${cx+r},${cy}"
          stroke="rgba(255,255,255,0.05)" stroke-width="9" fill="none" stroke-linecap="butt"/>
        <!-- Colored zones -->
        ${arcPaths}
        <!-- Needle -->
        <line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}"
          stroke="#fff" stroke-width="2" stroke-linecap="round" opacity="0.9"/>
        <circle cx="${cx}" cy="${cy}" r="4.5" fill="${color}"/>
        <circle cx="${cx}" cy="${cy}" r="2"   fill="#0a0c10"/>
        <!-- Zone labels -->
        <text x="10"  y="114" font-size="7" fill="rgba(255,255,255,0.22)" font-family="monospace">Ext. Fear</text>
        <text x="155" y="114" font-size="7" fill="rgba(255,255,255,0.22)" font-family="monospace">Ext. Greed</text>
      </svg>
    </div>
    <div class="dgauge-number" style="color:${color}">${score}</div>
    <div class="dgauge-label" style="color:${color}">${label}</div>
    <div class="dgauge-desc">${desc}</div>
    <div class="dgauge-note">Proxy from VIX ${vix != null ? `(${vix.toFixed(2)})` : ''} · Not the CNN Fear &amp; Greed Index</div>`;
  setTs('ts-sentiment', ts);
}

/* ── Overview load ───────────────────────────────────────────────── */
async function loadOverview() {
  const SKELS = { 'indices-rows': 5, 'mag7-rows': 7, 'crypto-rows': 4, 'commodities-rows': 3, 'energy-rows': 3, 'forex-rows': 5 };
  Object.entries(SKELS).forEach(([id, n]) => {
    const node = el(id); if (node) node.innerHTML = skeletons(n);
  });

  const statusEl  = el('dash-status');
  const updatedEl = el('dash-updated');

  try {
    const res  = await fetch('/api/market-data?type=overview');
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'API error');

    const ts = data.timestamp;

    paint('indices-rows',     data.indices);     setTs('ts-indices',     ts);
    paint('mag7-rows',        data.mag7);         setTs('ts-mag7',        ts);
    paint('crypto-rows',      data.crypto);       setTs('ts-crypto',      ts);
    paint('commodities-rows', data.commodities);  setTs('ts-commodities', ts);
    paint('energy-rows',      data.energy);       setTs('ts-energy',      ts);
    paint('forex-rows',       data.forex);        setTs('ts-forex',       ts);

    renderBonds(data.bonds, ts);
    renderSentiment(data.sentiment, ts);

    if (statusEl) { statusEl.className = 'd-status-dot live'; statusEl.textContent = 'Market data loaded'; }
    if (updatedEl && ts) updatedEl.textContent = `As of ${tsFmt(ts)} · May be delayed`;

  } catch (_) {
    ['indices-rows','mag7-rows','crypto-rows','commodities-rows','energy-rows','forex-rows'].forEach(id => {
      const node = el(id); if (node) node.innerHTML = `<div class="derr">Data unavailable — try refreshing</div>`;
    });
    const sp = el('sentiment-panel'); if (sp) sp.innerHTML = `<div class="derr">Data unavailable</div>`;
    const br = el('bonds-rows');      if (br) br.innerHTML = `<div class="derr">Data unavailable</div>`;
    if (statusEl) { statusEl.className = 'd-status-dot err'; statusEl.textContent = 'Market data unavailable — try refreshing'; }
  }
}

/* ── Stock chart ─────────────────────────────────────────────────── */
const RANGES = {
  '1D':  { interval: '5min',  outputsize: 80  },
  '5D':  { interval: '1h',    outputsize: 40  },
  '1M':  { interval: '1day',  outputsize: 23  },
  '3M':  { interval: '1day',  outputsize: 66  },
  '6M':  { interval: '1day',  outputsize: 130 },
  'YTD': { interval: '1day',  outputsize: 180 },
  '1Y':  { interval: '1day',  outputsize: 252 },
  'MAX': { interval: '1week', outputsize: 500 },
};

let chartInst   = null;
let activeRange = '1Y';
let activeSym   = null;

async function fetchChart(symbol, range) {
  const { interval, outputsize } = RANGES[range] || RANGES['1Y'];
  const res  = await fetch(`/api/market-data?type=chart&symbol=${encodeURIComponent(symbol)}&interval=${interval}&outputsize=${outputsize}`);
  const data = await res.json();
  if (!res.ok || data.error) throw new Error(data.error || 'Chart data unavailable');
  return data.values || [];
}

function renderChart(values, isUp) {
  const canvas = document.getElementById('stock-chart');
  if (!canvas) return;

  if (chartInst) { chartInst.destroy(); chartInst = null; }

  const ctx    = canvas.getContext('2d');
  const labels = values.map(v => v.t);
  const prices = values.map(v => v.c);
  const color  = isUp ? '#34d399' : '#f87171';

  const grad = ctx.createLinearGradient(0, 0, 0, canvas.offsetHeight || 280);
  grad.addColorStop(0, isUp ? 'rgba(52,211,153,0.18)' : 'rgba(248,113,113,0.18)');
  grad.addColorStop(1, 'rgba(0,0,0,0)');

  chartInst = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data:            prices,
        borderColor:     color,
        borderWidth:     1.5,
        fill:            true,
        backgroundColor: grad,
        pointRadius:     0,
        tension:         0.2,
      }],
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      animation:           { duration: 300 },
      interaction:         { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1c2330',
          borderColor:     'rgba(255,255,255,0.1)',
          borderWidth:     1,
          titleColor:      'rgba(232,237,245,0.5)',
          bodyColor:       '#e8edf5',
          titleFont:       { family: "'DM Mono', monospace", size: 10 },
          bodyFont:        { family: "'DM Mono', monospace", size: 12 },
          callbacks: {
            title: (items) => items[0]?.label || '',
            label: (item)  => `  ${item.raw != null ? item.raw.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'}`,
          },
        },
      },
      scales: {
        x: {
          display: true,
          ticks: {
            color:       'rgba(232,237,245,0.2)',
            font:        { family: "'DM Mono', monospace", size: 9 },
            maxTicksLimit: 6,
            maxRotation: 0,
          },
          grid:  { color: 'rgba(255,255,255,0.03)' },
          border: { color: 'transparent' },
        },
        y: {
          display: true,
          position: 'right',
          ticks: {
            color:  'rgba(232,237,245,0.2)',
            font:   { family: "'DM Mono', monospace", size: 9 },
            maxTicksLimit: 5,
            callback: (v) => v.toLocaleString('en-US', { maximumFractionDigits: 2 }),
          },
          grid:  { color: 'rgba(255,255,255,0.03)' },
          border: { color: 'transparent' },
        },
      },
    },
  });
}

async function loadChart(symbol, range) {
  const chartBox = document.getElementById('chart-box');
  if (!chartBox) return;

  // Show loading overlay
  let loader = chartBox.querySelector('.dchartbox-loading');
  if (!loader) {
    loader = document.createElement('div');
    loader.className = 'dchartbox-loading';
    chartBox.appendChild(loader);
  }
  loader.textContent = 'Loading chart…';
  loader.style.display = 'flex';

  // Update active range button
  document.querySelectorAll('.drange-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.range === range);
  });

  try {
    const values = await fetchChart(symbol, range);
    loader.style.display = 'none';
    if (!values.length) { loader.textContent = 'Chart data unavailable'; loader.style.display = 'flex'; return; }
    const first = values[0]?.c;
    const last  = values[values.length - 1]?.c;
    renderChart(values, last >= first);
  } catch {
    loader.textContent = 'Chart data unavailable';
    loader.style.display = 'flex';
  }
}

/* ── Stock quote lookup ──────────────────────────────────────────── */
async function lookupStock(symbol) {
  const resultEl = el('search-result');
  if (!resultEl) return;
  resultEl.innerHTML = `<div class="dash-search-loading">Looking up ${symbol}…</div>`;
  activeSym = symbol;

  try {
    const res  = await fetch(`/api/market-data?type=quote&symbol=${encodeURIComponent(symbol)}`);
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Symbol not found');

    const dir     = pillDir(data.pct);
    const pct     = fmtPct(data.pct);
    const sign    = (data.change || 0) >= 0 ? '+' : '';
    const dec     = decimals(data.price, data.symbol);
    const fmtQ    = v => v != null ? v.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec }) : '—';
    const chgAbs  = data.change != null ? `${sign}${Math.abs(data.change).toFixed(dec > 2 ? 4 : 2)}` : null;

    const rangeButtons = Object.keys(RANGES).map(r =>
      `<button class="drange-btn${r === activeRange ? ' active' : ''}" data-range="${r}">${r}</button>`
    ).join('');

    const stats = [
      { label: 'Open',      val: fmtQ(data.open) },
      { label: 'Day High',  val: fmtQ(data.high) },
      { label: 'Day Low',   val: fmtQ(data.low)  },
      { label: 'Prev Close',val: fmtQ(data.prev_close) },
      { label: '52W High',  val: fmtQ(data.wk52_high)  },
      { label: '52W Low',   val: fmtQ(data.wk52_low)   },
      { label: 'Market Cap',val: '—' },
      { label: 'P/E Ratio', val: '—' },
    ].filter(s => s.val !== '—' || s.label === 'Market Cap' || s.label === 'P/E Ratio');

    resultEl.innerHTML = `
      <div class="dquote-top">
        <div>
          <span class="dquote-sym">${data.symbol}</span>
          ${data.name ? `<span class="dquote-name">${data.name}</span>` : ''}
        </div>
        ${data.exchange ? `<span class="dquote-exch">${data.exchange}</span>` : ''}
      </div>
      <div class="dquote-main">
        <span class="dquote-price">${fmtQ(data.price)}</span>
        ${chgAbs && pct ? `<span class="dquote-chg ${dir}">${chgAbs} &nbsp; ${pct}</span>` : ''}
      </div>
      <div class="drange-bar" id="range-bar">${rangeButtons}</div>
      <div class="dchartbox" id="chart-box">
        <canvas id="stock-chart"></canvas>
        <div class="dchartbox-loading">Loading chart…</div>
      </div>
      <div class="dstats">
        ${stats.map(s => `<div class="dstat"><div class="dstat-label">${s.label}</div><div class="dstat-val">${s.val}</div></div>`).join('')}
      </div>
      <div style="margin-top:12px;font-family:var(--mono);font-size:8px;letter-spacing:.08em;color:var(--muted-2);text-align:center;">
        Market data may be delayed &middot; Not investment advice
      </div>`;

    // Wire up range buttons
    document.getElementById('range-bar')?.addEventListener('click', e => {
      const btn = e.target.closest('.drange-btn');
      if (!btn) return;
      activeRange = btn.dataset.range;
      loadChart(activeSym, activeRange);
    });

    // Load initial chart
    await loadChart(symbol, activeRange);

  } catch (err) {
    resultEl.innerHTML = `<div class="derr">${err.message || 'Symbol not found or unavailable'}</div>`;
  }
}

/* ── Search init ─────────────────────────────────────────────────── */
function initSearch() {
  const input = el('search-input');
  const btn   = el('search-go');
  if (!input || !btn) return;

  const go = () => {
    const sym = input.value.trim().toUpperCase().replace(/[^A-Z0-9./-]/g, '').slice(0, 12);
    if (sym) { activeRange = '1Y'; lookupStock(sym); }
  };

  btn.addEventListener('click', go);
  input.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
}

/* ── Boot ────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  loadOverview();
  initSearch();
});
