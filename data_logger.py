import sqlite3
import sys
import time
from datetime import datetime, timezone
import requests
import yfinance as yf
from market_hours import is_market_open, hours_to_market_open

DB_FILE  = "gap_log.db"
INTERVAL = 300  # 5 minutes

TICKERS = [
    "NVDA", "TSLA", "AAPL", "AMZN", "MSFT",
    "GOOGL", "META", "NFLX", "AMD", "INTC",
    "COIN", "MSTR", "PLTR", "ARM", "TSM",
    "GME", "BB", "NOK", "HOOD", "ZM",
    "BABA", "MU", "QCOM", "AVGO", "ORCL",
    "NOW", "RIVN",
]

def setup_db():
    con = sqlite3.connect(DB_FILE)
    con.execute("""
        CREATE TABLE IF NOT EXISTS gaps (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp          TEXT,
            ticker             TEXT,
            real_price         REAL,
            hl_price           REAL,
            gap_usd            REAL,
            gap_pct            REAL,
            bid_ask_spread_pct REAL,
            hours_to_open      REAL,
            market_open        INTEGER,
            day_of_week        TEXT,
            hour_utc           INTEGER,
            vix                REAL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS funding (
            ticker       TEXT,
            timestamp    TEXT,
            funding_rate REAL,
            premium      REAL,
            PRIMARY KEY (ticker, timestamp)
        )
    """)
    con.commit()
    con.close()

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

def fetch_recent_funding(ticker, hours_back=3):
    """
    Hyperliquid settles funding hourly regardless of our 5-minute polling
    cadence. Pulling the last few hours each cycle (instead of just "now")
    means a slow cycle or brief downtime doesn't leave a gap in the record.
    """
    end_ms   = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = end_ms - hours_back * 3600 * 1000
    try:
        resp = requests.post(
            "https://api.hyperliquid.xyz/info",
            json={"type": "fundingHistory", "coin": f"xyz:{ticker}", "startTime": start_ms, "endTime": end_ms},
            timeout=5,
        ).json()
        return resp
    except Exception:
        return []

def log_funding():
    con = sqlite3.connect(DB_FILE)
    total = 0
    for ticker in TICKERS:
        entries = fetch_recent_funding(ticker)
        rows = [
            (
                ticker,
                datetime.fromtimestamp(e["time"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                float(e["fundingRate"]),
                float(e["premium"]),
            )
            for e in entries
        ]
        con.executemany(
            "INSERT OR IGNORE INTO funding (ticker, timestamp, funding_rate, premium) VALUES (?, ?, ?, ?)",
            rows,
        )
        total += len(rows)
    con.commit()
    con.close()
    return total

def log_snapshot():
    now         = datetime.now(timezone.utc)
    market_open = 1 if is_market_open() else 0
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

        rows.append((
            now.strftime("%Y-%m-%d %H:%M:%S"),
            ticker,
            round(real,    4),
            round(hl_mid,  4),
            round(gap,     4),
            round(gap_pct, 4),
            hl.get("bid_ask_spread_pct"),
            h_to_open,
            market_open,
            now.strftime("%A"),
            now.hour,
            vix,
        ))

    con = sqlite3.connect(DB_FILE)
    con.executemany("""
        INSERT INTO gaps (
            timestamp, ticker, real_price, hl_price,
            gap_usd, gap_pct, bid_ask_spread_pct,
            hours_to_open, market_open, day_of_week, hour_utc, vix
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, rows)
    con.commit()
    con.close()

    return len(rows)

if __name__ == "__main__":
    setup_db()
    print(f"Data logger started — writing to '{DB_FILE}' every {INTERVAL // 60} minutes.", flush=True)
    print("Press Ctrl+C to stop.\n", flush=True)

    while True:
        try:
            count = log_snapshot()
            funding_count = log_funding()
            print(f"[{datetime.now().strftime('%H:%M:%S')}]  Logged {count} rows, {funding_count} funding entries", flush=True)
            time.sleep(INTERVAL)
        except KeyboardInterrupt:
            print("\nLogger stopped.", flush=True)
            break
        except Exception as e:
            print(f"[ERROR] {e}  — retrying in 60s", flush=True)
            time.sleep(60)
