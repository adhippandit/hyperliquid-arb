"""
Fully automated TESTNET paper trading. The moment a gap clears every risk
check (confidence, VIX, daily loss limit, exposure cap), this places a real
order on Hyperliquid's testnet — fake money, real order-placement mechanics
— with no manual approval step, then logs it via trade_log.py.

SAFETY: this script can ONLY ever talk to Hyperliquid's TESTNET. The testnet
URL is hardcoded below (constants.TESTNET_API_URL) and there is no config
option, flag, or code path that points anywhere else. This is deliberate —
a misconfiguration should never be able to send a real order to mainnet.

Setup required before running (none of this is done by this script):
  1. A testnet wallet address + private key — create your own (e.g. via
     MetaMask, switched to Hyperliquid's testnet). This script never
     generates, sees, or needs a real-money wallet.
  2. Free testnet funds from the faucet at https://app.hyperliquid-testnet.xyz
  3. A local file named hyperliquid_testnet_config.json in this folder:
       {"account_address": "0xYOUR_ADDRESS", "secret_key": "0xYOUR_TESTNET_PRIVATE_KEY"}
     Already covered by .gitignore — never commit it or paste its contents
     anywhere, including into a chat.
"""
import json
import time
import pickle
from datetime import datetime

import eth_account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

import trade_log
from events import ticker_close_rates
from risk import MAX_OPEN_TRADES
from scorer_web import score_gaps, check_exits

CONFIG_FILE = "hyperliquid_testnet_config.json"
MODEL_FILE  = "model.pkl"
PERP_DEX    = "xyz"  # the HIP-3 builder-deployed dex hosting the tokenized-stock markets


def load_exchange():
    with open(CONFIG_FILE) as f:
        config = json.load(f)
    account = eth_account.Account.from_key(config["secret_key"])
    address = config["account_address"] or account.address

    info = Info(constants.TESTNET_API_URL, skip_ws=True, perp_dexs=[PERP_DEX])
    exchange = Exchange(
        account, constants.TESTNET_API_URL,
        account_address=address, perp_dexs=[PERP_DEX],
    )
    return address, info, exchange


def size_decimals(info, coin):
    for asset in info.meta(dex=PERP_DEX)["universe"]:
        if asset["name"] == coin:
            return asset["szDecimals"]
    return 3  # fallback if not found


def main():
    print("Loading model...", flush=True)
    with open(MODEL_FILE, "rb") as f:
        model = pickle.load(f)
    ticker_rates = ticker_close_rates()

    address, info, exchange = load_exchange()
    print(f"Connected to Hyperliquid TESTNET as {address}", flush=True)

    while True:
        try:
            (results, vix, vix_ok, h_to_open, market_open, now, todays_pnl, loss_limit_hit,
             stop_alerts, real_prices, hl_prices) = score_gaps(model, ticker_rates)

            exits = check_exits(real_prices, hl_prices)
            for ex in exits:
                coin = f"xyz:{ex['ticker']}"
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Closing TESTNET position: "
                      f"{coin} {ex['direction']} ({ex['reason']}) at gap={ex['exit_gap_pct']:+.2f}%", flush=True)

                result = exchange.market_close(coin)
                print(f"  Result: {result}", flush=True)

                pnl = trade_log.exit_trade(ex["ticker"], ex["exit_gap_pct"])
                print(f"  Realized P&L: ${pnl:+.2f}", flush=True)

            trades = [r for r in results if r["trade"]][:MAX_OPEN_TRADES]

            if not trades and not exits:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No trade signals this cycle.", flush=True)

            for r in trades:
                coin      = f"xyz:{r['ticker']}"
                direction = "SHORT" if r["gap_pct"] > 0 else "LONG"
                is_buy    = direction == "LONG"
                decimals  = size_decimals(info, coin)
                sz        = round(r["position"] / r["hl"], decimals)

                print(f"[{datetime.now().strftime('%H:%M:%S')}] Placing TESTNET order: "
                      f"{coin} {direction} size={sz} (~${r['position']:.0f}) "
                      f"confidence={r['confidence']*100:.1f}%", flush=True)

                result = exchange.market_open(coin, is_buy, sz)
                print(f"  Result: {result}", flush=True)

                trade_log.enter_trade(r["ticker"], direction, r["position"], r["gap_pct"])

            time.sleep(300)
        except KeyboardInterrupt:
            print("\nStopped.", flush=True)
            break
        except Exception as e:
            print(f"[ERROR] {e} — retrying in 60s", flush=True)
            time.sleep(60)


if __name__ == "__main__":
    main()
