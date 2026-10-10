from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score
import pickle
from events import load_data, build_features, build_events, time_split, FEATURES

MODEL_FILE = "model.pkl"


def train():
    print("Loading data...", flush=True)
    df = load_data()
    print(f"  {len(df):,} total rows loaded", flush=True)

    df = build_features(df)

    print("Collapsing into distinct gap events (one row per dislocation, not per 5-min snapshot)...", flush=True)
    events = build_events(df)
    events = events.dropna(subset=FEATURES)
    print(f"  {len(events):,} distinct events (from {len(df):,} raw rows)", flush=True)
    print(f"  Gaps that closed:  {events['label'].sum():,} ({events['label'].mean()*100:.1f}%)", flush=True)
    print(f"  Gaps that did not: {(events['label']==0).sum():,} ({(events['label']==0).mean()*100:.1f}%)", flush=True)

    print("Splitting by time — train on the earliest 80%, test on the most recent 20%...", flush=True)
    train_df, test_df = time_split(events)
    print(f"  Train: {len(train_df):,} events  |  Test: {len(test_df):,} events", flush=True)

    X_train, y_train = train_df[FEATURES], train_df["label"]
    X_test,  y_test  = test_df[FEATURES],  test_df["label"]

    print("Training Random Forest...", flush=True)
    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=10,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced",
    )
    model.fit(X_train, y_train)

    print("Evaluating on the held-out future 20% (events the model never trained on)...", flush=True)
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"\n  Accuracy: {acc*100:.1f}%", flush=True)
    print("\n  Full report:", flush=True)
    print(classification_report(y_test, y_pred, target_names=["Did not close", "Closed"]), flush=True)

    print("Feature importance (what the model cares about most):", flush=True)
    for feat, imp in sorted(zip(FEATURES, model.feature_importances_), key=lambda x: -x[1]):
        print(f"  {feat:<25} {imp*100:.1f}%", flush=True)

    print(f"\nSaving model to '{MODEL_FILE}' (trained on the earliest 80% of events only)...", flush=True)
    with open(MODEL_FILE, "wb") as f:
        pickle.dump(model, f)
    print("Done. Model is ready.", flush=True)


if __name__ == "__main__":
    train()
