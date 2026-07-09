"""
Minimal manual trade log.

Nothing in this project places real orders — every trade is a human
decision made after looking at scorer_web.py. This module is the record of
what you actually did, which two things depend on:

  1. Daily loss limit (risk.py) needs a real running P&L for today; there's
     nowhere else that number could come from.
  2. The live scorer needs to know a gap you already entered is still open,
     so it doesn't keep re-flagging it as a "new" signal every 5 minutes.

Usage from the command line:
    python trade_log.py enter AAPL LONG 500 -1.23
    python trade_log.py exit AAPL -0.15
    python trade_log.py status
"""
import sqlite3
import sys
from datetime import datetime, timezone

DB_FILE = "gap_log.db"


def _connect():
    con = sqlite3.connect(DB_FILE)
    con.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker           TEXT,
            direction        TEXT,
            position_usd     REAL,
            entry_time       TEXT,
            entry_gap_pct    REAL,
            exit_time        TEXT,
            exit_gap_pct     REAL,
            pnl_usd          REAL,
            status           TEXT
        )
    """)
    return con


def enter_trade(ticker: str, direction: str, position_usd: float, gap_pct: float) -> int:
    con = _connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cur = con.execute(
        "INSERT INTO trades (ticker, direction, position_usd, entry_time, entry_gap_pct, status) "
        "VALUES (?, ?, ?, ?, ?, 'open')",
        (ticker.upper(), direction.upper(), position_usd, now, gap_pct),
    )
    con.commit()
    trade_id = cur.lastrowid
    con.close()
    return trade_id


def exit_trade(ticker: str, exit_gap_pct: float) -> float:
    """Closes the oldest open trade for this ticker. Returns realized P&L in dollars."""
    con = _connect()
    row = con.execute(
        "SELECT id, position_usd, entry_gap_pct, direction FROM trades "
        "WHERE ticker = ? AND status = 'open' ORDER BY entry_time ASC LIMIT 1",
        (ticker.upper(),),
    ).fetchone()
    if row is None:
        con.close()
        raise ValueError(f"No open trade found for {ticker.upper()}")

    trade_id, position_usd, entry_gap_pct, direction = row
    gap_captured = abs(entry_gap_pct) - abs(exit_gap_pct)
    pnl = round((gap_captured / 100) * position_usd, 2)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    con.execute(
        "UPDATE trades SET exit_time = ?, exit_gap_pct = ?, pnl_usd = ?, status = 'closed' WHERE id = ?",
        (now, exit_gap_pct, pnl, trade_id),
    )
    con.commit()
    con.close()
    return pnl


def open_tickers() -> set:
    """Tickers with a currently-open manually-logged trade, for signal dedup."""
    con = _connect()
    rows = con.execute("SELECT DISTINCT ticker FROM trades WHERE status = 'open'").fetchall()
    con.close()
    return {r[0] for r in rows}


def daily_pnl(date: str | None = None) -> float:
    """Realized P&L (dollars) from trades closed today (UTC date)."""
    date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    con = _connect()
    row = con.execute(
        "SELECT COALESCE(SUM(pnl_usd), 0) FROM trades WHERE status = 'closed' AND exit_time LIKE ?",
        (f"{date}%",),
    ).fetchone()
    con.close()
    return round(row[0], 2)


def status():
    con = _connect()
    open_rows = con.execute(
        "SELECT ticker, direction, position_usd, entry_time, entry_gap_pct FROM trades WHERE status = 'open'"
    ).fetchall()
    con.close()
    print(f"Today's realized P&L: ${daily_pnl():+.2f}")
    print(f"Open positions: {len(open_rows)}")
    for r in open_rows:
        print(f"  {r[0]:<6} {r[1]:<6} ${r[2]:,.0f}  entered {r[3]}  @ {r[4]:+.2f}% gap")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "enter":
        _, _, ticker, direction, position_usd, gap_pct = sys.argv
        trade_id = enter_trade(ticker, direction, float(position_usd), float(gap_pct))
        print(f"Logged open trade #{trade_id}: {ticker.upper()} {direction.upper()} ${float(position_usd):,.0f}")
    elif cmd == "exit":
        _, _, ticker, gap_pct = sys.argv
        pnl = exit_trade(ticker, float(gap_pct))
        print(f"Closed {ticker.upper()}: P&L ${pnl:+.2f}")
    elif cmd == "status":
        status()
    else:
        print(__doc__)
