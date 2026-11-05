"""Step 1: train several loan-default models and track every run in MLflow.

7 runs across 3 model types (logistic regression, random forest, gradient boosting).
Each run logs its parameters, the business metrics (recall, precision, AUC, ...) and the
model with a signature, so the scoring server can reject malformed requests.

Run:  MLFLOW_TRACKING_URI=http://localhost:5000 python train_tracked.py
"""
import warnings

import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow.models import infer_signature
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

EXPERIMENT = "loan-default"
FEATURES = ["amount_usd", "term_months", "monthly_income_usd", "age", "existing_loans"]
INT_FEATURES = ["term_months", "age", "existing_loans"]
TARGET = "defaulted"
THRESHOLD = 0.5  # a probability at or above this means "predict default"

RUNS = [
    ("logreg_C0.1",   "logistic_regression", LogisticRegression(C=0.1, class_weight="balanced", max_iter=1000)),
    ("logreg_C1",     "logistic_regression", LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000)),
    ("logreg_C10",    "logistic_regression", LogisticRegression(C=10.0, class_weight="balanced", max_iter=1000)),
    ("rf_depth4",     "random_forest", RandomForestClassifier(n_estimators=200, max_depth=4, class_weight="balanced", random_state=42)),
    ("rf_depth8",     "random_forest", RandomForestClassifier(n_estimators=300, max_depth=8, class_weight="balanced", random_state=42)),
    ("gbm_lr0.05",    "gradient_boosting", GradientBoostingClassifier(n_estimators=200, learning_rate=0.05, max_depth=3, random_state=42)),
    ("gbm_lr0.1_d2",  "gradient_boosting", GradientBoostingClassifier(n_estimators=150, learning_rate=0.1, max_depth=2, random_state=42)),
]


def load_data():
    df = pd.read_csv("data/loans.csv")
    df[INT_FEATURES] = df[INT_FEATURES].astype("int64")
    df[["amount_usd", "monthly_income_usd"]] = df[["amount_usd", "monthly_income_usd"]].astype("float64")
    return train_test_split(df[FEATURES], df[TARGET], test_size=0.25, stratify=df[TARGET], random_state=42)


def main():
    warnings.filterwarnings("ignore", message=".*integer column.*")  # inputs never contain missing values
    mlflow.set_experiment(EXPERIMENT)
    X_train, X_test, y_train, y_test = load_data()

    for run_name, model_type, estimator in RUNS:
        pipeline = Pipeline([("scale", StandardScaler()), ("model", estimator)])
        with mlflow.start_run(run_name=run_name) as run:
            pipeline.fit(X_train, y_train)
            proba = pipeline.predict_proba(X_test)[:, 1]
            pred = (proba >= THRESHOLD).astype(int)

            metrics = {
                "recall": recall_score(y_test, pred),        # share of real defaulters we catch
                "precision": precision_score(y_test, pred),  # share of flagged applicants who really default
                "roc_auc": roc_auc_score(y_test, proba),     # ranking quality, threshold-free
                "f1": f1_score(y_test, pred),
                "accuracy": accuracy_score(y_test, pred),
            }
            mlflow.set_tag("model_type", model_type)
            mlflow.log_params({"model_type": model_type, "threshold": THRESHOLD,
                               **{k: v for k, v in estimator.get_params().items()
                                  if k in ("C", "n_estimators", "max_depth", "learning_rate", "class_weight")}})
            mlflow.log_metrics(metrics)

            signature = infer_signature(X_train, pipeline.predict_proba(X_train.head(5)))
            mlflow.sklearn.log_model(
                pipeline,
                name="model",
                signature=signature,
                input_example=X_train.head(2),
                pyfunc_predict_fn="predict_proba",  # serving returns [P(repay), P(default)]
                # We trained these trees ourselves, so their node storage is safe to load.
                skops_trusted_types=["sklearn.tree._tree.Tree"] if model_type != "logistic_regression" else None,
            )
            print(f"{run_name:<14} {model_type:<20} recall={metrics['recall']:.3f} "
                  f"precision={metrics['precision']:.3f} auc={metrics['roc_auc']:.3f}  run_id={run.info.run_id}")


if __name__ == "__main__":
    main()
