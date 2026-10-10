"""
Properly validates "raise the confidence bar above 70%" — the idea we
deliberately did NOT apply earlier because it was only checked once, against
the one time window reused all session. This checks it two ways: against
that familiar window (using the real model.pkl), and against a genuinely
fresh middle chunk of history the model has never seen (using a throwaway
model trained only on the earliest 60%) — same rigor as the gap-size check.

Nothing here changes risk.py, model.pkl, or any real file.
"""
import pickle
import risk
import backtest
from sklearn.ensemble import RandomForestClassifier
from events import load_data, build_features, build_events, time_split, FEATURES

CONF_LEVELS = [0.70, 0.75, 0.80, 0.85, 0.90]


def summarize(label, trades_df):
    if trades_df.empty:
        print(f"  {label:<22} no trades at all")
        return
    total = len(trades_df)
    wins  = (trades_df["outcome"] == "WIN").sum()
    pnl   = trades_df["pnl_usd"].sum()
    print(f"  {label:<22} {total:>4} trades   {wins/total*100:>5.1f}% win rate   "
          f"total ${pnl:>+7.2f}   avg ${pnl/total:>+6.3f}/trade")


print("=== Part A: against the familiar, already-reused test window (real model.pkl) ===")
with open("model.pkl", "rb") as f:
    real_model = pickle.load(f)

df = load_data()
df = build_features(df)
all_events = build_events(df).dropna(subset=FEATURES)
_, test_events = time_split(all_events)

original_conf = risk.MIN_CONFIDENCE
for conf in CONF_LEVELS:
    risk.MIN_CONFIDENCE     = conf
    backtest.MIN_CONFIDENCE = conf
    trades_df = backtest.run_backtest(test_events.copy(), real_model)
    summarize(f"{conf*100:.0f}% confidence bar:", trades_df)
risk.MIN_CONFIDENCE     = original_conf
backtest.MIN_CONFIDENCE = original_conf


print("\n=== Part B: against a fresh, never-seen middle chunk (throwaway model, earliest 60% only) ===")
all_events = all_events.sort_values("timestamp")
cutoff1 = all_events["timestamp"].quantile(0.60)
cutoff2 = all_events["timestamp"].quantile(0.80)
train  = all_events[all_events["timestamp"] <= cutoff1]
middle = all_events[(all_events["timestamp"] > cutoff1) & (all_events["timestamp"] <= cutoff2)]
print(f"  Fresh middle period: {cutoff1.date()} to {cutoff2.date()}, {len(middle)} events\n")

temp_model = RandomForestClassifier(
    n_estimators=200, max_depth=8, min_samples_leaf=10,
    random_state=42, n_jobs=-1, class_weight="balanced",
)
temp_model.fit(train[FEATURES], train["label"])

for conf in CONF_LEVELS:
    risk.MIN_CONFIDENCE     = conf
    backtest.MIN_CONFIDENCE = conf
    trades_df = backtest.run_backtest(middle.copy(), temp_model)
    summarize(f"{conf*100:.0f}% confidence bar:", trades_df)
risk.MIN_CONFIDENCE     = original_conf
backtest.MIN_CONFIDENCE = original_conf

print("\nDone. model.pkl, risk.py, and all real files are untouched.")
