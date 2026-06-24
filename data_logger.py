import csv
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests
import yfinance as yf

def is_market_open():
    now_et = datetime.now(ZoneInfo("America/New_York"))
    if now_et.weekday() >= 5:
        return False
    open_time  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_time = now_et.replace(hour=16, minute=0,  second=0, microsecond=0)
    return open_time <= now_et <= close_time

LOG_FILE = "gap_log.csv"
INTERVAL = 300  # 5 minutes

COLUMNS = [
    "timestamp", "ticker",
    "real_price", "hl_price", "gap_usd", "gap_pct",
    "bid_ask_spread_pct",
    "hours_to_open", "market_open", "day_of_week", "hour_utc", "vix",
]

TICKERS = [
    "NVDA", "TSLA", "AAPL", "AMZN", "MSFT",
    "GOOGL", "META", "NFLX", "AMD", "INTC",
    "COIN", "MSTR", "PLTR", "ARM", "TSM",
    "GME", "BB", "NOK", "HOOD", "ZM",
    "BABA", "MU", "QCOM", "AVGO", "ORCL",
    "NOW", "RIVN",
]

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
        return None

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

def log_snapshot():
    now         = datetime.now(timezone.utc)
    market_open = is_market_open()
    h_to_open   = hours_to_market_open()
    vix         = fetch_vix()
    real_prices = fetch_real_prices()
    hl_prices   = fetch_hl_data()

    rows = []
    for ticker in TICKERS:
        real   = real_prices.get(ticker)
        hl     = hl_prices.get(ticker, {})
        hl_mid = hl.get("mid")

        if not real or not hl_mid:
            continue

        gap     = hl_mid - real
        gap_pct = (gap / real) * 100

        rows.append({
            "timestamp":          now.strftime("%Y-%m-%d %H:%M:%S"),
            "ticker":             ticker,
            "real_price":         round(real,    4),
            "hl_price":           round(hl_mid,  4),
            "gap_usd":            round(gap,     4),
            "gap_pct":            round(gap_pct, 4),
            "bid_ask_spread_pct": hl.get("bid_ask_spread_pct"),
            "hours_to_open":      h_to_open,
            "market_open":        market_open,
            "day_of_week":        now.strftime("%A"),
            "hour_utc":           now.hour,
            "vix":                vix,
        })

    file_exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

    return len(rows)

if __name__ == "__main__":
    print(f"Data logger started — writing to '{LOG_FILE}' every {INTERVAL // 60} minutes.", flush=True)
    print("Press Ctrl+C to stop.\n", flush=True)

    while True:
        try:
            count = log_snapshot()
            print(f"[{datetime.now().strftime('%H:%M:%S')}]  Logged {count} rows", flush=True)
            time.sleep(INTERVAL)
        except KeyboardInterrupt:
            print("\nLogger stopped.", flush=True)
            break
        except Exception as e:
            print(f"[ERROR] {e}  — retrying in 60s", flush=True)
            time.sleep(60)
