# src/app.py — Volatility Infrastructure Platform
import subprocess, sys, json, os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(title="Vol Platform")

# === Data store en mémoire ===
CACHE = {}

def fetch_symbol(symbol):
    """Lance un script Python séparé pour récupérer les données IBKR"""
    script = f"""
import json, sys
import nest_asyncio
nest_asyncio.apply()
from ib_insync import *
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq
import pandas as pd

R = 0.043

def bs_price(S, K, T, r, sigma, right='C'):
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    if right == 'C':
        return float(S*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2))
    else:
        return float(K*np.exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1))

def implied_vol(market_price, S, K, T, r, right='C'):
    try:
        return float(brentq(lambda sig: bs_price(S, K, T, r, sig, right) - market_price, 0.001, 5.0, xtol=1e-6))
    except:
        return None

def bs_greeks(S, K, T, r, sigma, right='C'):
    if T <= 0 or sigma <= 0:
        return None
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    if right == 'C':
        delta = float(norm.cdf(d1))
    else:
        delta = float(norm.cdf(d1) - 1)
    gamma = float(norm.pdf(d1) / (S * sigma * np.sqrt(T)))
    vega = float(S * norm.pdf(d1) * np.sqrt(T) / 100)
    theta = float((-(S * norm.pdf(d1) * sigma) / (2*np.sqrt(T)) - r*K*np.exp(-r*T)*norm.cdf(d2 if right == 'C' else -d2)) / 365)
    return {{'delta': delta, 'gamma': gamma, 'vega': vega, 'theta': theta}}

util.startLoop()
ib = IB()
ib.connect('127.0.0.1', 4002, clientId=99)
ib.reqMarketDataType(3)

symbol = '{symbol}'
contract = Stock(symbol, 'SMART', 'USD')
ib.qualifyContracts(contract)

ticker = ib.reqMktData(contract, '', False, False)
ib.sleep(3)
spot = ticker.last if ticker.last > 0 else ticker.close
ib.cancelMktData(contract)

chains = ib.reqSecDefOptParams(contract.symbol, '', contract.secType, contract.conId)
chain = next((c for c in chains if c.exchange == 'SMART'), None)

expirations = [e for e in sorted(chain.expirations) if e >= pd.Timestamp.now().strftime('%Y%m%d')][:3]
strikes = [s for s in sorted(chain.strikes) if spot * 0.90 <= s <= spot * 1.10]

option_contracts = []
for exp in expirations:
    for strike in strikes:
        for right in ['C', 'P']:
            option_contracts.append(Option(symbol, exp, strike, right, 'SMART', multiplier='100'))

qualified = []
for i in range(0, len(option_contracts), 50):
    batch = option_contracts[i:i+50]
    ib.qualifyContracts(*batch)
    qualified.extend([c for c in batch if c.conId > 0])
    ib.sleep(0.5)

option_data = []
for i in range(0, len(qualified), 50):
    batch = qualified[i:i+50]
    tickers = [ib.reqMktData(c, '', False, False) for c in batch]
    ib.sleep(5)
    for t in tickers:
        bid = float(t.bid) if t.bid > 0 else None
        ask = float(t.ask) if t.ask > 0 else None
        mid = (bid + ask) / 2 if bid and ask else None
        iv_val = None
        greeks = None
        if mid and mid > 0:
            exp_date = pd.Timestamp(t.contract.lastTradeDateOrContractMonth)
            T = max((exp_date - pd.Timestamp.now()).days / 365.0, 0.001)
            iv_val = implied_vol(mid, spot, t.contract.strike, T, R, t.contract.right)
            if iv_val:
                greeks = bs_greeks(spot, t.contract.strike, T, R, iv_val, t.contract.right)
        option_data.append({{
            'expiry': t.contract.lastTradeDateOrContractMonth,
            'strike': float(t.contract.strike),
            'right': t.contract.right,
            'bid': bid, 'ask': ask, 'mid': mid,
            'iv': round(iv_val, 4) if iv_val else None,
            'delta': round(greeks['delta'], 4) if greeks else None,
            'gamma': round(greeks['gamma'], 6) if greeks else None,
            'vega': round(greeks['vega'], 4) if greeks else None,
            'theta': round(greeks['theta'], 4) if greeks else None,
        }})
        ib.cancelMktData(t.contract)

ib.disconnect()
print(json.dumps({{'symbol': symbol, 'spot': float(spot), 'options': option_data}}))
"""
    result = subprocess.run(
        [sys.executable, '-c', script],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        return {'error': result.stderr[-500:]}
    
    # Prendre la dernière ligne qui est le JSON
    lines = result.stdout.strip().split('\n')
    for line in reversed(lines):
        try:
            return json.loads(line)
        except:
            continue
    return {'error': 'No valid JSON output'}

# === API Endpoints ===
@app.get("/api/chain/{symbol}")
async def get_chain(symbol: str):
    symbol = symbol.upper()
    print(f"📡 Fetching {symbol}...")
    data = fetch_symbol(symbol)
    CACHE[symbol] = data
    print(f"✅ {symbol} done — {len(data.get('options', []))} options")
    return data

@app.get("/api/spot/{symbol}")
async def get_spot(symbol: str):
    symbol = symbol.upper()
    if symbol in CACHE:
        return {'symbol': symbol, 'spot': CACHE[symbol].get('spot')}
    return {'symbol': symbol, 'spot': None}

# === Frontend HTML ===
@app.get("/", response_class=HTMLResponse)
def frontend():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Volatility Infrastructure Platform</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Segoe UI', sans-serif; background: #0f1117; color: #e0e0e0; }
            .header { background: #1a1d29; padding: 20px 40px; border-bottom: 2px solid #2d7ff9; }
            .header h1 { color: #2d7ff9; font-size: 24px; }
            .controls { padding: 20px 40px; display: flex; gap: 15px; align-items: center; }
            .controls input { background: #1a1d29; border: 1px solid #333; color: white; padding: 10px 15px;
                             border-radius: 6px; font-size: 16px; width: 200px; }
            .controls button { background: #2d7ff9; color: white; border: none; padding: 10px 25px;
                              border-radius: 6px; font-size: 16px; cursor: pointer; }
            .controls button:hover { background: #1a6fe0; }
            .controls button:disabled { background: #555; cursor: wait; }
            .spot-info { padding: 10px 40px; font-size: 18px; }
            .spot-info span { color: #2d7ff9; font-weight: bold; }
            .charts { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; padding: 20px 40px; }
            .chart-box { background: #1a1d29; border-radius: 10px; padding: 15px; }
            #status { color: #888; font-size: 14px; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; }
            th { background: #2d7ff9; color: white; padding: 8px; text-align: right; }
            td { padding: 6px 8px; border-bottom: 1px solid #333; text-align: right; font-size: 13px; }
            tr:hover { background: #1f2233; }
            .section { padding: 20px 40px; }
            h2 { color: #2d7ff9; margin-bottom: 15px; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Volatility Infrastructure Platform &mdash; S&amp;P 500</h1>
        </div>
        <div class="controls">
            <input type="text" id="symbol" placeholder="Ticker (ex: AAPL)" value="AAPL"
                   onkeydown="if(event.key==='Enter') loadData()">
            <button id="btn" onclick="loadData()">Charger</button>
            <span id="status"></span>
        </div>
        <div class="spot-info" id="spotInfo"></div>
        <div class="charts">
            <div class="chart-box"><div id="smileChart"></div></div>
            <div class="chart-box"><div id="deltaChart"></div></div>
            <div class="chart-box"><div id="gammaChart"></div></div>
            <div class="chart-box"><div id="vegaChart"></div></div>
        </div>
        <div class="section">
            <h2>Option Chain</h2>
            <div id="chainTable"></div>
        </div>
        <script>
        async function loadData() {
            const sym = document.getElementById('symbol').value.toUpperCase();
            const btn = document.getElementById('btn');
            btn.disabled = true;
            btn.textContent = '⏳ Loading...';
            document.getElementById('status').textContent = 'Fetching ' + sym + ' from IBKR... (~30-60s)';

            try {
                const res = await fetch('/api/chain/' + sym);
                const data = await res.json();

                if (data.error) {
                    document.getElementById('status').textContent = 'Erreur: ' + data.error;
                    btn.disabled = false; btn.textContent = 'Charger';
                    return;
                }

                document.getElementById('spotInfo').innerHTML =
                    '<span>' + data.symbol + '</span> &mdash; Spot: <span>$' + data.spot?.toFixed(2) + '</span>';

                const opts = data.options.filter(o => o.iv !== null);
                const expiries = [...new Set(opts.map(o => o.expiry))].sort();
                const darkLayout = {
                    paper_bgcolor: '#1a1d29', plot_bgcolor: '#1a1d29',
                    font: {color: '#e0e0e0'}, legend: {font: {size: 10}},
                    margin: {t: 40, b: 40, l: 50, r: 20}
                };

                // Smile
                const smileTraces = [];
                expiries.forEach(exp => {
                    const calls = opts.filter(o => o.expiry === exp && o.right === 'C');
                    smileTraces.push({
                        x: calls.map(o => o.strike), y: calls.map(o => o.iv * 100),
                        name: exp, mode: 'lines+markers', marker: {size: 4}
                    });
                });
                Plotly.newPlot('smileChart', smileTraces, {
                    ...darkLayout, title: 'Volatility Smile',
                    xaxis: {title: 'Strike'}, yaxis: {title: 'IV (%)'}
                });

                // Greeks
                const exp0 = expiries[0];
                const calls0 = opts.filter(o => o.expiry === exp0 && o.right === 'C');

                Plotly.newPlot('deltaChart', [{
                    x: calls0.map(o => o.strike), y: calls0.map(o => o.delta),
                    mode: 'lines+markers', marker: {size: 4, color: '#2d7ff9'}
                }], {...darkLayout, title: 'Delta (Calls)', xaxis: {title: 'Strike'}, yaxis: {title: 'Delta'}, showlegend: false});

                Plotly.newPlot('gammaChart', [{
                    x: calls0.map(o => o.strike), y: calls0.map(o => o.gamma),
                    mode: 'lines+markers', marker: {size: 4, color: '#ff4444'}
                }], {...darkLayout, title: 'Gamma', xaxis: {title: 'Strike'}, yaxis: {title: 'Gamma'}, showlegend: false});

                Plotly.newPlot('vegaChart', [{
                    x: calls0.map(o => o.strike), y: calls0.map(o => o.vega),
                    mode: 'lines+markers', marker: {size: 4, color: '#aa44ff'}
                }], {...darkLayout, title: 'Vega', xaxis: {title: 'Strike'}, yaxis: {title: 'Vega'}, showlegend: false});

                // Table
                let html = '<table><tr><th>Expiry</th><th>Strike</th><th>Type</th><th>Bid</th><th>Ask</th><th>IV</th><th>Delta</th><th>Gamma</th><th>Vega</th><th>Theta</th></tr>';
                opts.forEach(o => {
                    html += '<tr><td>' + o.expiry + '</td><td>' + o.strike + '</td><td>' + o.right + '</td>'
                        + '<td>' + (o.bid !== null ? o.bid.toFixed(2) : '-') + '</td>'
                        + '<td>' + (o.ask !== null ? o.ask.toFixed(2) : '-') + '</td>'
                        + '<td>' + (o.iv * 100).toFixed(1) + '%</td>'
                        + '<td>' + (o.delta !== null ? o.delta.toFixed(3) : '-') + '</td>'
                        + '<td>' + (o.gamma !== null ? o.gamma.toFixed(5) : '-') + '</td>'
                        + '<td>' + (o.vega !== null ? o.vega.toFixed(3) : '-') + '</td>'
                        + '<td>' + (o.theta !== null ? o.theta.toFixed(3) : '-') + '</td></tr>';
                });
                html += '</table>';
                document.getElementById('chainTable').innerHTML = html;

                document.getElementById('status').textContent = '✅ ' + opts.length + ' options loaded';
            } catch(e) {
                document.getElementById('status').textContent = 'Erreur: ' + e.message;
            }
            btn.disabled = false; btn.textContent = 'Charger';
        }
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)