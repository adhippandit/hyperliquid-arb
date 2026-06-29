import sqlite3
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import pickle

DB_FILE    = "gap_log.db"
MODEL_FILE = "model.pkl"

# How small the gap must get for us to consider it "closed"
CLOSE_THRESHOLD = 0.3

# How many hours forward we look to see if the gap closed
HORIZON_HOURS = 48

def load_data():
    con = pd.read_sql("SELECT * FROM gaps ORDER BY id", sqlite3.connect(DB_FILE))
    con["timestamp"] = pd.to_datetime(con["timestamp"])
    return con

def label_gaps(df):
    """
    For each row, look forward up to HORIZON_HOURS and check if the gap
    for that ticker came back below CLOSE_THRESHOLD. Label 1 if yes, 0 if no.
    """
    df = df.copy()
    df["label"] = 0

    for ticker in df["ticker"].unique():
        ticker_df = df[df["ticker"] == ticker].copy()

        for idx, row in ticker_df.iterrows():
            # Only label gaps that are meaningful (above 0.5%)
            if abs(row["gap_pct"]) < 0.5:
                df.at[idx, "label"] = -1  # too small to bother trading
                continue

            # Look at all future observations for this ticker within 48 hours
            future = ticker_df[
                (ticker_df["timestamp"] > row["timestamp"]) &
                (ticker_df["timestamp"] <= row["timestamp"] + pd.Timedelta(hours=HORIZON_HOURS))
            ]

            if future.empty:
                df.at[idx, "label"] = -1  # no future data, cannot label
                continue

            # Did the gap close?
            if (future["gap_pct"].abs() < CLOSE_THRESHOLD).any():
                df.at[idx, "label"] = 1  # gap closed — good trade
            else:
                df.at[idx, "label"] = 0  # gap did not close — bad trade

    return df

def build_features(df):
    df = df.copy()

    # Convert day of week to a number (Monday=0, Sunday=6)
    day_map = {
        "Monday": 0, "Tuesday": 1, "Wednesday": 2,
        "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6
    }
    df["day_num"]    = df["day_of_week"].map(day_map)
    df["is_weekend"] = df["day_num"].isin([5, 6]).astype(int)
    df["gap_abs"]    = df["gap_pct"].abs()

    return df

FEATURES = [
    "gap_abs",
    "is_weekend",
    "day_num",
    "hour_utc",
    "hours_to_open",
    "vix",
    "bid_ask_spread_pct",
]

def train():
    print("Loading data...", flush=True)
    df = load_data()
    print(f"  {len(df):,} total rows loaded", flush=True)

    print("Labelling gaps...", flush=True)
    df = label_gaps(df)

    # Remove rows we could not label
    df = df[df["label"] != -1]
    print(f"  {len(df):,} rows labelled", flush=True)
    print(f"  Gaps that closed:     {df['label'].sum():,} ({df['label'].mean()*100:.1f}%)", flush=True)
    print(f"  Gaps that did not:    {(df['label']==0).sum():,} ({(df['label']==0).mean()*100:.1f}%)", flush=True)

    print("Building features...", flush=True)
    df = build_features(df)
    df = df.dropna(subset=FEATURES)

    X = df[FEATURES]
    y = df["label"]

    print("Splitting into training and test sets...", flush=True)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"  Training set: {len(X_train):,} rows", flush=True)
    print(f"  Test set:     {len(X_test):,} rows", flush=True)

    print("Training Random Forest...", flush=True)
    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=10,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    print("Evaluating model...", flush=True)
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"\n  Accuracy: {acc*100:.1f}%", flush=True)
    print("\n  Full report:", flush=True)
    print(classification_report(y_test, y_pred, target_names=["Did not close", "Closed"]), flush=True)

    print("Feature importance (what the model cares about most):", flush=True)
    for feat, imp in sorted(zip(FEATURES, model.feature_importances_), key=lambda x: -x[1]):
        print(f"  {feat:<25} {imp*100:.1f}%", flush=True)

    print(f"\nSaving model to '{MODEL_FILE}'...", flush=True)
    with open(MODEL_FILE, "wb") as f:
        pickle.dump(model, f)
    print("Done. Model is ready.", flush=True)

if __name__ == "__main__":
    train()
