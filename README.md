# Loan Prediction API

FastAPI service that predicts the probability that a loan applicant defaults.

| File | Purpose |
|---|---|
| `main.py` | The API (`GET /health`, `POST /predictions`); model path from `MODEL_PATH` |
| `model/model.json` | Trained logistic-regression model (coefficients) |
| `train_model.py` | Re-trains the model (dev only, uses `requirements-dev.txt`) |
| `Dockerfile` | Development image (tests + reload) |
| `Dockerfile.prod` | Production image: multi-stage, slim, non-root, health check |
| `compose.yaml` | `api` (built from `Dockerfile.prod`) + Postgres `db` |
| `init.sql` | Creates the `predictions` table |
| `CHECKLIST.md` | Evidence for every production requirement |

## Run

```bash
docker compose up -d --build
# open http://localhost:8000/docs
```

## Example request

```bash
curl -X POST http://localhost:8000/predictions \
  -H "Content-Type: application/json" \
  -d '{"amount_usd": 1500, "term_months": 12, "monthly_income_usd": 450, "age": 34, "existing_loans": 1}'
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
