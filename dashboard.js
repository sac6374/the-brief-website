/* The Brief — Market Dashboard
   All market data fetched via /api/market-data (Cloudflare Pages Function proxy).
   No API keys in this file. No hardcoded prices. */

const LABELS = {
  SPX:        'S&P 500',
  IXIC:       'Nasdaq Composite',
  DJI:        'Dow Jones',
  RUT:        'Russell 2000',
  VIX:        'CBOE VIX',
  'EUR/USD':  'Euro / Dollar',
  'USD/JPY':  'Dollar / Yen',
  'GBP/USD':  'Sterling / Dollar',
  DXY:        'US Dollar Index',
  'BTC/USD':  'Bitcoin',
  'ETH/USD':  'Ethereum',
  'XAU/USD':  'Gold (spot)',
  'XAG/USD':  'Silver (spot)',
  'WTI/USD':  'WTI Crude Oil',
  'BRNT/USD': 'Brent Crude',
};

function decimals(price, sym) {
  if (price == null) return 2;
  if ((sym || '').includes('BTC') || price > 10000) return 0;
  if (price > 999) return 2;
  if (price > 9)   return 2;
  if (price > 0.9) return 4;
  return 6;
}

function fmtPrice(price, sym) {
  if (price == null) return '—';
  const d = decimals(price, sym);
  return price.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
}

function fmtPct(pct) {
  if (pct == null) return null;
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${Math.abs(pct) < 0.01 ? pct.toFixed(3) : pct.toFixed(2)}%`;
}

function pillClass(pct) {
  if (pct == null) return 'flat';
  return pct >= 0 ? 'up' : 'dn';
}

function rowHTML(item) {
  const label   = LABELS[item.symbol] || item.name || item.symbol;
  const price   = fmtPrice(item.price, item.symbol);
  const pctStr  = fmtPct(item.pct);
  const dir     = pillClass(item.pct);
  const arrow   = dir === 'up' ? '▲ ' : dir === 'dn' ? '▼ ' : '';
  const chgText = pctStr ? `${arrow}${pctStr}` : '—';

  return `
    <div class="drow">
      <div>
        <div class="drow-name">${label}</div>
        <span class="drow-sym">${item.symbol}</span>
      </div>
      <div class="drow-price">${price}</div>
      <div class="dpill ${dir}">${chgText}</div>
    </div>`;
}

function skeletonHTML(n) {
  return Array(n).fill(`
    <div class="dskel-row">
      <div class="dskel" style="width:55%;"></div>
      <div class="dskel dskel-sm"></div>
      <div class="dskel dskel-sm"></div>
    </div>`).join('');
}

function errBlock(msg) {
  return `<div class="derr">${msg || 'Market data unavailable right now'}</div>`;
}

function paint(id, items) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!items || !items.length) { el.innerHTML = errBlock(); return; }
  el.innerHTML = items.map(i => i.unavailable
    ? `<div class="drow"><div><div class="drow-name">${i.symbol}</div></div><div class="drow-price" style="color:var(--muted-2)">—</div><div class="dpill flat">N/A</div></div>`
    : rowHTML(i)
  ).join('');
}

function setSkeletons() {
  const map = { 'indices-rows': 5, 'mag7-rows': 7, 'forex-rows': 4, 'crypto-rows': 2, 'commodities-rows': 4 };
  Object.entries(map).forEach(([id, n]) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = skeletonHTML(n);
  });
}

/* ── VIX panel ──────────────────────────────────────────────────── */
function renderVix(price) {
  const el = document.getElementById('vix-panel');
  if (!el) return;

  let label, color, desc;
  if      (price < 15) { label = 'Low Volatility';     color = 'var(--green)';   desc = 'Markets calm. Historically a low-fear environment.'; }
  else if (price < 20) { label = 'Moderate';           color = '#84cc16';        desc = 'Near historical average. No obvious stress signals.'; }
  else if (price < 25) { label = 'Elevated';           color = '#facc15';        desc = 'Above-average volatility. Markets pricing in uncertainty.'; }
  else if (price < 35) { label = 'High Volatility';    color = '#f97316';        desc = 'Significant market stress. Large daily moves expected.'; }
  else                 { label = 'Extreme Volatility'; color = 'var(--red)';     desc = 'Extreme fear. Historical spikes often signal capitulation.'; }

  /* Semicircle gauge — arc goes from 210° to 330° (150° sweep) */
  const clamp  = Math.min(Math.max(price, 9), 55);
  const ratio  = (clamp - 9) / (55 - 9);
  const sweep  = 180;
  const startA = 180;
  const endA   = startA + ratio * sweep;
  const toRad  = a => (a * Math.PI) / 180;
  const cx = 90, cy = 90, r = 70;
  const x1 = cx + r * Math.cos(toRad(startA));
  const y1 = cy + r * Math.sin(toRad(startA));
  const x2 = cx + r * Math.cos(toRad(endA));
  const y2 = cy + r * Math.sin(toRad(endA));
  const large = (endA - startA) > 180 ? 1 : 0;

  const gaugeArc = price > 9
    ? `<path d="M${x1},${y1} A${r},${r} 0 ${large} 1 ${x2},${y2}" stroke="${color}" stroke-width="8" fill="none" stroke-linecap="round"/>`
    : '';

  el.innerHTML = `
    <div class="dvix-svg-wrap">
      <svg viewBox="0 0 180 100" xmlns="http://www.w3.org/2000/svg">
        <path d="M${cx-r},${cy} A${r},${r} 0 0 1 ${cx+r},${cy}" stroke="rgba(255,255,255,0.06)" stroke-width="8" fill="none" stroke-linecap="round"/>
        ${gaugeArc}
      </svg>
    </div>
    <div class="dvix-number" style="color:${color}">${fmtPrice(price, 'VIX')}</div>
    <div class="dvix-label" style="color:${color}">${label}</div>
    <div class="dvix-desc">${desc}</div>
    <div class="dvix-note">CBOE VIX &mdash; measures 30-day implied S&amp;P 500 volatility</div>`;
}

/* ── Main load ──────────────────────────────────────────────────── */
async function loadOverview() {
  setSkeletons();

  const statusEl  = document.getElementById('dash-status-text');
  const updatedEl = document.getElementById('dash-updated');

  try {
    const res  = await fetch('/api/market-data?type=overview');
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'API error');

    paint('indices-rows',     data.indices);
    paint('mag7-rows',        data.mag7);
    paint('forex-rows',       data.forex);
    paint('crypto-rows',      data.crypto);
    paint('commodities-rows', data.commodities);

    const vix = (data.indices || []).find(i => i.symbol === 'VIX');
    if (vix && vix.price != null) renderVix(vix.price);
    else {
      const vp = document.getElementById('vix-panel');
      if (vp) vp.innerHTML = errBlock('VIX data unavailable');
    }

    if (statusEl) {
      statusEl.className = 'dash-status-dot live';
      statusEl.textContent = 'Market data loaded';
    }
    if (updatedEl && data.timestamp) {
      const t = new Date(data.timestamp);
      updatedEl.textContent = `As of ${t.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })} · May be delayed`;
    }
  } catch (_) {
    ['indices-rows', 'mag7-rows', 'forex-rows', 'crypto-rows', 'commodities-rows'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = errBlock();
    });
    const vp = document.getElementById('vix-panel');
    if (vp) vp.innerHTML = errBlock();
    if (statusEl) {
      statusEl.className = 'dash-status-dot err';
      statusEl.textContent = 'Market data unavailable — try refreshing';
    }
  }
}

/* ── Stock lookup ───────────────────────────────────────────────── */
async function lookupStock(symbol) {
  const el = document.getElementById('stock-result');
  if (!el) return;
  el.innerHTML = '<div class="dsearch-loading">Loading…</div>';

  try {
    const res  = await fetch(`/api/market-data?type=quote&symbol=${encodeURIComponent(symbol)}`);
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Symbol not found');

    const dir = data.pct == null ? 'flat' : (data.pct >= 0 ? 'up' : 'dn');
    const pct = fmtPct(data.pct);
    const dec = decimals(data.price, data.symbol);
    const fmt = v => v != null ? v.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec }) : '—';
    const sign    = (data.change || 0) >= 0 ? '+' : '';
    const chgAbs  = data.change != null
      ? `${sign}${Math.abs(data.change) < 0.001 ? data.change.toFixed(4) : data.change.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : null;

    el.innerHTML = `
      <div class="dquote">
        <div class="dquote-header">
          <div>
            <span class="dquote-sym">${data.symbol}</span>
            ${data.name ? `<span class="dquote-name">${data.name}</span>` : ''}
          </div>
          ${data.exchange ? `<span class="dquote-exch">${data.exchange}</span>` : ''}
        </div>
        <div class="dquote-main">
          <span class="dquote-price">${fmt(data.price)}</span>
          ${chgAbs && pct ? `<span class="dquote-chg ${dir}">${chgAbs} &nbsp; ${pct}</span>` : ''}
        </div>
        ${(data.open || data.high || data.low || data.prev_close) ? `
        <div class="dquote-stats">
          ${data.open       != null ? `<div class="dquote-stat"><span class="dquote-stat-label">Open</span><span class="dquote-stat-val">${fmt(data.open)}</span></div>` : ''}
          ${data.high       != null ? `<div class="dquote-stat"><span class="dquote-stat-label">High</span><span class="dquote-stat-val">${fmt(data.high)}</span></div>` : ''}
          ${data.low        != null ? `<div class="dquote-stat"><span class="dquote-stat-label">Low</span><span class="dquote-stat-val">${fmt(data.low)}</span></div>` : ''}
          ${data.prev_close != null ? `<div class="dquote-stat"><span class="dquote-stat-label">Prev Close</span><span class="dquote-stat-val">${fmt(data.prev_close)}</span></div>` : ''}
        </div>` : ''}
        <div class="dquote-footer">Market data may be delayed &middot; Not investment advice</div>
      </div>`;
  } catch (err) {
    el.innerHTML = errBlock(err.message || 'Market data unavailable right now');
  }
}

function initSearch() {
  const input = document.getElementById('stock-search-input');
  const btn   = document.getElementById('stock-search-btn');
  if (!input || !btn) return;

  const go = () => {
    const sym = input.value.trim().toUpperCase().replace(/[^A-Z0-9./-]/g, '');
    if (sym) lookupStock(sym);
  };

  btn.addEventListener('click', go);
  input.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
}

document.addEventListener('DOMContentLoaded', () => {
  loadOverview();
  initSearch();
});
