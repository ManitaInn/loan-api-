"""Train the loan default model and save it as plain JSON (dev only: needs requirements-dev.txt).

The production image does not need scikit-learn: main.py reads the JSON
coefficients and computes the logistic regression with the standard library.
"""
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

FEATURES = ["amount_usd", "term_months", "monthly_income_usd", "age", "existing_loans"]
rng = np.random.default_rng(42)
n = 2000

amount = rng.uniform(100, 5000, n)
term = rng.integers(3, 61, n)
income = rng.uniform(150, 2000, n)
age = rng.integers(18, 70, n)
existing = rng.integers(0, 4, n)

# Synthetic rule: high monthly payment relative to income and many existing loans raise the risk.
payment_ratio = (amount / term) / income
logit = -3.0 + 6.0 * payment_ratio + 0.6 * existing - 0.01 * (age - 18)
default = rng.random(n) < 1 / (1 + np.exp(-logit))

X = np.column_stack([amount, term, income, age, existing])
scaler = StandardScaler().fit(X)
clf = LogisticRegression(max_iter=1000).fit(scaler.transform(X), default)

model = {
    "version": "1.0.0",
    "features": FEATURES,
    "mean": scaler.mean_.round(6).tolist(),
    "scale": scaler.scale_.round(6).tolist(),
    "coef": clf.coef_[0].round(6).tolist(),
    "intercept": round(float(clf.intercept_[0]), 6),
    "threshold": 0.5,
}
out = Path("model/model.json")
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(model, indent=2))
print(f"saved {out}  accuracy={clf.score(scaler.transform(X), default):.3f}")
