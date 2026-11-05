from fastapi.testclient import TestClient

from main import app

GOOD = {"amount_usd": 1500, "term_months": 12, "monthly_income_usd": 450, "age": 34, "existing_loans": 1}


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_prediction_is_200_with_probability():
    with TestClient(app) as client:
        response = client.post("/predictions", json=GOOD)
    assert response.status_code == 200
    body = response.json()
    assert 0 <= body["default_probability"] <= 1
    assert isinstance(body["approved"], bool)


def test_high_risk_application_is_riskier():
    risky = {**GOOD, "amount_usd": 5000, "term_months": 3, "monthly_income_usd": 200, "existing_loans": 3}
    with TestClient(app) as client:
        low = client.post("/predictions", json=GOOD).json()["default_probability"]
        high = client.post("/predictions", json=risky).json()["default_probability"]
    assert high > low


def test_invalid_application_is_422():
    with TestClient(app) as client:
        response = client.post("/predictions", json={**GOOD, "age": 12})
    assert response.status_code == 422
