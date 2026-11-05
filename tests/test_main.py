import os

from fastapi.testclient import TestClient

from main import app

GOOD = {"amount_usd": 1500, "term_months": 12, "monthly_income_usd": 450, "age": 34, "existing_loans": 1}
AUTH = {"X-API-Key": os.environ["API_KEY"]}


def test_health_is_public_and_shows_release():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "git_sha" in body


def test_prediction_is_200_with_probability():
    with TestClient(app) as client:
        response = client.post("/predictions", json=GOOD, headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert 0 <= body["default_probability"] <= 1
    assert isinstance(body["approved"], bool)


def test_high_risk_application_is_riskier():
    risky = {**GOOD, "amount_usd": 5000, "term_months": 3, "monthly_income_usd": 200, "existing_loans": 3}
    with TestClient(app) as client:
        low = client.post("/predictions", json=GOOD, headers=AUTH).json()["default_probability"]
        high = client.post("/predictions", json=risky, headers=AUTH).json()["default_probability"]
    assert high > low


def test_invalid_application_is_422():
    with TestClient(app) as client:
        response = client.post("/predictions", json={**GOOD, "age": 12}, headers=AUTH)
    assert response.status_code == 422


# --- the three API-key checks ---
def test_missing_api_key_is_401():
    with TestClient(app) as client:
        assert client.post("/predictions", json=GOOD).status_code == 401


def test_wrong_api_key_is_403():
    with TestClient(app) as client:
        assert client.post("/predictions", json=GOOD, headers={"X-API-Key": "wrong"}).status_code == 403


def test_correct_api_key_is_200():
    with TestClient(app) as client:
        assert client.post("/predictions", json=GOOD, headers=AUTH).status_code == 200


# --- risk_level (added in the improvement PR) ---
def test_prediction_includes_risk_level():
    safe = {"amount_usd": 800, "term_months": 24, "monthly_income_usd": 1800, "age": 45, "existing_loans": 0}
    risky = {"amount_usd": 5000, "term_months": 3, "monthly_income_usd": 200, "age": 22, "existing_loans": 3}
    with TestClient(app) as client:
        assert client.post("/predictions", json=safe, headers=AUTH).json()["risk_level"] == "low"
        assert client.post("/predictions", json=risky, headers=AUTH).json()["risk_level"] == "high"


# --- added after the bad-release drill: a threshold change declined every borrower in production ---
SAFE = {"amount_usd": 800, "term_months": 24, "monthly_income_usd": 1800, "age": 45, "existing_loans": 0}
RISKY = {"amount_usd": 5000, "term_months": 3, "monthly_income_usd": 200, "age": 22, "existing_loans": 3}


def test_model_threshold_is_in_a_sane_range():
    import json
    threshold = json.load(open("model/model.json"))["threshold"]
    assert 0.2 <= threshold <= 0.8, f"approval threshold {threshold} would approve or decline almost everyone"


def test_clearly_safe_applicant_is_approved():
    with TestClient(app) as client:
        assert client.post("/predictions", json=SAFE, headers=AUTH).json()["approved"] is True


def test_clearly_risky_applicant_is_declined():
    with TestClient(app) as client:
        assert client.post("/predictions", json=RISKY, headers=AUTH).json()["approved"] is False
