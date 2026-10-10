"""
Sanity check on model.pkl: does it ever predict "did not close", or does it
always guess the same answer? Prints raw prediction counts vs actual counts
on the same held-out test set model.py evaluates on. Read-only — doesn't
retrain or change anything.
"""
import pickle
from events import load_data, build_features, build_events, time_split, FEATURES

print("Loading data...", flush=True)
df = load_data()
df = build_features(df)
events = build_events(df).dropna(subset=FEATURES)
_, test_df = time_split(events)

X_test = test_df[FEATURES]
y_test = test_df["label"]

with open("model.pkl", "rb") as f:
    model = pickle.load(f)

predictions = model.predict(X_test)

print(f"\nTest set size: {len(y_test):,} events\n")

print("What actually happened:")
print(f"  Closed:         {(y_test == 1).sum():,}")
print(f"  Did not close:  {(y_test == 0).sum():,}")

print("\nWhat the model predicted:")
print(f"  Closed:         {(predictions == 1).sum():,}")
print(f"  Did not close:  {(predictions == 0).sum():,}")

if (predictions == 0).sum() == 0:
    print("\n=> The model predicted 'Closed' for every single event. It never once guessed 'did not close.'")
elif (predictions == 1).sum() == 0:
    print("\n=> The model predicted 'Did not close' for every single event. It never once guessed 'closed.'")
else:
    print("\n=> The model predicted both outcomes at least once — it's not a single-answer rubber stamp.")
