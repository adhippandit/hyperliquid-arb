import yfinance as yf
from datetime import datetime

TICKERS = [
    "NVDA", "TSLA", "AAPL", "AMZN", "MSFT",
    "GOOGL", "META", "NFLX", "AMD", "INTC",
    "COIN", "MSTR", "PLTR", "ARM", "TSM",
    "GME", "BB", "NOK", "HOOD", "ZM",
    "BABA", "MU", "QCOM", "AVGO", "ORCL",
    "NOW", "RIVN"
]

def fetch_real_prices():
    print(f"\n--- Real Stock Prices @ {datetime.now().strftime('%H:%M:%S')} ---\n")

    for ticker in TICKERS:
        stock = yf.Ticker(ticker)
        info = stock.fast_info
        price = info.last_price
        if price:
            print(f"  {ticker:6s}  ${price:,.2f}")
        else:
            print(f"  {ticker:6s}  no price available")

if __name__ == "__main__":
    fetch_real_prices()
