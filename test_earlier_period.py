"""
Checks whether "trade bigger gaps" holds up on a genuinely different, never-
tested-on stretch of time, not just the one 17-day window we've been reusing.

Splits history into three chronological chunks instead of two:
  - earliest 60%  -> train a fresh temporary model on this only
  - middle 20%    -> the fresh test period this script actually checks
  - final 20%     -> the window already used repeatedly elsewhere, skipped here

This is a completely separate model from model.pkl — nothing here overwrites
the real model or changes any file.
"""
import events
import backtest
from sklearn.ensemble import RandomForestClassifier
from events import load_data, build_features, build_events, FEATURES

def three_way_split(all_events):
    all_events = all_events.sort_values("timestamp")
    cutoff1 = all_events["timestamp"].quantile(0.60)
    cutoff2 = all_events["timestamp"].quantile(0.80)
    train  = all_events[all_events["timestamp"] <= cutoff1]
    middle = all_events[(all_events["timestamp"] > cutoff1) & (all_events["timestamp"] <= cutoff2)]
    return train, middle, cutoff1, cutoff2

def run_for_gap_min(gap_min, label):
    events.SIGNAL_THRESHOLD = gap_min
    df = load_data()
    df = build_features(df)
    all_events = build_events(df).dropna(subset=FEATURES)
    train, middle, cutoff1, cutoff2 = three_way_split(all_events)

    model = RandomForestClassifier(
        n_estimators=200, max_depth=8, min_samples_leaf=10,
        random_state=42, n_jobs=-1, class_weight="balanced",
    )
    model.fit(train[FEATURES], train["label"])

    backtest.MIN_CONFIDENCE = 0.70
    trades_df = backtest.run_backtest(middle.copy(), model)

    if trades_df.empty:
        print(f"  {label:<14} middle period {cutoff1.date()} to {cutoff2.date()}, "
              f"{len(middle)} events — no trades met the bar")
        return

    total = len(trades_df)
    wins  = (trades_df["outcome"] == "WIN").sum()
    pnl   = trades_df["pnl_usd"].sum()
    print(f"  {label:<14} middle period {cutoff1.date()} to {cutoff2.date()}, "
          f"{len(middle)} events -> {total} trades, {wins/total*100:.1f}% win rate, "
          f"total ${pnl:+.2f}, avg ${pnl/total:+.3f}/trade")

print("Testing on a fresh, never-before-used middle chunk of history:\n")
original_threshold = events.SIGNAL_THRESHOLD
run_for_gap_min(0.5, "min gap 0.5%:")
run_for_gap_min(2.0, "min gap 2.0%:")
events.SIGNAL_THRESHOLD = original_threshold

print("\nDone. model.pkl and all project files are untouched — this used a throwaway model.")
