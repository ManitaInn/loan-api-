"""Step 5: monitor input drift and prediction drift for the champion model.

Simulates 14 days of production applications. Days 1-7 look like the training data; from day 8
the economy worsens (incomes fall, requested amounts rise). For each day we compute:
  - PSI (Population Stability Index) of every feature against the training data
  - the share of applicants the champion model predicts will default

Outputs: monitor_drift.png (the chart) and monitor_report.csv (the numbers).

PSI rule of thumb: < 0.10 stable, 0.10-0.25 moderate shift, > 0.25 major shift.

Run:  MLFLOW_TRACKING_URI=http://localhost:5000 python monitor.py
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mlflow
import numpy as np
import pandas as pd

from make_data import FEATURES, generate

INT_FEATURES = ["term_months", "age", "existing_loans"]
WARN_PSI, ALERT_PSI = 0.10, 0.25          # set from the chart, see the report
WARN_RATE_CHANGE = 0.05                    # +5 percentage points in predicted default rate


def psi(expected: pd.Series, actual: pd.Series, bins: int = 10) -> float:
    """Population Stability Index with quantile bins taken from the training data."""
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    e = np.histogram(expected, edges)[0] / len(expected)
    a = np.histogram(actual, edges)[0] / len(actual)
    e, a = np.clip(e, 1e-4, None), np.clip(a, 1e-4, None)
    return float(np.sum((a - e) * np.log(a / e)))


def daily_batches():
    for day in range(1, 15):
        drift = max(0, day - 7)                       # 0 for days 1-7, then 1, 2, ... 7
        yield day, generate(400, seed=1000 + day,
                            income_shift=1 - 0.05 * drift,    # income falls 5% per day after day 7
                            amount_shift=1 + 0.04 * drift)    # requested amounts rise 4% per day


def main():
    reference = pd.read_csv("data/loans.csv")
    model = mlflow.pyfunc.load_model("models:/loan-default@champion")

    def default_rate(df):
        X = df[FEATURES].copy()
        X[INT_FEATURES] = X[INT_FEATURES].astype("int64")
        return float((model.predict(X)[:, 1] >= 0.5).mean())

    baseline_rate = default_rate(reference)
    rows = []
    for day, batch in daily_batches():
        row = {"day": day, **{f"psi_{f}": round(psi(reference[f], batch[f]), 4) for f in FEATURES}}
        row["predicted_default_rate"] = round(default_rate(batch), 4)
        rows.append(row)
    report = pd.DataFrame(rows)
    report.to_csv("monitor_report.csv", index=False)

    psi_cols = [f"psi_{f}" for f in FEATURES]
    stable = report[report.day <= 7]
    print(f"Baseline predicted default rate (training data): {baseline_rate:.1%}")
    print(f"Days 1-7 (no drift): max PSI of any feature = {stable[psi_cols].to_numpy().max():.3f}, "
          f"predicted default rate {stable.predicted_default_rate.min():.1%}-{stable.predicted_default_rate.max():.1%}")
    print(report.to_string(index=False))
    for _, r in report.iterrows():
        worst = max(psi_cols, key=lambda c: r[c])
        level = "ALERT" if r[worst] > ALERT_PSI else "WARN" if r[worst] > WARN_PSI else "ok"
        if r.predicted_default_rate - baseline_rate > WARN_RATE_CHANGE and level == "ok":
            level = "WARN"
        if level != "ok":
            print(f"day {int(r.day):>2}: {level:<5} {worst[4:]} PSI={r[worst]:.3f}, "
                  f"predicted default rate {r.predicted_default_rate:.1%}")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    for f in FEATURES:
        ax1.plot(report.day, report[f"psi_{f}"], marker="o", label=f)
    ax1.axhline(WARN_PSI, color="orange", linestyle="--", label=f"warning PSI {WARN_PSI}")
    ax1.axhline(ALERT_PSI, color="red", linestyle="--", label=f"alert PSI {ALERT_PSI}")
    ax1.axvspan(0.5, 7.5, color="green", alpha=0.07, label="no drift (days 1-7)")
    ax1.set_ylabel("PSI vs training data")
    ax1.set_title("Input drift per feature")
    ax1.legend(fontsize=8, ncol=2)
    ax2.plot(report.day, report.predicted_default_rate * 100, marker="o", color="purple", label="predicted default rate")
    ax2.axhline(baseline_rate * 100, color="gray", linestyle=":", label=f"training baseline {baseline_rate:.1%}")
    ax2.axhline((baseline_rate + WARN_RATE_CHANGE) * 100, color="orange", linestyle="--", label="warning +5 pts")
    ax2.set_ylabel("% predicted to default")
    ax2.set_xlabel("production day")
    ax2.set_title("Prediction drift (champion model)")
    ax2.legend(fontsize=8)
    ax2.set_xticks(report.day)
    fig.tight_layout()
    fig.savefig("monitor_drift.png", dpi=120)
    print("saved monitor_drift.png and monitor_report.csv")


if __name__ == "__main__":
    main()
