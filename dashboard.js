/* The Brief — Market Dashboard JS
   No API keys. No live data. Sample data only.
   All prices are illustrative and clearly labeled as sample data.
*/

/* ── Sample stock database (clearly labeled, not live) ─────────── */
const SAMPLE_STOCKS = [
  { ticker:'AAPL',  name:'Apple Inc.',             price:'198.40', chg:'+2.1%',  dir:'up'  },
  { ticker:'MSFT',  name:'Microsoft Corp.',         price:'432.60', chg:'+0.8%',  dir:'up'  },
  { ticker:'NVDA',  name:'NVIDIA Corp.',            price:'128.90', chg:'+3.2%',  dir:'up'  },
  { ticker:'AMZN',  name:'Amazon.com Inc.',         price:'196.30', chg:'+1.5%',  dir:'up'  },
  { ticker:'GOOGL', name:'Alphabet Inc.',           price:'178.40', chg:'−0.4%',  dir:'dn'  },
  { ticker:'META',  name:'Meta Platforms',          price:'523.80', chg:'+1.9%',  dir:'up'  },
  { ticker:'TSLA',  name:'Tesla Inc.',              price:'248.60', chg:'−1.2%',  dir:'dn'  },
  { ticker:'JPM',   name:'JPMorgan Chase',          price:'218.40', chg:'+0.6%',  dir:'up'  },
  { ticker:'GS',    name:'Goldman Sachs',           price:'462.10', chg:'+0.9%',  dir:'up'  },
  { ticker:'BAC',   name:'Bank of America',         price:'41.80',  chg:'+0.4%',  dir:'up'  },
  { ticker:'WFC',   name:'Wells Fargo',             price:'58.20',  chg:'−0.2%',  dir:'dn'  },
  { ticker:'MS',    name:'Morgan Stanley',          price:'98.60',  chg:'+0.7%',  dir:'up'  },
  { ticker:'XOM',   name:'Exxon Mobil',             price:'112.30', chg:'−0.8%',  dir:'dn'  },
  { ticker:'CVX',   name:'Chevron Corp.',           price:'153.40', chg:'−0.5%',  dir:'dn'  },
  { ticker:'V',     name:'Visa Inc.',               price:'276.80', chg:'+0.3%',  dir:'up'  },
  { ticker:'MA',    name:'Mastercard Inc.',         price:'474.20', chg:'+0.4%',  dir:'up'  },
  { ticker:'BRK',   name:'Berkshire Hathaway B',   price:'458.90', chg:'+0.1%',  dir:'up'  },
  { ticker:'LLY',   name:'Eli Lilly',               price:'812.40', chg:'+1.6%',  dir:'up'  },
  { ticker:'UNH',   name:'UnitedHealth Group',      price:'538.20', chg:'−0.3%',  dir:'dn'  },
  { ticker:'INTC',  name:'Intel Corp.',             price:'34.80',  chg:'+8.4%',  dir:'up'  },
];

/* ── Stock search ───────────────────────────────────────────────── */
function initSearch() {
  const input = document.getElementById('stock-search-input');
  const btn   = document.getElementById('stock-search-btn');
  const results = document.getElementById('stock-search-results');

  if (!input || !btn || !results) return;

  function runSearch() {
    const q = input.value.trim().toUpperCase();
    if (!q) {
      results.innerHTML = '<div class="dash-search-empty">Type a ticker — e.g. AAPL, MSFT, NVDA</div>';
      return;
    }
    const hits = SAMPLE_STOCKS.filter(s =>
      s.ticker.startsWith(q) || s.name.toUpperCase().includes(q)
    ).slice(0, 8);

    if (!hits.length) {
      results.innerHTML = '<div class="dash-search-empty">No match — only sample tickers available</div>';
      return;
    }

    results.innerHTML = hits.map(s => `
      <div class="dash-search-result-row">
        <span class="dash-search-ticker">${s.ticker}</span>
        <span class="dash-search-name">${s.name}</span>
        <span class="dash-search-price">$${s.price}</span>
        <span class="dash-search-chg ${s.dir}">${s.chg}</span>
      </div>
    `).join('');
  }

  btn.addEventListener('click', runSearch);
  input.addEventListener('keydown', e => { if (e.key === 'Enter') runSearch(); });
  input.addEventListener('input', () => {
    if (input.value.trim().length >= 1) runSearch();
    else results.innerHTML = '<div class="dash-search-empty">Type a ticker — e.g. AAPL, MSFT, NVDA</div>';
  });
}

/* ── Fear & Greed gauge (SVG arc) ───────────────────────────────── */
function initGauge() {
  const svg    = document.getElementById('gauge-svg');
  const needle = document.getElementById('gauge-needle');
  if (!svg || !needle) return;

  const VALUE = 58; // static sample value
  const cx = 110, cy = 100, r = 80;

  /* Convert gauge value (0-100) to SVG angle.
     The arc runs from 180° (left) to 0° (right), so:
     angle = 180 - (value/100 * 180) */
  function valToAngle(v) { return 180 - (v / 100) * 180; }

  /* Draw coloured arc background */
  const zones = [
    { from:0,  to:25,  color:'#dc2626' },
    { from:25, to:45,  color:'#f97316' },
    { from:45, to:55,  color:'#eab308' },
    { from:55, to:75,  color:'#84cc16' },
    { from:75, to:100, color:'#22c55e' },
  ];

  function polar(angle, radius) {
    const rad = (angle * Math.PI) / 180;
    return { x: cx + radius * Math.cos(rad), y: cy - radius * Math.sin(rad) };
  }

  function arcPath(fromV, toV, outerR, innerR) {
    const a1 = valToAngle(fromV);
    const a2 = valToAngle(toV);
    const o1 = polar(a1, outerR), o2 = polar(a2, outerR);
    const i1 = polar(a1, innerR), i2 = polar(a2, innerR);
    const large = (a1 - a2) > 180 ? 1 : 0;
    return [
      `M ${o1.x} ${o1.y}`,
      `A ${outerR} ${outerR} 0 ${large} 0 ${o2.x} ${o2.y}`,
      `L ${i2.x} ${i2.y}`,
      `A ${innerR} ${innerR} 0 ${large} 1 ${i1.x} ${i1.y}`,
      'Z'
    ].join(' ');
  }

  const arcsG = document.getElementById('gauge-arcs');
  zones.forEach(z => {
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', arcPath(z.from, z.to, r, r - 20));
    path.setAttribute('fill', z.color);
    path.setAttribute('opacity', '0.75');
    arcsG.appendChild(path);
  });

  /* Animate needle */
  const targetAngle = valToAngle(VALUE);
  let current = 180;
  const step = () => {
    current += (targetAngle - current) * 0.08;
    const rad = (current * Math.PI) / 180;
    const tx = cx + (r - 8) * Math.cos(rad);
    const ty = cy - (r - 8) * Math.sin(rad);
    needle.setAttribute('x2', tx);
    needle.setAttribute('y2', ty);
    if (Math.abs(current - targetAngle) > 0.3) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/* ── Init ───────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  initSearch();
  initGauge();

  /* Default search placeholder */
  const results = document.getElementById('stock-search-results');
  if (results) {
    results.innerHTML = '<div class="dash-search-empty">Type a ticker — e.g. AAPL, MSFT, NVDA</div>';
  }
});
