import requests
import time
import os
from datetime import datetime

ASSETS = [
    "xyz:NVDA", "xyz:TSLA", "xyz:AAPL", "xyz:AMZN", "xyz:MSFT",
    "xyz:GOOGL", "xyz:META", "xyz:NFLX", "xyz:AMD", "xyz:INTC",
    "xyz:COIN", "xyz:MSTR", "xyz:PLTR", "xyz:ARM", "xyz:TSM",
    "xyz:GME", "xyz:BB", "xyz:NOK", "xyz:HOOD", "xyz:ZM",
    "xyz:BABA", "xyz:MU", "xyz:QCOM", "xyz:AVGO", "xyz:ORCL",
    "xyz:NOW", "xyz:RIVN"
]

def fetch_prices():
    os.system('cls')
    print(f"  Hyperliquid Synthetic Stock Prices @ {datetime.now().strftime('%H:%M:%S')}  (Ctrl+C to stop)\n")

    for asset in ASSETS:
        resp = requests.post(
            "https://api.hyperliquid.xyz/info",
            json={"type": "l2Book", "coin": asset}
        ).json()

        label = asset.replace("xyz:", "")

        if resp and resp.get("levels"):
            bids = resp["levels"][0]
            asks = resp["levels"][1]
            if bids and asks:
                best_bid = float(bids[0]["px"])
                best_ask = float(asks[0]["px"])
                mid = (best_bid + best_ask) / 2
                print(f"  {label:6s}  ${mid:,.2f}")
            else:
                print(f"  {label:6s}  no liquidity")
        else:
            print(f"  {label:6s}  not found")

if __name__ == "__main__":
    print("Starting live price feed... press Ctrl+C to stop.")
    time.sleep(1)
    while True:
        fetch_prices()
        time.sleep(5)
