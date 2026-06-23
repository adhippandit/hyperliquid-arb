import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests
import yfinance as yf
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from rich.align import Align

console = Console(file=sys.stdout, force_terminal=True)

STOCKS = {
    "NVDA":  "Nvidia          | AI chips, powers ChatGPT data centres",
    "TSLA":  "Tesla           | electric vehicles & energy",
    "AAPL":  "Apple           | iPhone, Mac, Services",
    "AMZN":  "Amazon          | e-commerce & AWS cloud",
    "MSFT":  "Microsoft       | Windows, Azure, Office 365",
    "GOOGL": "Google          | search, YouTube, Google Cloud",
    "META":  "Meta            | Facebook, Instagram, WhatsApp",
    "NFLX":  "Netflix         | streaming entertainment",
    "AMD":   "AMD             | chips competing with Nvidia & Intel",
    "INTC":  "Intel           | legacy chip maker",
    "COIN":  "Coinbase        | largest US crypto exchange",
    "MSTR":  "MicroStrategy   | corporate Bitcoin treasury",
    "PLTR":  "Palantir        | AI & data analytics for governments",
    "ARM":   "ARM Holdings    | chip architecture (powers every iPhone)",
    "TSM":   "TSMC            | world's largest chip manufacturer",
    "GME":   "GameStop        | meme stock, video game retailer",
    "BB":    "BlackBerry      | legacy tech, now cybersecurity",
    "NOK":   "Nokia           | legacy telecom equipment maker",
    "HOOD":  "Robinhood       | retail trading app",
    "ZM":    "Zoom            | video conferencing",
    "BABA":  "Alibaba         | China's Amazon",
    "MU":    "Micron          | memory chips (DRAM & NAND)",
    "QCOM":  "Qualcomm        | mobile chips (Snapdragon)",
    "AVGO":  "Broadcom        | networking & infrastructure chips",
    "ORCL":  "Oracle          | enterprise software & cloud",
    "NOW":   "ServiceNow      | enterprise workflow automation",
    "RIVN":  "Rivian          | electric truck startup",
}

def is_market_open():
    now_et = datetime.now(ZoneInfo("America/New_York"))
    if now_et.weekday() >= 5:
        return False
    open_time  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_time = now_et.replace(hour=16, minute=0,  second=0, microsecond=0)
    return open_time <= now_et <= close_time

def get_hyperliquid_price(ticker):
    try:
        resp = requests.post(
            "https://api.hyperliquid.xyz/info",
            json={"type": "l2Book", "coin": f"xyz:{ticker}"},
            timeout=5
        ).json()
        if resp and resp.get("levels"):
            bids, asks = resp["levels"][0], resp["levels"][1]
            if bids and asks:
                return (float(bids[0]["px"]) + float(asks[0]["px"])) / 2
    except:
        pass
    return None

def get_real_price(ticker):
    try:
        return yf.Ticker(ticker).fast_info.last_price
    except:
        return None

def fetch_all():
    data = []
    for ticker in STOCKS:
        real = get_real_price(ticker)
        hl   = get_hyperliquid_price(ticker)
        if real and hl:
            gap     = hl - real
            gap_pct = (gap / real) * 100
            data.append((ticker, real, hl, gap, gap_pct))
    data.sort(key=lambda x: abs(x[4]), reverse=True)
    return data

def render(data, countdown):
    console.clear()

    # Header
    status = "[bold green]OPEN[/bold green]" if is_market_open() else "[bold red]CLOSED[/bold red]"
    now    = datetime.now().strftime("%a %d %b %Y  %H:%M:%S")
    console.print(Panel(
        f"[bold white]  HYPERLIQUID ARB SCANNER[/bold white]"
        f"   [dim]{now}[/dim]"
        f"   NYSE: {status}  [dim](after-hours / weekend)[/dim]",
        style="blue", padding=(0, 1)
    ))
    console.print()

    # Table
    table = Table(
        box=box.SIMPLE_HEAVY,
        header_style="bold cyan",
        border_style="blue",
        padding=(0, 1),
    )
    table.add_column("",         width=2,  no_wrap=True)
    table.add_column("Ticker",   width=6,  style="bold white", no_wrap=True)
    table.add_column("Company & What They Do", width=48)
    table.add_column("Real Price",  width=13, justify="right", no_wrap=True)
    table.add_column("Hyperliquid", width=13, justify="right", no_wrap=True)
    table.add_column("Gap %",       width=9,  justify="right", no_wrap=True)
    table.add_column("Signal",      width=10, justify="center", no_wrap=True)

    opps = []
    for ticker, real, hl, gap, gap_pct in data:
        desc = STOCKS.get(ticker, ticker)

        if gap_pct > 1.0:
            icon, signal, gc = "[red]+[/red]", Text("SHORT HL", style="bold red"),    "red"
            opps.append((ticker, gap_pct, "SHORT", desc))
            row_style = ""
        elif gap_pct < -1.0:
            icon, signal, gc = "[green]-[/green]", Text("LONG HL", style="bold green"), "green"
            opps.append((ticker, gap_pct, "LONG",  desc))
            row_style = ""
        else:
            icon, signal, gc = "[dim].[/dim]", Text("--", style="dim"), "dim"
            row_style = "dim"

        table.add_row(
            icon, ticker, desc,
            f"${real:>11,.2f}",
            f"${hl:>11,.2f}",
            f"[{gc}]{gap_pct:+.2f}%[/{gc}]",
            signal,
            style=row_style,
        )

    console.print(table)
    console.print()

    # Top opportunity explanation
    if opps:
        ticker, gap_pct, direction, desc = opps[0]
        parts = desc.split("|")
        company = parts[0].strip()
        what    = parts[1].strip() if len(parts) > 1 else ""
        if direction == "LONG":
            msg = (
                f"[bold green]{ticker}[/bold green] ({company}) -- {what} -- "
                f"is [bold]{abs(gap_pct):.2f}% CHEAPER[/bold] on Hyperliquid than the real market.  "
                f"[dim]Strategy: buy on Hyperliquid, price should rise back to reality.[/dim]"
            )
        else:
            msg = (
                f"[bold red]{ticker}[/bold red] ({company}) -- {what} -- "
                f"is [bold]{abs(gap_pct):.2f}% MORE EXPENSIVE[/bold] on Hyperliquid than the real market.  "
                f"[dim]Strategy: short on Hyperliquid, price should fall back to reality.[/dim]"
            )
        console.print(Panel(
            f"[bold yellow]  TOP OPPORTUNITY[/bold yellow]   {msg}",
            style="yellow", padding=(0, 1)
        ))
        console.print()

    # Footer
    console.print(
        f"  [dim]{len(opps)} opportunities above 1% threshold  |  "
        f"Refreshing in [bold]{countdown}s[/bold]  |  Ctrl+C to quit[/dim]"
    )

REFRESH = 30

if __name__ == "__main__":
    console.print("[bold blue]  Starting scanner -- fetching live prices...[/bold blue]")
    try:
        while True:
            data = fetch_all()
            for countdown in range(REFRESH, 0, -1):
                render(data, countdown)
                time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[dim]  Scanner stopped.[/dim]")
