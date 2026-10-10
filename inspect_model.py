"""Load model.pkl and print what's actually inside it — no training, read-only."""
import pickle
from events import FEATURES

MODEL_FILE = "model.pkl"

with open(MODEL_FILE, "rb") as f:
    model = pickle.load(f)

print(f"Model type: {type(model).__name__}")
print(f"Number of trees: {model.n_estimators}")
print(f"Max tree depth: {model.max_depth}")
print(f"Min samples per leaf: {model.min_samples_leaf}")
print(f"Classes it predicts: {list(model.classes_)}  (0 = did not close, 1 = closed)")

print("\nFeature importance (what it weighs most heavily when predicting):")
for feat, imp in sorted(zip(FEATURES, model.feature_importances_), key=lambda x: -x[1]):
    bar = "#" * int(imp * 50)
    print(f"  {feat:<20} {imp*100:5.1f}%  {bar}")
