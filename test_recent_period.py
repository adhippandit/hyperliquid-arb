"""
Backtests model.pkl against gap events from the last DAYS_BACK days —
a rolling window measured back from the newest data actually collected,
not from today's date (so it still works correctly if the logger has
gaps) and not from model.pkl's training time (that broke the moment the
model got retrained on newer data, since "since training" then meant
"today"). Whether this window is still genuinely held-out depends on
where the current model's train/test split falls — check separately
(e.g. via events.py's time_split) before trusting this as out-of-sample.

Reuses build_events/run_backtest/print_summary from events.py and
backtest.py directly, so this is the same pipeline the live scorer and the
main backtest use — not a separate implementation. Nothing here retrains or
overwrites model.pkl.
"""
import pickle
from datetime import timedelta
from events import load_data, build_features, build_events
from backtest import run_backtest, print_summary

DAYS_BACK = 3

print("Loading data...", flush=True)
df = load_data()
df = build_features(df)

print("Collapsing into distinct gap events...", flush=True)
all_events = build_events(df)

newest = all_events["timestamp"].max()
WINDOW_START = newest - timedelta(days=DAYS_BACK)

recent = all_events[all_events["timestamp"] > WINDOW_START].copy()
end_date = recent["timestamp"].max().date() if not recent.empty else "n/a"
print(f"  Window start: {WINDOW_START}", flush=True)
print(f"  {len(recent):,} gap events in this window ({WINDOW_START.date()} -> {end_date})", flush=True)

with open("model.pkl", "rb") as f:
    model = pickle.load(f)

print("Running backtest on this unseen recent window...", flush=True)
trades_df = run_backtest(recent, model)

print_summary(trades_df)

if not trades_df.empty:
    OUT = "backtest_results_recent.csv"
    trades_df.to_csv(OUT, index=False)
    print(f"  Trade log saved to '{OUT}'")
