"""FastAPI service that serves whichever model version holds the `champion` alias.

It never names a file or a version number: MODEL_URI defaults to models:/loan-default@champion.
Moving the alias in the registry and restarting this service is the whole promotion/rollback.

Run:  MLFLOW_TRACKING_URI=http://localhost:5000 uvicorn api_mlflow:app --port 8000
"""
import os
from contextlib import asynccontextmanager

import mlflow
import pandas as pd
from fastapi import FastAPI, HTTPException
from mlflow import MlflowClient
from pydantic import BaseModel, Field

MODEL_NAME = os.getenv("MODEL_NAME", "loan-default")
MODEL_ALIAS = os.getenv("MODEL_ALIAS", "champion")
MODEL_URI = f"models:/{MODEL_NAME}@{MODEL_ALIAS}"
FEATURES = ["amount_usd", "term_months", "monthly_income_usd", "age", "existing_loans"]
INT_FEATURES = ["term_months", "age", "existing_loans"]
THRESHOLD = 0.5

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Resolve the alias once at startup, then load exactly that version.
    version = MlflowClient().get_model_version_by_alias(MODEL_NAME, MODEL_ALIAS)
    state["model"] = mlflow.pyfunc.load_model(MODEL_URI)
    state["version"] = version.version
    state["run_id"] = version.run_id
    yield
    state.clear()


app = FastAPI(title="Loan Prediction API (MLflow registry)", version="2.0.0", lifespan=lifespan)


class LoanApplication(BaseModel):
    amount_usd: float = Field(..., gt=0, le=50000, description="Requested loan amount in US dollars", examples=[1500])
    term_months: int = Field(..., ge=1, le=60, description="Repayment period in months", examples=[12])
    monthly_income_usd: float = Field(..., gt=0, description="Monthly income in US dollars", examples=[450])
    age: int = Field(..., ge=18, le=100, description="Age in years", examples=[34])
    existing_loans: int = Field(..., ge=0, le=20, description="Loans the borrower already has", examples=[1])


def to_frame(application: LoanApplication) -> pd.DataFrame:
    df = pd.DataFrame([application.model_dump()])[FEATURES]
    df[INT_FEATURES] = df[INT_FEATURES].astype("int64")  # must match the model signature
    return df


@app.get("/health")
def health():
    if "model" not in state:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {"status": "ok", "model_uri": MODEL_URI, "model_version": state["version"], "run_id": state["run_id"]}


@app.post("/predictions")
def predict(application: LoanApplication):
    proba = state["model"].predict(to_frame(application))  # [[P(repay), P(default)]]
    p_default = float(proba[0][1])
    return {
        "default_probability": round(p_default, 6),
        "approved": p_default < THRESHOLD,
        "model_uri": MODEL_URI,
        "model_version": state["version"],
    }
