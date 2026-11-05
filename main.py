"""Loan prediction API.

Configuration comes only from environment variables:
  MODEL_PATH    path to the model JSON file          (default: model/model.json)
  API_KEY       key clients must send in the X-API-Key header to call /predictions
  DATABASE_URL  optional Postgres URL; when set, every prediction is saved
  GIT_SHA       commit the image was built from (set by the pipeline, shown on /health)
"""
import json
import logging
import math
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

MODEL_PATH = Path(os.getenv("MODEL_PATH", "model/model.json"))
DATABASE_URL = os.getenv("DATABASE_URL")  # never hard-coded: set by compose.yaml or the platform
GIT_SHA = os.getenv("GIT_SHA", "unknown")  # not a secret: identifies the release
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

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


app = FastAPI(title="Loan Prediction API", version="1.1.0", lifespan=lifespan)


def require_api_key(key: str | None = Security(api_key_header)) -> None:
    """401 when the header is missing, 403 when it is wrong. The key lives only in the environment."""
    expected = os.getenv("API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="API key not configured")
    if key is None:
        raise HTTPException(status_code=401, detail="Missing API key", headers={"WWW-Authenticate": "API-Key"})
    if not secrets.compare_digest(key, expected):
        raise HTTPException(status_code=403, detail="Invalid API key")


class LoanApplication(BaseModel):
    amount_usd: float = Field(..., gt=0, le=50000, description="Requested loan amount in US dollars", examples=[1500])
    term_months: int = Field(..., ge=1, le=60, description="Repayment period in months", examples=[12])
    monthly_income_usd: float = Field(..., gt=0, description="Borrower's monthly income in US dollars", examples=[450])
    age: int = Field(..., ge=18, le=100, description="Borrower's age in years", examples=[34])
    existing_loans: int = Field(..., ge=0, le=20, description="Number of loans the borrower already has", examples=[1])


RISK_BANDS = [(0.15, "low"), (0.40, "medium"), (1.01, "high")]  # upper bounds on the default probability


def risk_level(probability: float) -> str:
    return next(label for upper, label in RISK_BANDS if probability < upper)


class Prediction(BaseModel):
    default_probability: float = Field(..., description="Probability (0-1) that the borrower defaults")
    risk_level: str = Field(..., description="low (< 0.15), medium (< 0.40) or high: for loan officers at a glance")
    approved: bool = Field(..., description="True when the probability is below the model threshold")
    model_version: str


@app.get("/health")
def health():
    """Used by the Docker HEALTHCHECK and by Compose."""
    if "model" not in state:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {"status": "ok", "git_sha": GIT_SHA, "model_version": state["model"].get("version", "unknown")}


@app.post("/predictions", response_model=Prediction, status_code=200, dependencies=[Depends(require_api_key)])
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
    return Prediction(default_probability=probability, risk_level=risk_level(probability), approved=approved,
                      model_version=model.get("version", "unknown"))
