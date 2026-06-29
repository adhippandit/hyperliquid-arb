import pickle
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import time
import webbrowser
import os
from risk import position_size, daily_loss_limit, vix_allowed, MAX_OPEN_TRADES, TOTAL_CAPITAL, VIX_CIRCUIT_BREAKER

MODEL_FILE = "model.pkl"
HTML_FILE  = "scorer.html"

TICKERS = [
    "NVDA", "TSLA", "AAPL", "AMZN", "MSFT",
    "GOOGL", "META", "NFLX", "AMD", "INTC",
    "COIN", "MSTR", "PLTR", "ARM", "TSM",
    "GME", "BB", "NOK", "HOOD", "ZM",
    "BABA", "MU", "QCOM", "AVGO", "ORCL",
    "NOW", "RIVN",
]

CONFIDENCE_THRESHOLD = 0.70

def is_market_open():
    now_et = datetime.now(ZoneInfo("America/New_York"))
    if now_et.weekday() >= 5:
        return False
    open_time  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_time = now_et.replace(hour=16, minute=0,  second=0, microsecond=0)
    return open_time <= now_et <= close_time

def hours_to_market_open():
    now_et = datetime.now(ZoneInfo("America/New_York"))
    if is_market_open():
        return 0.0
    candidate = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    if now_et >= candidate or now_et.weekday() >= 5:
        candidate += timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
    return round((candidate - now_et).total_seconds() / 3600, 2)

def fetch_vix():
    try:
        return round(yf.Ticker("^VIX").fast_info.last_price, 2)
    except:
        return 20.0

def fetch_real_prices():
    prices = {}
    for ticker in TICKERS:
        try:
            prices[ticker] = yf.Ticker(ticker).fast_info.last_price
        except:
            prices[ticker] = None
    return prices

def fetch_hl_data():
    hl_prices = {}
    for ticker in TICKERS:
        try:
            resp = requests.post(
                "https://api.hyperliquid.xyz/info",
                json={"type": "l2Book", "coin": f"xyz:{ticker}"},
                timeout=5,
            ).json()
            if resp and resp.get("levels"):
                bids, asks = resp["levels"][0], resp["levels"][1]
                if bids and asks:
                    best_bid = float(bids[0]["px"])
                    best_ask = float(asks[0]["px"])
                    mid      = (best_bid + best_ask) / 2
                    hl_prices[ticker] = {
                        "mid":                mid,
                        "bid_ask_spread_pct": round((best_ask - best_bid) / mid * 100, 4),
                    }
        except:
            pass
    return hl_prices

def score_gaps(model):
    now         = datetime.now(timezone.utc)
    market_open = is_market_open()
    h_to_open   = hours_to_market_open()
    vix         = fetch_vix()
    day_num     = now.weekday()
    is_weekend  = 1 if day_num >= 5 else 0
    hour_utc    = now.hour

    real_prices = fetch_real_prices()
    hl_prices   = fetch_hl_data()

    results = []
    for ticker in TICKERS:
        real   = real_prices.get(ticker)
        hl     = hl_prices.get(ticker, {})
        hl_mid = hl.get("mid")

        if not real or not hl_mid:
            continue

        gap     = hl_mid - real
        gap_pct = (gap / real) * 100
        gap_abs = abs(gap_pct)

        if gap_abs < 0.5:
            continue

        spread = hl.get("bid_ask_spread_pct", 0.1)

        features = pd.DataFrame([{
            "gap_abs":            gap_abs,
            "is_weekend":         is_weekend,
            "day_num":            day_num,
            "hour_utc":           hour_utc,
            "hours_to_open":      h_to_open,
            "vix":                vix,
            "bid_ask_spread_pct": spread,
        }])

        confidence = model.predict_proba(features)[0][1]

        results.append({
            "ticker":     ticker,
            "real":       real,
            "hl":         hl_mid,
            "gap_pct":    gap_pct,
            "gap_abs":    gap_abs,
            "confidence": confidence,
            "spread":     spread,
            "trade":      confidence >= CONFIDENCE_THRESHOLD,
            "position":   position_size(confidence) if confidence >= CONFIDENCE_THRESHOLD else 0,
        })

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results, vix, h_to_open, market_open, now

def write_html(results, vix, h_to_open, market_open, now):
    sg_time = datetime.now(ZoneInfo("Asia/Singapore"))
    market_status = "OPEN" if market_open else "CLOSED"
    market_color  = "#00c853" if market_open else "#ff1744"
    trades        = [r for r in results if r["trade"]]

    rows_html = ""
    for r in results:
        gap_color  = "#ff4444" if r["gap_pct"] > 0 else "#00c853"
        conf_pct   = f"{r['confidence']*100:.1f}%"
        conf_bar   = int(r["confidence"] * 100)

        if r["trade"]:
            signal_html  = '<span class="signal-trade">TRADE IT</span>'
            row_class    = "row-trade"
            position_html = f'<span style="color:#3fb950;font-weight:700">${r["position"]:,.0f}</span>'
        else:
            signal_html   = '<span class="signal-skip">skip</span>'
            row_class     = "row-skip"
            position_html = '<span style="color:#484f58">—</span>'

        rows_html += f"""
        <tr class="{row_class}">
            <td class="ticker">{r['ticker']}</td>
            <td>${r['real']:,.2f}</td>
            <td>${r['hl']:,.2f}</td>
            <td style="color:{gap_color}; font-weight:600">{r['gap_pct']:+.2f}%</td>
            <td>
                <div class="conf-wrap">
                    <div class="conf-bar" style="width:{conf_bar}%"></div>
                    <span class="conf-label">{conf_pct}</span>
                </div>
            </td>
            <td>{r['spread']:.3f}%</td>
            <td>{position_html}</td>
            <td>{signal_html}</td>
        </tr>"""

    if not vix_allowed(vix):
        banner = (
            f'<div class="banner-wait" style="border-color:#ff1744;color:#ff6b6b">'
            f'&#9888; VIX CIRCUIT BREAKER ACTIVE — VIX is {vix} (limit: {VIX_CIRCUIT_BREAKER}) &mdash; '
            f'Market too volatile, no trades today regardless of signals</div>'
        )
    elif trades:
        capped   = trades[:MAX_OPEN_TRADES]
        exposure = sum(r["position"] for r in capped)
        banner   = (
            f'<div class="banner-trade">&#9650; {len(trades)} trade signal{"s" if len(trades)>1 else ""} above {int(CONFIDENCE_THRESHOLD*100)}% confidence'
            f' &nbsp;&bull;&nbsp; Taking top {len(capped)} (max {MAX_OPEN_TRADES}) &nbsp;&bull;&nbsp; Total exposure: ${exposure:,.0f} of ${TOTAL_CAPITAL:,}'
            f' &nbsp;&bull;&nbsp; Daily loss limit: ${daily_loss_limit():,.0f}</div>'
        )
    else:
        banner = f'<div class="banner-wait">No high-confidence opportunities right now &mdash; waiting for next refresh &nbsp;&bull;&nbsp; Daily loss limit: ${daily_loss_limit():,.0f}</div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="300">
<title>Hyperliquid Scorer</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#0d1117; color:#e6edf3; font-family:'Segoe UI',system-ui,sans-serif; font-size:14px; }}

  .header {{ background:#161b22; border-bottom:1px solid #30363d; padding:18px 32px; display:flex; align-items:center; gap:32px; }}
  .header h1 {{ font-size:18px; font-weight:700; color:#58a6ff; letter-spacing:.5px; }}
  .pill {{ background:#21262d; border:1px solid #30363d; border-radius:20px; padding:4px 14px; font-size:12px; color:#8b949e; }}
  .pill span {{ color:#e6edf3; font-weight:600; }}
  .pill .green {{ color:#00c853; }}
  .pill .red   {{ color:#ff1744; }}

  .container {{ padding:24px 32px; }}

  {banner_css()}

  table {{ width:100%; border-collapse:collapse; background:#161b22; border-radius:10px; overflow:hidden; border:1px solid #30363d; }}
  thead tr {{ background:#21262d; }}
  th {{ padding:12px 16px; text-align:left; font-size:11px; text-transform:uppercase; letter-spacing:.8px; color:#8b949e; font-weight:600; }}
  td {{ padding:11px 16px; border-top:1px solid #21262d; }}

  .row-trade {{ background:#0d2016; }}
  .row-trade:hover {{ background:#112a1e; }}
  .row-skip {{ opacity:.55; }}
  .row-skip:hover {{ opacity:.75; }}

  .ticker {{ font-weight:700; color:#58a6ff; font-size:15px; }}

  .conf-wrap {{ position:relative; background:#21262d; border-radius:4px; height:20px; width:120px; overflow:hidden; }}
  .conf-bar  {{ position:absolute; left:0; top:0; height:100%; background:linear-gradient(90deg,#238636,#2ea043); border-radius:4px; }}
  .conf-label {{ position:absolute; width:100%; text-align:center; line-height:20px; font-size:12px; font-weight:700; color:#fff; }}

  .signal-trade {{ background:#238636; color:#fff; padding:3px 10px; border-radius:4px; font-weight:700; font-size:12px; }}
  .signal-skip  {{ color:#484f58; font-size:12px; }}

  .footer {{ padding:12px 32px; color:#484f58; font-size:12px; }}
</style>
</head>
<body>

<div class="header">
  <h1>HYPERLIQUID MODEL SCORER</h1>
  <div class="pill">SGT <span>{sg_time.strftime('%a %d %b  %H:%M')}</span></div>
  <div class="pill">UTC <span>{now.strftime('%H:%M')}</span></div>
  <div class="pill">NYSE <span class="{'green' if market_open else 'red'}">{market_status}</span></div>
  <div class="pill">VIX <span>{vix}</span></div>
  <div class="pill">Hours to open <span>{h_to_open}</span></div>
</div>

<div class="container">
  {banner}

  <table>
    <thead>
      <tr>
        <th>Ticker</th>
        <th>Real Price</th>
        <th>HL Price</th>
        <th>Gap %</th>
        <th>Confidence</th>
        <th>Spread</th>
        <th>Position $</th>
        <th>Signal</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</div>

<div class="footer">Auto-refreshes every 5 minutes &nbsp;&bull;&nbsp; Last updated {sg_time.strftime('%H:%M:%S')} SGT</div>

</body>
</html>"""

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)

def banner_css():
    return (
        "  .banner-trade { background:#0d2016; border:1px solid #238636; border-radius:8px;"
        " padding:12px 20px; margin-bottom:20px; color:#3fb950; font-weight:600; font-size:14px; }\n"
        "  .banner-wait  { background:#161b22; border:1px solid #30363d; border-radius:8px;"
        " padding:12px 20px; margin-bottom:20px; color:#8b949e; font-size:14px; }\n"
    )

def main():
    print("Loading model...", flush=True)
    with open(MODEL_FILE, "rb") as f:
        model = pickle.load(f)
    print("Model ready.", flush=True)

    first_run = True
    while True:
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}]  Fetching prices...", flush=True)
            results, vix, h_to_open, market_open, now = score_gaps(model)
            write_html(results, vix, h_to_open, market_open, now)

            trades = [r for r in results if r["trade"]]
            print(f"[{datetime.now().strftime('%H:%M:%S')}]  {len(results)} gaps scored — {len(trades)} trade signals — saved to scorer.html", flush=True)

            if first_run:
                webbrowser.open(f"file:///{os.path.abspath(HTML_FILE)}")
                first_run = False

            time.sleep(300)
        except KeyboardInterrupt:
            print("\nScorer stopped.", flush=True)
            break
        except Exception as e:
            print(f"[ERROR] {e} — retrying in 60s", flush=True)
            time.sleep(60)

if __name__ == "__main__":
    main()
