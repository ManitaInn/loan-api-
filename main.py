"""Loan prediction API.

Configuration comes only from environment variables:
  MODEL_PATH    path to the model JSON file          (default: model/model.json)
  DATABASE_URL  optional Postgres URL; when set, every prediction is saved
"""
import json
import logging
import math
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

MODEL_PATH = Path(os.getenv("MODEL_PATH", "model/model.json"))
DATABASE_URL = os.getenv("DATABASE_URL")  # never hard-coded: set by compose.yaml or the platform

log = logging.getLogger("loan-api")
state: dict = {}


def load_model(path: Path) -> dict:
    model = json.loads(path.read_text())
    for key in ("features", "mean", "scale", "coef", "intercept", "threshold"):
        if key not in model:
            raise ValueError(f"model file {path} is missing '{key}'")
    return model


def save_prediction(application: dict, probability: float, approved: bool) -> None:
    """Store the prediction when a database is configured; the API still works without one."""
    if not DATABASE_URL:
        return
    try:
        import psycopg

        with psycopg.connect(DATABASE_URL, connect_timeout=3) as conn:
            conn.execute(
                "INSERT INTO predictions (amount_usd, term_months, monthly_income_usd, age, "
                "existing_loans, default_probability, approved) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (*[application[f] for f in state["model"]["features"]], probability, approved),
            )
    except Exception as exc:  # a database problem must not break predictions
        log.warning("could not save prediction: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["model"] = load_model(MODEL_PATH)
    yield
    state.clear()


app = FastAPI(title="Loan Prediction API", version="1.0.0", lifespan=lifespan)


class LoanApplication(BaseModel):
    amount_usd: float = Field(..., gt=0, le=50000, description="Requested loan amount in US dollars", examples=[1500])
    term_months: int = Field(..., ge=1, le=60, description="Repayment period in months", examples=[12])
    monthly_income_usd: float = Field(..., gt=0, description="Borrower's monthly income in US dollars", examples=[450])
    age: int = Field(..., ge=18, le=100, description="Borrower's age in years", examples=[34])
    existing_loans: int = Field(..., ge=0, le=20, description="Number of loans the borrower already has", examples=[1])


class Prediction(BaseModel):
    default_probability: float = Field(..., description="Probability (0-1) that the borrower defaults")
    approved: bool = Field(..., description="True when the probability is below the model threshold")
    model_version: str


@app.get("/health")
def health():
    """Used by the Docker HEALTHCHECK and by Compose."""
    if "model" not in state:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {"status": "ok", "model_version": state["model"].get("version", "unknown")}


@app.post("/predictions", response_model=Prediction, status_code=200)
def predict(application: LoanApplication):
    model = state["model"]
    values = application.model_dump()
    z = model["intercept"] + sum(
        c * (values[f] - m) / s
        for f, m, s, c in zip(model["features"], model["mean"], model["scale"], model["coef"])
    )
    probability = round(1 / (1 + math.exp(-z)), 4)
    approved = probability < model["threshold"]
    save_prediction(values, probability, approved)
    return Prediction(default_probability=probability, approved=approved,
                      model_version=model.get("version", "unknown"))
