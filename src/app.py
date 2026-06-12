# # src/app.py — Volatility Infrastructure Platform
# # Step 5 du doc: fallback explicite si marché fermé (mid → last → close → snapshot)

# import subprocess, sys, json, os, math, glob
# from datetime import datetime
# from fastapi import FastAPI
# from fastapi.responses import HTMLResponse
# import uvicorn

# app = FastAPI(title="Vol Platform")

# CACHE = {}
# DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw')


# def clean_nan(obj):
#     """Nettoie les NaN/Inf pour serialiser en JSON"""
#     if isinstance(obj, float):
#         if math.isnan(obj) or math.isinf(obj):
#             return None
#         return obj
#     if isinstance(obj, dict):
#         return {k: clean_nan(v) for k, v in obj.items()}
#     if isinstance(obj, list):
#         return [clean_nan(i) for i in obj]
#     return obj


# def get_latest_parquet(symbol):
#     """Trouve le dernier snapshot parquet pour ce symbole"""
#     pattern = os.path.join(DATA_DIR, f'options_{symbol}_*.parquet')
#     files = sorted(glob.glob(pattern))
#     if files:
#         return files[-1]
#     return None


# def fetch_from_ibkr(symbol):
#     """Lance un subprocess pour récupérer les données IBKR en live (delayed)"""
#     script = f"""
# import json, sys, math
# import nest_asyncio
# nest_asyncio.apply()
# from ib_insync import *
# import numpy as np
# from scipy.stats import norm
# from scipy.optimize import brentq
# import pandas as pd

# R = 0.043

# def bs_price(S, K, T, r, sigma, right='C'):
#     d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
#     d2 = d1 - sigma*np.sqrt(T)
#     if right == 'C':
#         return float(S*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2))
#     return float(K*np.exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1))

# def implied_vol(market_price, S, K, T, r, right='C'):
#     try:
#         return float(brentq(lambda sig: bs_price(S, K, T, r, sig, right) - market_price, 0.001, 5.0, xtol=1e-6))
#     except:
#         return None

# def bs_greeks(S, K, T, r, sigma, right='C'):
#     if T <= 0 or sigma <= 0:
#         return None
#     d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
#     d2 = d1 - sigma*np.sqrt(T)
#     delta = float(norm.cdf(d1) if right == 'C' else norm.cdf(d1) - 1)
#     gamma = float(norm.pdf(d1) / (S * sigma * np.sqrt(T)))
#     vega = float(S * norm.pdf(d1) * np.sqrt(T) / 100)
#     theta = float((-(S * norm.pdf(d1) * sigma) / (2*np.sqrt(T)) - r*K*np.exp(-r*T)*norm.cdf(d2 if right == 'C' else -d2)) / 365)
#     return {{'delta': delta, 'gamma': gamma, 'vega': vega, 'theta': theta}}

# def safe(v):
#     if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
#         return None
#     return v

# util.startLoop()
# ib = IB()
# ib.connect('127.0.0.1', 4002, clientId=99)
# ib.reqMarketDataType(3)

# symbol = '{symbol}'
# contract = Stock(symbol, 'SMART', 'USD')
# ib.qualifyContracts(contract)

# ticker = ib.reqMktData(contract, '', False, False)
# ib.sleep(4)

# # Reference spot avec fallback explicite (Step 5 du doc)
# spot = None
# reference_type = None
# if ticker.last and ticker.last > 0 and not math.isnan(ticker.last):
#     spot = float(ticker.last)
#     reference_type = 'last'
# elif ticker.bid and ticker.ask and ticker.bid > 0 and ticker.ask > 0:
#     spot = float((ticker.bid + ticker.ask) / 2)
#     reference_type = 'mid'
# elif ticker.close and ticker.close > 0 and not math.isnan(ticker.close):
#     spot = float(ticker.close)
#     reference_type = 'close'

# ib.cancelMktData(contract)

# if not spot:
#     print(json.dumps({{'error': 'No spot available'}}))
#     ib.disconnect()
#     sys.exit(0)

# chains = ib.reqSecDefOptParams(contract.symbol, '', contract.secType, contract.conId)
# chain = next((c for c in chains if c.exchange == 'SMART'), None)
# if not chain:
#     print(json.dumps({{'error': 'No chain'}}))
#     ib.disconnect()
#     sys.exit(0)

# expirations = [e for e in sorted(chain.expirations) if e >= pd.Timestamp.now().strftime('%Y%m%d')][:3]
# strikes = [s for s in sorted(chain.strikes) if spot * 0.90 <= s <= spot * 1.10]

# option_contracts = []
# for exp in expirations:
#     for strike in strikes:
#         for right in ['C', 'P']:
#             option_contracts.append(Option(symbol, exp, strike, right, 'SMART', multiplier='100'))

# qualified = []
# for i in range(0, len(option_contracts), 50):
#     batch = option_contracts[i:i+50]
#     ib.qualifyContracts(*batch)
#     qualified.extend([c for c in batch if c.conId > 0])
#     ib.sleep(0.5)

# option_data = []
# for i in range(0, len(qualified), 50):
#     batch = qualified[i:i+50]
#     tickers = [ib.reqMktData(c, '', False, False) for c in batch]
#     ib.sleep(5)
#     for t in tickers:
#         bid = safe(float(t.bid)) if t.bid and t.bid > 0 else None
#         ask = safe(float(t.ask)) if t.ask and t.ask > 0 else None
#         last = safe(float(t.last)) if t.last and t.last > 0 else None
#         close = safe(float(t.close)) if t.close and t.close > 0 else None
        
#         # Mid avec fallback (Step 5)
#         mid = None
#         quote_source = None
#         if bid and ask:
#             mid = (bid + ask) / 2
#             quote_source = 'mid'
#         elif last:
#             mid = last
#             quote_source = 'last'
#         elif close:
#             mid = close
#             quote_source = 'close'
        
#         iv_val = None
#         greeks = None
#         if mid and mid > 0:
#             exp_date = pd.Timestamp(t.contract.lastTradeDateOrContractMonth)
#             T = max((exp_date - pd.Timestamp.now()).days / 365.0, 0.001)
#             iv_val = implied_vol(mid, spot, t.contract.strike, T, R, t.contract.right)
#             if iv_val:
#                 greeks = bs_greeks(spot, t.contract.strike, T, R, iv_val, t.contract.right)
        
#         option_data.append({{
#             'expiry': t.contract.lastTradeDateOrContractMonth,
#             'strike': float(t.contract.strike),
#             'right': t.contract.right,
#             'bid': bid, 'ask': ask, 'last': last, 'close': close, 'mid': mid,
#             'quote_source': quote_source,
#             'iv': round(iv_val, 4) if iv_val else None,
#             'delta': round(greeks['delta'], 4) if greeks else None,
#             'gamma': round(greeks['gamma'], 6) if greeks else None,
#             'vega': round(greeks['vega'], 4) if greeks else None,
#             'theta': round(greeks['theta'], 4) if greeks else None,
#         }})
#         ib.cancelMktData(t.contract)

# ib.disconnect()
# print(json.dumps({{
#     'symbol': symbol,
#     'spot': spot,
#     'reference_type': reference_type,
#     'options': option_data,
#     'mode': 'live_delayed'
# }}))
# """
#     result = subprocess.run(
#         [sys.executable, '-c', script],
#         capture_output=True, text=True, timeout=180
#     )
#     if result.returncode != 0:
#         return {'error': f'Subprocess failed: {result.stderr[-300:]}'}
    
#     lines = result.stdout.strip().split('\n')
#     for line in reversed(lines):
#         try:
#             return json.loads(line)
#         except json.JSONDecodeError:
#             continue
#     return {'error': 'No valid JSON output'}


# def fetch_from_parquet(symbol):
#     """Lit le dernier snapshot historique sauvegardé (fallback)"""
#     path = get_latest_parquet(symbol)
#     if not path:
#         return None
    
#     try:
#         import pandas as pd
#         df = pd.read_parquet(path, engine='fastparquet')
        
#         # Reconstruire mid + recalculer IV/Greeks depuis bid/ask
#         import numpy as np
#         from scipy.stats import norm
#         from scipy.optimize import brentq
        
#         R = 0.043
        
#         def bs_price(S, K, T, r, sigma, right):
#             d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
#             d2 = d1 - sigma*np.sqrt(T)
#             if right == 'C':
#                 return float(S*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2))
#             return float(K*np.exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1))
        
#         def iv_solve(price, S, K, T, r, right):
#             try:
#                 return float(brentq(lambda sig: bs_price(S, K, T, r, sig, right) - price, 0.001, 5.0))
#             except:
#                 return None
        
#         def greeks(S, K, T, r, sigma, right):
#             if T <= 0 or sigma <= 0:
#                 return None
#             d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
#             d2 = d1 - sigma*np.sqrt(T)
#             delta = float(norm.cdf(d1) if right == 'C' else norm.cdf(d1) - 1)
#             gamma = float(norm.pdf(d1) / (S * sigma * np.sqrt(T)))
#             vega = float(S * norm.pdf(d1) * np.sqrt(T) / 100)
#             theta = float((-(S * norm.pdf(d1) * sigma) / (2*np.sqrt(T)) - r*K*np.exp(-r*T)*norm.cdf(d2 if right == 'C' else -d2)) / 365)
#             return {'delta': delta, 'gamma': gamma, 'vega': vega, 'theta': theta}
        
#         # Charger aussi le spot du même jour
#         spot_files = sorted(glob.glob(os.path.join(DATA_DIR, 'spots_*.parquet')))
#         spot = None
#         if spot_files:
#             spots = pd.read_parquet(spot_files[-1], engine='fastparquet')
#             row = spots[spots['symbol'] == symbol]
#             if len(row) > 0:
#                 spot = float(row['last'].iloc[0]) if pd.notna(row['last'].iloc[0]) else float(row['close'].iloc[0])
        
#         if not spot:
#             return None
        
#         # Filtrer les options qui ont des quotes
#         df = df.dropna(subset=['bid', 'ask'])
#         df['mid'] = (df['bid'] + df['ask']) / 2
        
#         # Recalculer IV + Greeks
#         options = []
#         for _, row in df.iterrows():
#             exp_date = pd.Timestamp(row['expiry'])
#             T = max((exp_date - pd.Timestamp.now()).days / 365.0, 0.001)
#             iv = iv_solve(row['mid'], spot, row['strike'], T, R, row['right'])
#             gk = greeks(spot, row['strike'], T, R, iv, row['right']) if iv else None
            
#             options.append({
#                 'expiry': row['expiry'],
#                 'strike': float(row['strike']),
#                 'right': row['right'],
#                 'bid': float(row['bid']) if pd.notna(row['bid']) else None,
#                 'ask': float(row['ask']) if pd.notna(row['ask']) else None,
#                 'mid': float(row['mid']),
#                 'quote_source': 'historical',
#                 'iv': round(iv, 4) if iv else None,
#                 'delta': round(gk['delta'], 4) if gk else None,
#                 'gamma': round(gk['gamma'], 6) if gk else None,
#                 'vega': round(gk['vega'], 4) if gk else None,
#                 'theta': round(gk['theta'], 4) if gk else None,
#             })
        
#         snapshot_date = os.path.basename(path).split('_')[-1].replace('.parquet', '')
#         return {
#             'symbol': symbol,
#             'spot': spot,
#             'reference_type': 'historical_close',
#             'options': options,
#             'mode': f'historical_snapshot_{snapshot_date}'
#         }
#     except Exception as e:
#         print(f"Erreur fallback parquet: {e}")
#         return None


# @app.get("/api/chain/{symbol}")
# async def get_chain(symbol: str):
#     symbol = symbol.upper()
#     print(f"📡 Fetching {symbol}...")
    
#     # 1. Essayer live (delayed)
#     data = fetch_from_ibkr(symbol)
    
#     # 2. Si live échoue ou retourne 0 options exploitables, fallback historique
#     if data.get('error') or len([o for o in data.get('options', []) if o.get('mid')]) == 0:
#         print(f"⚠️  Live failed/empty for {symbol}, trying historical fallback...")
#         historical = fetch_from_parquet(symbol)
#         if historical:
#             data = historical
#             print(f"✅ {symbol} loaded from historical snapshot")
#         else:
#             print(f"❌ No historical data for {symbol}")
#     else:
#         print(f"✅ {symbol} loaded live — {len(data['options'])} options")
    
#     data = clean_nan(data)
#     CACHE[symbol] = data
#     return data


# @app.get("/", response_class=HTMLResponse)
# def frontend():
#     return """
#     <!DOCTYPE html>
#     <html>
#     <head>
#         <title>Volatility Infrastructure Platform</title>
#         <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
#         <style>
#             * { margin: 0; padding: 0; box-sizing: border-box; }
#             body { font-family: 'Segoe UI', sans-serif; background: #0f1117; color: #e0e0e0; }
#             .header { background: #1a1d29; padding: 20px 40px; border-bottom: 2px solid #2d7ff9; }
#             .header h1 { color: #2d7ff9; font-size: 24px; }
#             .controls { padding: 20px 40px; display: flex; gap: 15px; align-items: center; flex-wrap: wrap; }
#             .controls input { background: #1a1d29; border: 1px solid #333; color: white; padding: 10px 15px;
#                              border-radius: 6px; font-size: 16px; width: 200px; }
#             .controls button { background: #2d7ff9; color: white; border: none; padding: 10px 25px;
#                               border-radius: 6px; font-size: 16px; cursor: pointer; }
#             .controls button:hover { background: #1a6fe0; }
#             .controls button:disabled { background: #555; cursor: wait; }
#             .spot-info { padding: 10px 40px; font-size: 18px; }
#             .spot-info span { color: #2d7ff9; font-weight: bold; }
#             .mode-tag { display: inline-block; padding: 4px 10px; border-radius: 4px; 
#                        font-size: 12px; margin-left: 10px; font-weight: bold; }
#             .mode-live { background: #1a4d2e; color: #4ade80; }
#             .mode-hist { background: #4d3a1a; color: #fbbf24; }
#             .charts { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; padding: 20px 40px; }
#             .chart-box { background: #1a1d29; border-radius: 10px; padding: 15px; }
#             #status { color: #888; font-size: 14px; }
#             table { width: 100%; border-collapse: collapse; margin-top: 20px; }
#             th { background: #2d7ff9; color: white; padding: 8px; text-align: right; font-size: 12px; }
#             td { padding: 6px 8px; border-bottom: 1px solid #333; text-align: right; font-size: 12px; }
#             tr:hover { background: #1f2233; }
#             .section { padding: 20px 40px; }
#             h2 { color: #2d7ff9; margin-bottom: 15px; }
#         </style>
#     </head>
#     <body>
#         <div class="header">
#             <h1>Volatility Infrastructure Platform &mdash; S&amp;P 500</h1>
#         </div>
#         <div class="controls">
#             <input type="text" id="symbol" placeholder="Ticker" value="AAPL"
#                    onkeydown="if(event.key==='Enter') loadData()">
#             <button id="btn" onclick="loadData()">Charger</button>
#             <span id="status"></span>
#         </div>
#         <div class="spot-info" id="spotInfo"></div>
#         <div class="charts">
#             <div class="chart-box"><div id="smileChart"></div></div>
#             <div class="chart-box"><div id="deltaChart"></div></div>
#             <div class="chart-box"><div id="gammaChart"></div></div>
#             <div class="chart-box"><div id="vegaChart"></div></div>
#         </div>
#         <div class="section">
#             <h2>Option Chain</h2>
#             <div id="chainTable"></div>
#         </div>
#         <script>
#         async function loadData() {
#             const sym = document.getElementById('symbol').value.toUpperCase();
#             const btn = document.getElementById('btn');
#             btn.disabled = true;
#             btn.textContent = '⏳ Loading...';
#             document.getElementById('status').textContent = 'Fetching ' + sym + '...';

#             try {
#                 const res = await fetch('/api/chain/' + sym);
#                 const data = await res.json();

#                 if (data.error) {
#                     document.getElementById('status').textContent = 'Erreur: ' + data.error;
#                     btn.disabled = false; btn.textContent = 'Charger';
#                     return;
#                 }

#                 const isLive = data.mode === 'live_delayed';
#                 const modeTag = isLive 
#                     ? '<span class="mode-tag mode-live">LIVE DELAYED</span>'
#                     : '<span class="mode-tag mode-hist">HISTORICAL — ' + data.mode.replace('historical_snapshot_', '') + '</span>';
                
#                 document.getElementById('spotInfo').innerHTML =
#                     '<span>' + data.symbol + '</span> &mdash; Spot: <span>$' + (data.spot?.toFixed(2) || '?') + '</span>'
#                     + ' <small style="color:#888">(' + data.reference_type + ')</small>'
#                     + modeTag;

#                 const opts = data.options.filter(o => o.iv !== null);
#                 const expiries = [...new Set(opts.map(o => o.expiry))].sort();
#                 const darkLayout = {
#                     paper_bgcolor: '#1a1d29', plot_bgcolor: '#1a1d29',
#                     font: {color: '#e0e0e0'}, legend: {font: {size: 10}},
#                     margin: {t: 40, b: 40, l: 50, r: 20}
#                 };

#                 const smileTraces = [];
#                 expiries.forEach(exp => {
#                     const calls = opts.filter(o => o.expiry === exp && o.right === 'C');
#                     smileTraces.push({
#                         x: calls.map(o => o.strike), y: calls.map(o => o.iv * 100),
#                         name: exp, mode: 'lines+markers', marker: {size: 4}
#                     });
#                 });
#                 Plotly.newPlot('smileChart', smileTraces, {
#                     ...darkLayout, title: 'Volatility Smile',
#                     xaxis: {title: 'Strike'}, yaxis: {title: 'IV (%)'}
#                 });

#                 const exp0 = expiries[0];
#                 const calls0 = opts.filter(o => o.expiry === exp0 && o.right === 'C');

#                 Plotly.newPlot('deltaChart', [{
#                     x: calls0.map(o => o.strike), y: calls0.map(o => o.delta),
#                     mode: 'lines+markers', marker: {size: 4, color: '#2d7ff9'}
#                 }], {...darkLayout, title: 'Delta (Calls)', xaxis: {title: 'Strike'}, yaxis: {title: 'Delta'}, showlegend: false});

#                 Plotly.newPlot('gammaChart', [{
#                     x: calls0.map(o => o.strike), y: calls0.map(o => o.gamma),
#                     mode: 'lines+markers', marker: {size: 4, color: '#ff4444'}
#                 }], {...darkLayout, title: 'Gamma', xaxis: {title: 'Strike'}, yaxis: {title: 'Gamma'}, showlegend: false});

#                 Plotly.newPlot('vegaChart', [{
#                     x: calls0.map(o => o.strike), y: calls0.map(o => o.vega),
#                     mode: 'lines+markers', marker: {size: 4, color: '#aa44ff'}
#                 }], {...darkLayout, title: 'Vega', xaxis: {title: 'Strike'}, yaxis: {title: 'Vega'}, showlegend: false});

#                 let html = '<table><tr><th>Expiry</th><th>Strike</th><th>Type</th><th>Bid</th><th>Ask</th><th>Mid</th><th>Source</th><th>IV</th><th>Delta</th><th>Gamma</th><th>Vega</th><th>Theta</th></tr>';
#                 opts.forEach(o => {
#                     html += '<tr><td>' + o.expiry + '</td><td>' + o.strike + '</td><td>' + o.right + '</td>'
#                         + '<td>' + (o.bid !== null ? o.bid.toFixed(2) : '-') + '</td>'
#                         + '<td>' + (o.ask !== null ? o.ask.toFixed(2) : '-') + '</td>'
#                         + '<td>' + (o.mid !== null ? o.mid.toFixed(2) : '-') + '</td>'
#                         + '<td style="color:#888">' + (o.quote_source || '-') + '</td>'
#                         + '<td>' + (o.iv * 100).toFixed(1) + '%</td>'
#                         + '<td>' + (o.delta !== null ? o.delta.toFixed(3) : '-') + '</td>'
#                         + '<td>' + (o.gamma !== null ? o.gamma.toFixed(5) : '-') + '</td>'
#                         + '<td>' + (o.vega !== null ? o.vega.toFixed(3) : '-') + '</td>'
#                         + '<td>' + (o.theta !== null ? o.theta.toFixed(3) : '-') + '</td></tr>';
#                 });
#                 html += '</table>';
#                 document.getElementById('chainTable').innerHTML = html;

#                 document.getElementById('status').textContent = '✅ ' + opts.length + ' options';
#             } catch(e) {
#                 document.getElementById('status').textContent = 'Erreur: ' + e.message;
#             }
#             btn.disabled = false; btn.textContent = 'Charger';
#         }
#         </script>
#     </body>
#     </html>
#     """


# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=8000)


# src/app.py — Volatility Infrastructure Platform
# Step 5 du doc: fallback explicite (mid → last → close → snapshot)
# Step 10 TODO: Dollar Greeks, Rho, Root Time Vega, Start/Mid/End market

import subprocess, sys, json, os, math, glob
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(title="Vol Platform")

CACHE = {}
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw')


def clean_nan(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_nan(i) for i in obj]
    return obj


def get_latest_parquet(symbol):
    pattern = os.path.join(DATA_DIR, f'options_{symbol}_*.parquet')
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def fetch_from_ibkr(symbol):
    """Subprocess séparé pour éviter conflits event loop"""
    script = f"""
import json, sys, math
import nest_asyncio
nest_asyncio.apply()
from ib_insync import *
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq
import pandas as pd

R = 0.043
MULTIPLIER = 100

def bs_price(S, K, T, r, sigma, right='C'):
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    if right == 'C':
        return float(S*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2))
    return float(K*np.exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1))

def implied_vol(market_price, S, K, T, r, right='C'):
    try:
        return float(brentq(lambda sig: bs_price(S, K, T, r, sig, right) - market_price, 0.001, 5.0, xtol=1e-6))
    except:
        return None

def bs_greeks_full(S, K, T, r, sigma, right='C'):
    \"\"\"Greeks complets + Dollar Greeks + Rho + Root Time Vega\"\"\"
    if T <= 0 or sigma <= 0:
        return None
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    if right == 'C':
        delta = float(norm.cdf(d1))
        rho = float(K * T * np.exp(-r*T) * norm.cdf(d2) / 100)
    else:
        delta = float(norm.cdf(d1) - 1)
        rho = float(-K * T * np.exp(-r*T) * norm.cdf(-d2) / 100)
    gamma = float(norm.pdf(d1) / (S * sigma * np.sqrt(T)))
    vega = float(S * norm.pdf(d1) * np.sqrt(T) / 100)
    theta = float((-(S * norm.pdf(d1) * sigma) / (2*np.sqrt(T)) - r*K*np.exp(-r*T)*norm.cdf(d2 if right == 'C' else -d2)) / 365)
    # Dollar Greeks (Eq 17-18)
    dollar_gamma = float(gamma * S**2 * MULTIPLIER)
    dollar_vega = float(vega * MULTIPLIER)
    # Root Time Vega (comparable cross-maturité)
    root_time_vega = float(vega / np.sqrt(T)) if T > 0 else None
    return {{
        'delta': delta, 'gamma': gamma, 'vega': vega, 'theta': theta,
        'rho': rho,
        'dollar_gamma': dollar_gamma, 'dollar_vega': dollar_vega,
        'root_time_vega': root_time_vega
    }}

def safe(v):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return v

util.startLoop()
ib = IB()
ib.connect('127.0.0.1', 4002, clientId=99)
ib.reqMarketDataType(3)

symbol = '{symbol}'
contract = Stock(symbol, 'SMART', 'USD')
ib.qualifyContracts(contract)
ticker = ib.reqMktData(contract, '', False, False)
ib.sleep(4)

spot = None
reference_type = None
if ticker.last and ticker.last > 0 and not math.isnan(ticker.last):
    spot = float(ticker.last); reference_type = 'last'
elif ticker.bid and ticker.ask and ticker.bid > 0 and ticker.ask > 0:
    spot = float((ticker.bid + ticker.ask) / 2); reference_type = 'mid'
elif ticker.close and ticker.close > 0 and not math.isnan(ticker.close):
    spot = float(ticker.close); reference_type = 'close'

ib.cancelMktData(contract)

if not spot:
    print(json.dumps({{'error': 'No spot'}}))
    ib.disconnect()
    sys.exit(0)

chains = ib.reqSecDefOptParams(contract.symbol, '', contract.secType, contract.conId)
chain = next((c for c in chains if c.exchange == 'SMART'), None)
if not chain:
    print(json.dumps({{'error': 'No chain'}}))
    ib.disconnect()
    sys.exit(0)

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
        bid = safe(float(t.bid)) if t.bid and t.bid > 0 else None
        ask = safe(float(t.ask)) if t.ask and t.ask > 0 else None
        last = safe(float(t.last)) if t.last and t.last > 0 else None
        close = safe(float(t.close)) if t.close and t.close > 0 else None

        # Start / Mid / End market (TODO)
        start_market = bid
        mid_market = (bid + ask) / 2 if (bid and ask) else None
        end_market = ask

        # Fallback chain pour avoir AU MOINS un prix exploitable
        fallback_px = mid_market or last or close

        quote_source = None
        if mid_market: quote_source = 'mid'
        elif last: quote_source = 'last'
        elif close: quote_source = 'close'

        # === IV à partir des 3 prix (start/mid/end) — fourchette de plausibilité ===
        exp_date = pd.Timestamp(t.contract.lastTradeDateOrContractMonth)
        T = max((exp_date - pd.Timestamp.now()).days / 365.0, 0.001)
        K = t.contract.strike
        right = t.contract.right

        iv_bid = implied_vol(bid, spot, K, T, R, right) if bid else None
        iv_mid = implied_vol(mid_market, spot, K, T, R, right) if mid_market else None
        iv_ask = implied_vol(ask, spot, K, T, R, right) if ask else None
        iv_ref = iv_mid or implied_vol(fallback_px, spot, K, T, R, right) if fallback_px else None
        iv_spread = (iv_ask - iv_bid) if (iv_bid and iv_ask) else None

        greeks = bs_greeks_full(spot, K, T, R, iv_ref, right) if iv_ref else None

        option_data.append({{
            'expiry': t.contract.lastTradeDateOrContractMonth,
            'strike': float(K),
            'right': right,
            'bid': bid, 'ask': ask, 'last': last, 'close': close,
            'start_market': start_market,
            'mid_market': mid_market,
            'end_market': end_market,
            'quote_source': quote_source,
            'iv': round(iv_ref, 4) if iv_ref else None,
            'iv_bid': round(iv_bid, 4) if iv_bid else None,
            'iv_ask': round(iv_ask, 4) if iv_ask else None,
            'iv_spread': round(iv_spread, 4) if iv_spread else None,
            'delta': round(greeks['delta'], 4) if greeks else None,
            'gamma': round(greeks['gamma'], 6) if greeks else None,
            'vega': round(greeks['vega'], 4) if greeks else None,
            'theta': round(greeks['theta'], 4) if greeks else None,
            'rho': round(greeks['rho'], 4) if greeks else None,
            'dollar_gamma': round(greeks['dollar_gamma'], 2) if greeks else None,
            'dollar_vega': round(greeks['dollar_vega'], 2) if greeks else None,
            'root_time_vega': round(greeks['root_time_vega'], 4) if greeks else None,
        }})
        ib.cancelMktData(t.contract)

ib.disconnect()
print(json.dumps({{
    'symbol': symbol,
    'spot': spot,
    'reference_type': reference_type,
    'options': option_data,
    'mode': 'live_delayed'
}}))
"""
    result = subprocess.run(
        [sys.executable, '-c', script],
        capture_output=True, text=True, timeout=180
    )
    if result.returncode != 0:
        return {'error': f'Subprocess failed: {result.stderr[-300:]}'}

    lines = result.stdout.strip().split('\n')
    for line in reversed(lines):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return {'error': 'No valid JSON'}


def fetch_from_parquet(symbol):
    """Fallback historique avec recalcul de tous les Greeks v2"""
    path = get_latest_parquet(symbol)
    if not path:
        return None
    try:
        import pandas as pd
        import numpy as np
        from scipy.stats import norm
        from scipy.optimize import brentq

        R = 0.043
        MULTIPLIER = 100

        def bs_price(S, K, T, r, sigma, right):
            d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
            d2 = d1 - sigma*np.sqrt(T)
            if right == 'C':
                return float(S*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2))
            return float(K*np.exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1))

        def iv_solve(price, S, K, T, r, right):
            try:
                return float(brentq(lambda sig: bs_price(S, K, T, r, sig, right) - price, 0.001, 5.0))
            except:
                return None

        def greeks_full(S, K, T, r, sigma, right):
            if T <= 0 or sigma <= 0:
                return None
            d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
            d2 = d1 - sigma*np.sqrt(T)
            if right == 'C':
                delta = float(norm.cdf(d1))
                rho = float(K * T * np.exp(-r*T) * norm.cdf(d2) / 100)
            else:
                delta = float(norm.cdf(d1) - 1)
                rho = float(-K * T * np.exp(-r*T) * norm.cdf(-d2) / 100)
            gamma = float(norm.pdf(d1) / (S * sigma * np.sqrt(T)))
            vega = float(S * norm.pdf(d1) * np.sqrt(T) / 100)
            theta = float((-(S * norm.pdf(d1) * sigma) / (2*np.sqrt(T)) - r*K*np.exp(-r*T)*norm.cdf(d2 if right == 'C' else -d2)) / 365)
            dollar_gamma = float(gamma * S**2 * MULTIPLIER)
            dollar_vega = float(vega * MULTIPLIER)
            root_time_vega = float(vega / np.sqrt(T)) if T > 0 else None
            return {
                'delta': delta, 'gamma': gamma, 'vega': vega, 'theta': theta, 'rho': rho,
                'dollar_gamma': dollar_gamma, 'dollar_vega': dollar_vega,
                'root_time_vega': root_time_vega
            }

        df = pd.read_parquet(path, engine='fastparquet')

        spot_files = sorted(glob.glob(os.path.join(DATA_DIR, 'spots_*.parquet')))
        spot = None
        if spot_files:
            spots = pd.read_parquet(spot_files[-1], engine='fastparquet')
            row = spots[spots['symbol'] == symbol]
            if len(row) > 0:
                spot = float(row['last'].iloc[0]) if pd.notna(row['last'].iloc[0]) else float(row['close'].iloc[0])
        if not spot:
            return None

        df = df.dropna(subset=['bid', 'ask'])
        df['mid'] = (df['bid'] + df['ask']) / 2

        options = []
        for _, row in df.iterrows():
            exp_date = pd.Timestamp(row['expiry'])
            T = max((exp_date - pd.Timestamp.now()).days / 365.0, 0.001)
            K = float(row['strike'])
            right = row['right']
            bid = float(row['bid']) if pd.notna(row['bid']) else None
            ask = float(row['ask']) if pd.notna(row['ask']) else None
            mid = float(row['mid'])

            iv_bid = iv_solve(bid, spot, K, T, R, right) if bid else None
            iv_mid = iv_solve(mid, spot, K, T, R, right)
            iv_ask = iv_solve(ask, spot, K, T, R, right) if ask else None
            iv_spread = (iv_ask - iv_bid) if (iv_bid and iv_ask) else None
            gk = greeks_full(spot, K, T, R, iv_mid, right) if iv_mid else None

            options.append({
                'expiry': row['expiry'],
                'strike': K,
                'right': right,
                'bid': bid, 'ask': ask, 'mid': mid,
                'start_market': bid, 'mid_market': mid, 'end_market': ask,
                'quote_source': 'historical',
                'iv': round(iv_mid, 4) if iv_mid else None,
                'iv_bid': round(iv_bid, 4) if iv_bid else None,
                'iv_ask': round(iv_ask, 4) if iv_ask else None,
                'iv_spread': round(iv_spread, 4) if iv_spread else None,
                'delta': round(gk['delta'], 4) if gk else None,
                'gamma': round(gk['gamma'], 6) if gk else None,
                'vega': round(gk['vega'], 4) if gk else None,
                'theta': round(gk['theta'], 4) if gk else None,
                'rho': round(gk['rho'], 4) if gk else None,
                'dollar_gamma': round(gk['dollar_gamma'], 2) if gk else None,
                'dollar_vega': round(gk['dollar_vega'], 2) if gk else None,
                'root_time_vega': round(gk['root_time_vega'], 4) if gk else None,
            })

        snapshot_date = os.path.basename(path).split('_')[-1].replace('.parquet', '')
        return {
            'symbol': symbol, 'spot': spot, 'reference_type': 'historical_close',
            'options': options, 'mode': f'historical_snapshot_{snapshot_date}'
        }
    except Exception as e:
        print(f"Erreur fallback parquet: {e}")
        return None


@app.get("/api/chain/{symbol}")
async def get_chain(symbol: str):
    symbol = symbol.upper()
    print(f"📡 Fetching {symbol}...")
    data = fetch_from_ibkr(symbol)
    if data.get('error') or len([o for o in data.get('options', []) if o.get('iv')]) == 0:
        print(f"⚠️  Live failed/empty, fallback parquet...")
        historical = fetch_from_parquet(symbol)
        if historical:
            data = historical
            print(f"✅ {symbol} historical snapshot")
        else:
            print(f"❌ No data for {symbol}")
    else:
        print(f"✅ {symbol} live — {len(data['options'])} options")

    data = clean_nan(data)
    CACHE[symbol] = data
    return data


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
            .controls { padding: 20px 40px; display: flex; gap: 15px; align-items: center; flex-wrap: wrap; }
            .controls input { background: #1a1d29; border: 1px solid #333; color: white; padding: 10px 15px;
                             border-radius: 6px; font-size: 16px; width: 200px; }
            .controls button { background: #2d7ff9; color: white; border: none; padding: 10px 25px;
                              border-radius: 6px; font-size: 16px; cursor: pointer; }
            .controls button:hover { background: #1a6fe0; }
            .controls button:disabled { background: #555; cursor: wait; }
            .spot-info { padding: 10px 40px; font-size: 18px; }
            .spot-info span { color: #2d7ff9; font-weight: bold; }
            .mode-tag { display: inline-block; padding: 4px 10px; border-radius: 4px;
                       font-size: 12px; margin-left: 10px; font-weight: bold; }
            .mode-live { background: #1a4d2e; color: #4ade80; }
            .mode-hist { background: #4d3a1a; color: #fbbf24; }
            .charts { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; padding: 20px 40px; }
            .chart-box { background: #1a1d29; border-radius: 10px; padding: 15px; }
            #status { color: #888; font-size: 14px; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 11px; }
            th { background: #2d7ff9; color: white; padding: 6px 4px; text-align: right; font-size: 11px; position: sticky; top: 0; }
            td { padding: 5px 4px; border-bottom: 1px solid #333; text-align: right; }
            tr:hover { background: #1f2233; }
            .section { padding: 20px 40px; }
            h2 { color: #2d7ff9; margin-bottom: 15px; }
            .table-wrap { overflow-x: auto; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Volatility Infrastructure Platform &mdash; S&amp;P 500</h1>
        </div>
        <div class="controls">
            <input type="text" id="symbol" placeholder="Ticker" value="AAPL"
                   onkeydown="if(event.key==='Enter') loadData()">
            <button id="btn" onclick="loadData()">Charger</button>
            <span id="status"></span>
        </div>
        <div class="spot-info" id="spotInfo"></div>
        <div class="charts">
            <div class="chart-box"><div id="smileChart"></div></div>
            <div class="chart-box"><div id="dollarGreeksChart"></div></div>
            <div class="chart-box"><div id="deltaChart"></div></div>
            <div class="chart-box"><div id="gammaChart"></div></div>
            <div class="chart-box"><div id="vegaChart"></div></div>
            <div class="chart-box"><div id="rhoChart"></div></div>
        </div>
        <div class="section">
            <h2>Option Chain</h2>
            <div class="table-wrap"><div id="chainTable"></div></div>
        </div>
        <script>
        async function loadData() {
            const sym = document.getElementById('symbol').value.toUpperCase();
            const btn = document.getElementById('btn');
            btn.disabled = true;
            btn.textContent = '⏳ Loading...';
            document.getElementById('status').textContent = 'Fetching ' + sym + '...';

            try {
                const res = await fetch('/api/chain/' + sym);
                const data = await res.json();

                if (data.error) {
                    document.getElementById('status').textContent = 'Erreur: ' + data.error;
                    btn.disabled = false; btn.textContent = 'Charger';
                    return;
                }

                const isLive = data.mode === 'live_delayed';
                const modeTag = isLive
                    ? '<span class="mode-tag mode-live">LIVE DELAYED</span>'
                    : '<span class="mode-tag mode-hist">HISTORICAL — ' + data.mode.replace('historical_snapshot_', '') + '</span>';

                document.getElementById('spotInfo').innerHTML =
                    '<span>' + data.symbol + '</span> &mdash; Spot: <span>$' + (data.spot?.toFixed(2) || '?') + '</span>'
                    + ' <small style="color:#888">(' + data.reference_type + ')</small>'
                    + modeTag;

                const opts = data.options.filter(o => o.iv !== null);
                const expiries = [...new Set(opts.map(o => o.expiry))].sort();
                const darkLayout = {
                    paper_bgcolor: '#1a1d29', plot_bgcolor: '#1a1d29',
                    font: {color: '#e0e0e0'}, legend: {font: {size: 10}},
                    margin: {t: 40, b: 40, l: 50, r: 20}
                };

                // === Smile avec fourchette bid/mid/ask ===
                const smileTraces = [];
                expiries.forEach(exp => {
                    const calls = opts.filter(o => o.expiry === exp && o.right === 'C');
                    smileTraces.push({
                        x: calls.map(o => o.strike), y: calls.map(o => o.iv * 100),
                        name: exp + ' (mid)', mode: 'lines+markers', marker: {size: 4}
                    });
                    if (calls.some(o => o.iv_bid)) {
                        smileTraces.push({
                            x: calls.map(o => o.strike), y: calls.map(o => o.iv_bid ? o.iv_bid * 100 : null),
                            name: exp + ' (bid)', mode: 'lines', line: {dash: 'dot', width: 1},
                            opacity: 0.5, showlegend: false
                        });
                        smileTraces.push({
                            x: calls.map(o => o.strike), y: calls.map(o => o.iv_ask ? o.iv_ask * 100 : null),
                            name: exp + ' (ask)', mode: 'lines', line: {dash: 'dot', width: 1},
                            opacity: 0.5, showlegend: false
                        });
                    }
                });
                Plotly.newPlot('smileChart', smileTraces, {
                    ...darkLayout, title: 'Volatility Smile (mid + bid/ask range)',
                    xaxis: {title: 'Strike'}, yaxis: {title: 'IV (%)'}
                });

                const exp0 = expiries[0];
                const calls0 = opts.filter(o => o.expiry === exp0 && o.right === 'C');

                // === Dollar Greeks (Eq 17-18) ===
                Plotly.newPlot('dollarGreeksChart', [
                    {
                        x: calls0.map(o => o.strike), y: calls0.map(o => o.dollar_gamma),
                        name: 'Dollar Gamma ($)', mode: 'lines+markers', marker: {size: 4, color: '#22d3ee'}
                    },
                    {
                        x: calls0.map(o => o.strike), y: calls0.map(o => o.dollar_vega),
                        name: 'Dollar Vega ($)', mode: 'lines+markers', marker: {size: 4, color: '#a78bfa'},
                        yaxis: 'y2'
                    }
                ], {
                    ...darkLayout, title: 'Dollar Greeks (Eq 17-18)',
                    xaxis: {title: 'Strike'},
                    yaxis: {title: 'Dollar Gamma ($)', titlefont: {color: '#22d3ee'}},
                    yaxis2: {title: 'Dollar Vega ($)', titlefont: {color: '#a78bfa'}, overlaying: 'y', side: 'right'}
                });

                Plotly.newPlot('deltaChart', [{
                    x: calls0.map(o => o.strike), y: calls0.map(o => o.delta),
                    mode: 'lines+markers', marker: {size: 4, color: '#2d7ff9'}
                }], {...darkLayout, title: 'Delta', xaxis: {title: 'Strike'}, yaxis: {title: 'Delta'}, showlegend: false});

                Plotly.newPlot('gammaChart', [{
                    x: calls0.map(o => o.strike), y: calls0.map(o => o.gamma),
                    mode: 'lines+markers', marker: {size: 4, color: '#ff4444'}
                }], {...darkLayout, title: 'Gamma', xaxis: {title: 'Strike'}, yaxis: {title: 'Gamma'}, showlegend: false});

                // Vega + Root Time Vega
                Plotly.newPlot('vegaChart', [
                    {x: calls0.map(o => o.strike), y: calls0.map(o => o.vega),
                     name: 'Vega', mode: 'lines+markers', marker: {size: 4, color: '#aa44ff'}},
                    {x: calls0.map(o => o.strike), y: calls0.map(o => o.root_time_vega),
                     name: 'Root Time Vega', mode: 'lines+markers', marker: {size: 4, color: '#f59e0b'}, yaxis: 'y2'}
                ], {
                    ...darkLayout, title: 'Vega & Root Time Vega',
                    xaxis: {title: 'Strike'},
                    yaxis: {title: 'Vega', titlefont: {color: '#aa44ff'}},
                    yaxis2: {title: 'RTV', titlefont: {color: '#f59e0b'}, overlaying: 'y', side: 'right'}
                });

                // Rho
                Plotly.newPlot('rhoChart', [{
                    x: calls0.map(o => o.strike), y: calls0.map(o => o.rho),
                    mode: 'lines+markers', marker: {size: 4, color: '#10b981'}
                }], {...darkLayout, title: 'Rho (per 1% rate)', xaxis: {title: 'Strike'}, yaxis: {title: 'Rho'}, showlegend: false});

                // === Table ===
                let html = '<table><tr>'
                    + '<th>Expiry</th><th>K</th><th>Type</th>'
                    + '<th>Start (bid)</th><th>Mid</th><th>End (ask)</th>'
                    + '<th>IV bid</th><th>IV mid</th><th>IV ask</th><th>IV spread</th>'
                    + '<th>Δ</th><th>Γ</th><th>V</th><th>Θ</th><th>ρ</th>'
                    + '<th>$Gamma</th><th>$Vega</th><th>RTV</th>'
                    + '</tr>';
                opts.forEach(o => {
                    const f = (v, d=2) => v !== null && v !== undefined ? v.toFixed(d) : '-';
                    const pct = v => v !== null && v !== undefined ? (v*100).toFixed(1)+'%' : '-';
                    html += '<tr>'
                        + '<td>' + o.expiry + '</td><td>' + o.strike + '</td><td>' + o.right + '</td>'
                        + '<td>' + f(o.start_market) + '</td>'
                        + '<td>' + f(o.mid_market) + '</td>'
                        + '<td>' + f(o.end_market) + '</td>'
                        + '<td>' + pct(o.iv_bid) + '</td>'
                        + '<td>' + pct(o.iv) + '</td>'
                        + '<td>' + pct(o.iv_ask) + '</td>'
                        + '<td>' + pct(o.iv_spread) + '</td>'
                        + '<td>' + f(o.delta, 3) + '</td>'
                        + '<td>' + f(o.gamma, 5) + '</td>'
                        + '<td>' + f(o.vega, 3) + '</td>'
                        + '<td>' + f(o.theta, 3) + '</td>'
                        + '<td>' + f(o.rho, 3) + '</td>'
                        + '<td>' + f(o.dollar_gamma, 0) + '</td>'
                        + '<td>' + f(o.dollar_vega, 1) + '</td>'
                        + '<td>' + f(o.root_time_vega, 3) + '</td>'
                        + '</tr>';
                });
                html += '</table>';
                document.getElementById('chainTable').innerHTML = html;

                document.getElementById('status').textContent = '✅ ' + opts.length + ' options';
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