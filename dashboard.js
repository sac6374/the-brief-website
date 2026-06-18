/* The Brief — Market Dashboard
   All market data fetched via /api/market-data (Cloudflare Pages Function proxy).
   No API keys in this file. No hardcoded prices. */

const LABELS = {
  SPX:        'S&P 500',
  IXIC:       'Nasdaq',
  DJI:        'Dow Jones',
  RUT:        'Russell 2000',
  VIX:        'CBOE VIX',
  'EUR/USD':  'Euro / US Dollar',
  'USD/JPY':  'US Dollar / Yen',
  'GBP/USD':  'Sterling / US Dollar',
  DXY:        'US Dollar Index',
  'BTC/USD':  'Bitcoin',
  'ETH/USD':  'Ethereum',
  'XAU/USD':  'Gold (spot)',
  'XAG/USD':  'Silver (spot)',
  'WTI/USD':  'WTI Crude Oil',
  'BRNT/USD': 'Brent Crude Oil',
};

/* Decimal places by price magnitude */
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

/* Build a data row using existing .dash-row CSS classes */
function rowHTML(item) {
  const label    = LABELS[item.symbol] || item.name || item.symbol;
  const price    = fmtPrice(item.price, item.symbol);
  const pctStr   = fmtPct(item.pct);
  const dir      = item.pct == null ? 'flat' : (item.pct >= 0 ? 'up' : 'dn');
  const arrow    = dir === 'up' ? '▲' : dir === 'dn' ? '▼' : '';
  const chgText  = pctStr ? `${arrow}&nbsp;${pctStr}` : '—';

  return `
    <div class="dash-row">
      <div>
        <div class="dash-row-name">${item.symbol}</div>
        <div class="dash-row-sub">${label}</div>
      </div>
      <div class="dash-row-val">${price}</div>
      <div class="dash-row-chg ${dir}">${chgText}</div>
    </div>`;
}

function skeletonHTML(n) {
  return Array(n).fill('<div class="dash-row dash-skeleton-row"><div class="dash-skeleton"></div><div class="dash-skeleton dash-skeleton-sm"></div><div class="dash-skeleton dash-skeleton-sm"></div></div>').join('');
}

function unavailRowHTML(sym) {
  return `
    <div class="dash-row">
      <div>
        <div class="dash-row-name">${sym}</div>
      </div>
      <div class="dash-row-val" style="color:var(--d-muted-2)">—</div>
      <div class="dash-row-chg flat">Unavailable</div>
    </div>`;
}

function errBlock(msg = 'Market data unavailable right now') {
  return `<div class="dash-err-block">${msg}</div>`;
}

function paint(id, items, skeletonCount) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!items || !items.length) { el.innerHTML = errBlock(); return; }
  el.innerHTML = items.map(i => i.unavailable ? unavailRowHTML(i.symbol) : rowHTML(i)).join('');
}

function setSkeletons() {
  const map = { 'indices-rows': 5, 'mag7-rows': 7, 'forex-rows': 4, 'crypto-rows': 2, 'commodities-rows': 4 };
  Object.entries(map).forEach(([id, n]) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = skeletonHTML(n);
  });
}

/* ── VIX volatility panel ───────────────────────────────────── */
function renderVix(price) {
  const el = document.getElementById('vix-panel');
  if (!el) return;

  let label, color, desc;
  if      (price < 15) { label = 'Low Volatility';     color = '#22c55e'; desc = 'Markets calm. Historically a low-fear environment.'; }
  else if (price < 20) { label = 'Moderate';           color = '#84cc16'; desc = 'Near historical average. No obvious stress signals.'; }
  else if (price < 25) { label = 'Elevated';           color = '#facc15'; desc = 'Above-average volatility. Markets pricing in uncertainty.'; }
  else if (price < 35) { label = 'High Volatility';    color = '#f97316'; desc = 'Significant market stress. Large daily moves expected.'; }
  else                 { label = 'Extreme Volatility'; color = '#f05252'; desc = 'Extreme fear in the market. Historical spikes often signal capitulation.'; }

  el.innerHTML = `
    <div class="dash-vix-number" style="color:${color}">${fmtPrice(price, 'VIX')}</div>
    <div class="dash-vix-label" style="color:${color}">${label}</div>
    <div class="dash-vix-desc">${desc}</div>
    <div class="dash-vix-note">CBOE VIX Index — measures 30-day implied volatility of the S&amp;P 500</div>`;
}

/* ── Main load ──────────────────────────────────────────────── */
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

    if (statusEl) statusEl.innerHTML = '<span class="dash-status-live">&#x25CF;&nbsp;Market data loaded</span>';
    if (updatedEl && data.timestamp) {
      const t = new Date(data.timestamp);
      updatedEl.textContent = `As of ${t.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })} · May be delayed`;
    }
  } catch (err) {
    ['indices-rows', 'mag7-rows', 'forex-rows', 'crypto-rows', 'commodities-rows'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = errBlock();
    });
    const vp = document.getElementById('vix-panel');
    if (vp) vp.innerHTML = errBlock();
    if (statusEl) statusEl.innerHTML = '<span class="dash-status-err">&#x25CB;&nbsp;Market data unavailable — try refreshing</span>';
  }
}

/* ── Stock lookup ───────────────────────────────────────────── */
async function lookupStock(symbol) {
  const el = document.getElementById('stock-result');
  if (!el) return;
  el.innerHTML = '<div class="dash-search-loading">Loading…</div>';

  try {
    const res  = await fetch(`/api/market-data?type=quote&symbol=${encodeURIComponent(symbol)}`);
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Symbol not found');

    const dir  = data.pct == null ? 'flat' : (data.pct >= 0 ? 'up' : 'dn');
    const pct  = fmtPct(data.pct);
    const sign = (data.change || 0) >= 0 ? '+' : '';
    const dec  = decimals(data.price, data.symbol);
    const fmt  = v => v != null ? v.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec }) : '—';

    const chgAbs = data.change != null
      ? `${sign}${Math.abs(data.change) < 0.001 ? data.change.toFixed(4) : data.change.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : null;

    el.innerHTML = `
      <div class="dash-quote-card">
        <div class="dash-quote-header">
          <div class="dash-quote-id">
            <span class="dash-quote-sym">${data.symbol}</span>
            ${data.name ? `<span class="dash-quote-name">${data.name}</span>` : ''}
          </div>
          ${data.exchange ? `<span class="dash-quote-exch">${data.exchange}</span>` : ''}
        </div>
        <div class="dash-quote-main">
          <span class="dash-quote-price">${fmt(data.price)}</span>
          ${chgAbs && pct ? `<span class="dash-quote-chg ${dir}">${chgAbs}&nbsp;&nbsp;${pct}</span>` : ''}
        </div>
        <div class="dash-quote-stats">
          ${data.open       != null ? `<div class="dash-quote-stat"><span>Open</span><span>${fmt(data.open)}</span></div>`       : ''}
          ${data.high       != null ? `<div class="dash-quote-stat"><span>High</span><span>${fmt(data.high)}</span></div>`       : ''}
          ${data.low        != null ? `<div class="dash-quote-stat"><span>Low</span><span>${fmt(data.low)}</span></div>`        : ''}
          ${data.prev_close != null ? `<div class="dash-quote-stat"><span>Prev&nbsp;Close</span><span>${fmt(data.prev_close)}</span></div>` : ''}
        </div>
        <div class="dash-quote-footer">Market data may be delayed &middot; Not investment advice</div>
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
