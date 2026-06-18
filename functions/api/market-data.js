/* Cloudflare Pages Function — /api/market-data
   Proxies Twelve Data API. API key never exposed to browser. */

const TD_BASE = 'https://api.twelvedata.com';

const INDICES     = ['SPX', 'IXIC', 'DJI', 'RUT', 'VIX'];
const MAG7        = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA'];
const FOREX       = ['EUR/USD', 'USD/JPY', 'GBP/USD', 'DXY', 'USD/CAD'];
const CRYPTO      = ['BTC/USD', 'ETH/USD', 'XRP/USD', 'SOL/USD'];
const COMMODITIES = ['XAU/USD', 'XAG/USD', 'XCU/USD'];   // Gold, Silver, Copper
const ENERGY      = ['WTI/USD', 'BRNT/USD', 'NG/USD'];    // WTI, Brent, Nat Gas
const BONDS       = ['US10Y', 'US2Y'];                     // May be unavailable on free tier

function parseQ(raw, sym) {
  if (!raw || raw.status === 'error' || raw.code) return { symbol: sym, unavailable: true };
  const price  = parseFloat(raw.close);
  const change = parseFloat(raw.change);
  const pct    = parseFloat(raw.percent_change);
  const wk52   = raw.fifty_two_week || {};
  return {
    symbol:     raw.symbol || sym,
    name:       raw.name   || sym,
    exchange:   raw.exchange   || null,
    currency:   raw.currency   || null,
    price:      isNaN(price)  ? null : price,
    change:     isNaN(change) ? null : change,
    pct:        isNaN(pct)    ? null : pct,
    open:       parseFloat(raw.open)           || null,
    high:       parseFloat(raw.high)           || null,
    low:        parseFloat(raw.low)            || null,
    prev_close: parseFloat(raw.previous_close) || null,
    wk52_high:  parseFloat(wk52.high) || null,
    wk52_low:   parseFloat(wk52.low)  || null,
    datetime:   raw.datetime || null,
  };
}

async function tdBatch(symbols, apiKey) {
  const url = `${TD_BASE}/quote?symbol=${encodeURIComponent(symbols.join(','))}&apikey=${apiKey}`;
  const r   = await fetch(url, { headers: { 'User-Agent': 'ReadMarketBrief/1.0' } });
  if (!r.ok) throw new Error(`TD ${r.status}`);
  const body = await r.json();
  if (symbols.length === 1) return { [symbols[0]]: body };
  return body;
}

export async function onRequest({ env, request }) {
  const url    = new URL(request.url);
  const type   = url.searchParams.get('type')   || 'overview';
  const symbol = url.searchParams.get('symbol') || '';

  const resp = (data, status = 200) =>
    new Response(JSON.stringify(data), {
      status,
      headers: {
        'Content-Type':  'application/json',
        'Cache-Control': 'public, max-age=60',
      },
    });

  const apiKey = env.TWELVE_DATA_API_KEY;
  if (!apiKey) return resp({ error: 'Market data unavailable — proxy not configured' }, 503);

  try {

    /* ── Chart / time-series ── */
    if (type === 'chart') {
      const sym        = (symbol || '').toUpperCase().replace(/[^A-Z0-9./-]/g, '').slice(0, 12);
      if (!sym) return resp({ error: 'symbol required' }, 400);
      const interval   = url.searchParams.get('interval')   || '1day';
      const outputsize = url.searchParams.get('outputsize') || '252';
      const tdUrl = `${TD_BASE}/time_series?symbol=${encodeURIComponent(sym)}&interval=${interval}&outputsize=${outputsize}&apikey=${apiKey}`;
      const r = await fetch(tdUrl, { headers: { 'User-Agent': 'ReadMarketBrief/1.0' } });
      const d = await r.json();
      if (d.status === 'error' || !Array.isArray(d.values)) {
        return resp({ error: d.message || 'Chart data unavailable' }, 422);
      }
      const values = [...d.values].reverse().map(v => ({
        t: v.datetime,
        c: parseFloat(v.close),
        h: parseFloat(v.high),
        l: parseFloat(v.low),
        o: parseFloat(v.open),
      }));
      return resp({ symbol: sym, interval, values });
    }

    /* ── Single quote ── */
    if (type === 'quote') {
      const sym = (symbol || '').toUpperCase().replace(/[^A-Z0-9./-]/g, '').slice(0, 12);
      if (!sym) return resp({ error: 'symbol required' }, 400);
      const raw  = await tdBatch([sym], apiKey);
      const q    = parseQ(raw[sym] ?? raw, sym);
      if (q.unavailable) return resp({ error: 'Symbol not found or unavailable' }, 404);
      return resp(q);
    }

    /* ── Dashboard overview ── */
    if (type === 'overview') {
      const batch1 = [...INDICES, ...MAG7];
      const batch2 = [...FOREX, ...CRYPTO, ...COMMODITIES, ...ENERGY, ...BONDS];

      const [r1, r2] = await Promise.allSettled([
        tdBatch(batch1, apiKey),
        tdBatch(batch2, apiKey),
      ]);

      const all = {
        ...(r1.status === 'fulfilled' ? r1.value : {}),
        ...(r2.status === 'fulfilled' ? r2.value : {}),
      };

      const get = (s) => parseQ(all[s], s);

      const indicesData = INDICES.map(get);
      const vix = indicesData.find(i => i.symbol === 'VIX' && !i.unavailable);

      // Derive sentiment from VIX. Scale: VIX 8 → score 95, VIX 50 → score 5.
      let sentiment = null;
      if (vix && vix.price != null) {
        const v     = vix.price;
        const score = Math.round(Math.max(5, Math.min(95, 100 - ((v - 8) / 42) * 90)));
        sentiment   = { score, vix: v };
      }

      // Bonds — try to get data; gracefully mark unavailable
      const bondsData  = BONDS.map(get);
      const b10        = bondsData.find(b => b.symbol === 'US10Y' && !b.unavailable);
      const b2y        = bondsData.find(b => b.symbol === 'US2Y'  && !b.unavailable);
      const spread     = (b10 && b2y) ? parseFloat((b10.price - b2y.price).toFixed(3)) : null;

      return resp({
        timestamp:   new Date().toISOString(),
        indices:     indicesData,
        mag7:        MAG7.map(get),
        forex:       FOREX.map(get),
        crypto:      CRYPTO.map(get),
        commodities: COMMODITIES.map(get),
        energy:      ENERGY.map(get),
        bonds: {
          items:  bondsData,
          spread,
          available: !!(b10 || b2y),
        },
        sentiment,
      });
    }

    return resp({ error: 'Invalid type parameter' }, 400);

  } catch (err) {
    return resp({ error: 'Market data unavailable right now' }, 503);
  }
}
