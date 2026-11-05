"""Create the loan applications dataset used for training (data/loans.csv).

Each row is one past application; `defaulted` is 1 when the borrower did not repay.
"""
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES = ["amount_usd", "term_months", "monthly_income_usd", "age", "existing_loans"]


def generate(n: int, seed: int, income_shift: float = 1.0, amount_shift: float = 1.0) -> pd.DataFrame:
    """Synthetic but realistic applications; the shifts are used by monitor.py to simulate drift."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "amount_usd": (rng.gamma(2.0, 900, n) * amount_shift).clip(100, 20000).round(2),
        "term_months": rng.choice([3, 6, 12, 18, 24, 36, 48, 60], n),
        "monthly_income_usd": (rng.lognormal(6.7, 0.45, n) * income_shift).clip(120, 6000).round(2),
        "age": rng.integers(18, 70, n),
        "existing_loans": rng.poisson(1.1, n).clip(0, 8),
    })
    payment_ratio = (df.amount_usd / df.term_months) / df.monthly_income_usd
    logit = (-3.2 + 5.5 * payment_ratio + 0.55 * df.existing_loans
             - 0.015 * (df.age - 18) + 0.8 * (df.term_months <= 6))
    df["defaulted"] = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    return df


if __name__ == "__main__":
    out = Path("data/loans.csv")
    out.parent.mkdir(exist_ok=True)
    data = generate(6000, seed=42)
    data.to_csv(out, index=False)
    print(f"saved {out}: {len(data)} rows, default rate {data.defaulted.mean():.1%}")
