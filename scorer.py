import pickle
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
import time
import sys

console = Console(force_terminal=True)

MODEL_FILE = "model.pkl"

TICKERS = [
    "NVDA", "TSLA", "AAPL", "AMZN", "MSFT",
    "GOOGL", "META", "NFLX", "AMD", "INTC",
    "COIN", "MSTR", "PLTR", "ARM", "TSM",
    "GME", "BB", "NOK", "HOOD", "ZM",
    "BABA", "MU", "QCOM", "AVGO", "ORCL",
    "NOW", "RIVN",
]

DAY_MAP = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2,
    "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6
}

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
            "trade":      confidence >= CONFIDENCE_THRESHOLD,
        })

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results, vix, h_to_open, market_open, now

def render(results, vix, h_to_open, market_open, now):
    console.clear()

    status = "[bold green]OPEN[/bold green]" if market_open else "[bold red]CLOSED[/bold red]"
    console.print(Panel(
        f"[bold white]  HYPERLIQUID MODEL SCORER[/bold white]"
        f"   [dim]{now.strftime('%a %d %b %Y  %H:%M UTC')}[/dim]"
        f"   NYSE: {status}"
        f"   VIX: [bold]{vix}[/bold]"
        f"   Hours to open: [bold]{h_to_open}[/bold]",
        style="blue", padding=(0, 1)
    ))
    console.print()

    table = Table(box=box.SIMPLE_HEAVY, header_style="bold cyan", border_style="blue", padding=(0, 1))
    table.add_column("Ticker",      width=8,  style="bold white")
    table.add_column("Real Price",  width=13, justify="right")
    table.add_column("HL Price",    width=13, justify="right")
    table.add_column("Gap %",       width=10, justify="right")
    table.add_column("Confidence",  width=13, justify="right")
    table.add_column("Signal",      width=12, justify="center")

    trades = [r for r in results if r["trade"]]

    for r in results:
        gap_color = "red" if r["gap_pct"] > 0 else "green"
        conf_pct  = f"{r['confidence']*100:.1f}%"

        if r["trade"]:
            signal     = "[bold green]TRADE IT[/bold green]"
            row_style  = ""
        else:
            signal     = "[dim]skip[/dim]"
            row_style  = "dim"

        table.add_row(
            r["ticker"],
            f"${r['real']:>11,.2f}",
            f"${r['hl']:>11,.2f}",
            f"[{gap_color}]{r['gap_pct']:+.2f}%[/{gap_color}]",
            f"[bold]{conf_pct}[/bold]" if r["trade"] else conf_pct,
            signal,
            style=row_style,
        )

    console.print(table)
    console.print()

    if trades:
        console.print(Panel(
            f"[bold green]  {len(trades)} trade signal(s) above {CONFIDENCE_THRESHOLD*100:.0f}% confidence threshold[/bold green]",
            style="green", padding=(0, 1)
        ))
    else:
        console.print(Panel(
            "[dim]  No high-confidence opportunities right now. Waiting...[/dim]",
            style="dim", padding=(0, 1)
        ))

    console.print(f"\n  [dim]Refreshing in 5 minutes  |  Ctrl+C to quit[/dim]")

def main():
    console.print("[bold blue]  Loading model...[/bold blue]", end=" ")
    with open(MODEL_FILE, "rb") as f:
        model = pickle.load(f)
    console.print("[bold green]ready[/bold green]")
    console.print("[bold blue]  Fetching live prices...[/bold blue]\n")

    while True:
        try:
            results, vix, h_to_open, market_open, now = score_gaps(model)
            render(results, vix, h_to_open, market_open, now)
            time.sleep(300)
        except KeyboardInterrupt:
            console.print("\n[dim]  Scorer stopped.[/dim]")
            break
        except Exception as e:
            console.print(f"[red]  Error: {e} — retrying in 60s[/red]")
            time.sleep(60)

if __name__ == "__main__":
    main()
