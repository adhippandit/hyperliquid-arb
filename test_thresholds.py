"""
Tries different confidence bars and different minimum gap sizes against the
same held-out test period, to see which actually improves the honest,
fee-inclusive P&L — instead of guessing. Read-only: doesn't change model.pkl,
risk.py, or events.py; settings are patched in memory for this run only.
"""
import pickle
import risk
import events
import backtest
from events import load_data, build_features, build_events, time_split, FEATURES

with open("model.pkl", "rb") as f:
    model = pickle.load(f)


def summarize(label, trades_df):
    if trades_df.empty:
        print(f"  {label:<22} no trades at all")
        return
    total = len(trades_df)
    wins  = (trades_df["outcome"] == "WIN").sum()
    pnl   = trades_df["pnl_usd"].sum()
    print(f"  {label:<22} {total:>4} trades   {wins/total*100:>5.1f}% win rate   "
          f"total ${pnl:>+7.2f}   avg ${pnl/total:>+6.3f}/trade")


print("=== Raising the confidence bar ===")
df = load_data()
df = build_features(df)
all_events = build_events(df).dropna(subset=FEATURES)
_, test_events = time_split(all_events)

original_conf = risk.MIN_CONFIDENCE
for conf in [0.70, 0.75, 0.80, 0.85, 0.90]:
    risk.MIN_CONFIDENCE     = conf
    backtest.MIN_CONFIDENCE = conf
    trades_df = backtest.run_backtest(test_events.copy(), model)
    summarize(f"{conf*100:.0f}% confidence bar:", trades_df)
risk.MIN_CONFIDENCE     = original_conf
backtest.MIN_CONFIDENCE = original_conf


print("\n=== Raising the minimum gap size ===")
original_threshold = events.SIGNAL_THRESHOLD
for gap_min in [0.5, 0.75, 1.0, 1.5, 2.0]:
    events.SIGNAL_THRESHOLD = gap_min
    df2 = load_data()
    df2 = build_features(df2)
    ev  = build_events(df2).dropna(subset=FEATURES)
    _, test_ev = time_split(ev)
    trades_df = backtest.run_backtest(test_ev.copy(), model)
    summarize(f"min gap {gap_min}%:", trades_df)
events.SIGNAL_THRESHOLD = original_threshold

print("\nDone. Nothing was changed permanently — model.pkl, risk.py, and events.py are untouched.")
