# Model lifecycle with MLflow

| File | Step |
|---|---|
| `make_data.py` | creates `data/loans.csv` (6,000 past applications) |
| `train_tracked.py` | Step 1: 7 tracked runs, 3 model types |
| `register_models.py` | Step 2: registers the 2 best runs as `loan-default`, sets `champion` / `challenger` + descriptions |
| `api_mlflow.py` | Step 4: FastAPI that loads `models:/loan-default@champion` (by alias) |
| `monitor.py` | Step 5: drift chart `monitor_drift.png` |
| `set_champion.py` | Step 6: moves the `champion` alias (rollback / promotion) |

## The three programs

| Terminal | Program | Port |
|---|---|---|
| 1 | MLflow tracking server + model registry (UI) | 5000 |
| 2 | MLflow scoring server for `@champion` | 5001 |
| 3 | FastAPI (`api_mlflow.py`) | 8000 |

```bash
# Terminal 1
pip install -r requirements-mlflow.txt
mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri sqlite:///mlflow.db --artifacts-destination ./mlartifacts

# Terminal 4 (work terminal), once
export MLFLOW_TRACKING_URI=http://localhost:5000
python make_data.py && python train_tracked.py && python register_models.py

# Terminal 2
export MLFLOW_TRACKING_URI=http://localhost:5000
mlflow models serve -m "models:/loan-default@champion" --host 0.0.0.0 -p 5001 --env-manager local

# Terminal 3
export MLFLOW_TRACKING_URI=http://localhost:5000
uvicorn api_mlflow:app --host 0.0.0.0 --port 8000
```
