"""
One-off backfill: Hyperliquid keeps its own permanent hourly funding history
per contract, independent of whether data_logger.py was running. This pulls
that history for the entire window we've already collected gap data for, so
existing rows aren't missing a real income source the strategy relies on.

Safe to re-run — inserts are deduplicated on (ticker, timestamp).
"""
import sqlite3
import time
from datetime import datetime, timezone
import requests

DB_FILE = "gap_log.db"

TICKERS = [
    "NVDA", "TSLA", "AAPL", "AMZN", "MSFT",
    "GOOGL", "META", "NFLX", "AMD", "INTC",
    "COIN", "MSTR", "PLTR", "ARM", "TSM",
    "GME", "BB", "NOK", "HOOD", "ZM",
    "BABA", "MU", "QCOM", "AVGO", "ORCL",
    "NOW", "RIVN",
]


def setup_table(con):
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


def fetch_funding_history(ticker, start_ms, end_ms):
    resp = requests.post(
        "https://api.hyperliquid.xyz/info",
        json={"type": "fundingHistory", "coin": f"xyz:{ticker}", "startTime": start_ms, "endTime": end_ms},
        timeout=15,
    ).json()
    return resp


def backfill():
    con = sqlite3.connect(DB_FILE)
    setup_table(con)

    earliest = con.execute("SELECT MIN(timestamp) FROM gaps").fetchone()[0]
    if earliest is None:
        print("No rows in 'gaps' yet — nothing to backfill against.")
        return

    start_dt = datetime.strptime(earliest, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    end_dt   = datetime.now(timezone.utc)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms   = int(end_dt.timestamp() * 1000)

    print(f"Backfilling funding history from {start_dt} to {end_dt}...\n")

    total = 0
    for ticker in TICKERS:
        try:
            entries = fetch_funding_history(ticker, start_ms, end_ms)
        except Exception as e:
            print(f"  {ticker}: FAILED ({e})")
            continue

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
        con.commit()
        print(f"  {ticker}: {len(rows)} hourly funding entries")
        total += len(rows)
        time.sleep(0.2)  # be polite to the API

    print(f"\nDone. {total} funding rows backfilled into gap_log.db.")
    con.close()


if __name__ == "__main__":
    backfill()
