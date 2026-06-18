/* Cloudflare Pages Function — /api/market-data
   Proxies Twelve Data API. API key stored in Cloudflare environment secrets only.
   No secrets are exposed to the browser. */

const TD_BASE     = 'https://api.twelvedata.com';
const INDICES     = ['SPX', 'IXIC', 'DJI', 'RUT', 'VIX'];
const MAG7        = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA'];
const FOREX       = ['EUR/USD', 'USD/JPY', 'GBP/USD', 'DXY'];
const CRYPTO      = ['BTC/USD', 'ETH/USD'];
const COMMODITIES = ['XAU/USD', 'XAG/USD', 'WTI/USD', 'BRNT/USD'];

/* Parse a single Twelve Data quote object into a clean shape */
function parseQ(raw, sym) {
  if (!raw || raw.status === 'error' || raw.code) {
    return { symbol: sym, unavailable: true };
  }
  const price  = parseFloat(raw.close);
  const change = parseFloat(raw.change);
  const pct    = parseFloat(raw.percent_change);
  return {
    symbol:     raw.symbol     || sym,
    name:       raw.name       || sym,
    price:      isNaN(price)   ? null : price,
    change:     isNaN(change)  ? null : change,
    pct:        isNaN(pct)     ? null : pct,
    open:       parseFloat(raw.open)           || null,
    high:       parseFloat(raw.high)           || null,
    low:        parseFloat(raw.low)            || null,
    prev_close: parseFloat(raw.previous_close) || null,
    volume:     raw.volume   || null,
    datetime:   raw.datetime || null,
    exchange:   raw.exchange || null,
    currency:   raw.currency || null,
  };
}

/* Fetch batch quotes from Twelve Data */
async function tdQuote(symbols, apiKey) {
  const url = `${TD_BASE}/quote?symbol=${symbols.join(',')}&apikey=${apiKey}`;
  const r   = await fetch(url, { headers: { 'User-Agent': 'ReadMarketBrief/1.0' } });
  if (!r.ok) throw new Error(`Twelve Data responded ${r.status}`);
  const body = await r.json();
  /* Single symbol → Twelve Data returns the object directly, not wrapped */
  if (symbols.length === 1) return { [symbols[0]]: body };
  return body;
}

export async function onRequest({ env, request }) {
  const url    = new URL(request.url);
  const type   = url.searchParams.get('type')   || 'overview';
  const symbol = url.searchParams.get('symbol') || '';

  const json = (data, status = 200) =>
    new Response(JSON.stringify(data), {
      status,
      headers: {
        'Content-Type':  'application/json',
        'Cache-Control': 'public, max-age=60',
      },
    });

  const apiKey = env.TWELVE_DATA_API_KEY;
  if (!apiKey) return json({ error: 'Market data unavailable — proxy not configured' }, 503);

  try {
    /* ── Single quote lookup ── */
    if (type === 'quote' && symbol) {
      const sym = symbol.toUpperCase().replace(/[^A-Z0-9./-]/g, '').slice(0, 12);
      if (!sym) return json({ error: 'Invalid symbol' }, 400);
      const raw = await tdQuote([sym], apiKey);
      const q   = parseQ(raw[sym] ?? raw, sym);
      if (q.unavailable) return json({ error: 'Symbol not found or unavailable' }, 404);
      return json(q);
    }

    /* ── Dashboard overview ── */
    if (type === 'overview') {
      const b1 = [...INDICES, ...MAG7];
      const b2 = [...FOREX, ...CRYPTO, ...COMMODITIES];

      /* Run both batches in parallel; if one fails the other still renders */
      const [r1, r2] = await Promise.allSettled([
        tdQuote(b1, apiKey),
        tdQuote(b2, apiKey),
      ]);

      const all = {
        ...(r1.status === 'fulfilled' ? r1.value : {}),
        ...(r2.status === 'fulfilled' ? r2.value : {}),
      };

      const get = (s) => parseQ(all[s], s);

      return json({
        timestamp:   new Date().toISOString(),
        indices:     INDICES.map(get),
        mag7:        MAG7.map(get),
        forex:       FOREX.map(get),
        crypto:      CRYPTO.map(get),
        commodities: COMMODITIES.map(get),
        bonds:       null, /* US Treasury yields not available on Twelve Data free tier */
      });
    }

    return json({ error: 'Invalid type parameter' }, 400);

  } catch (err) {
    return json({ error: 'Market data unavailable right now' }, 503);
  }
}
