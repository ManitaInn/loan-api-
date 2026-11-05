"""Step 2: register the two best runs under `loan-default` and give them roles.

Selection rule (business metrics, see the memo in the report):
  1. keep runs with precision >= 0.50  (at most half of the applicants we flag are good borrowers)
  2. rank by recall (share of real defaulters we catch), then by ROC AUC
The best becomes `champion`, the second `challenger`. Each version gets a description.

Run:  MLFLOW_TRACKING_URI=http://localhost:5000 python register_models.py
"""
import os

import mlflow
from mlflow import MlflowClient

EXPERIMENT = "loan-default"
MODEL_NAME = "loan-default"
MIN_PRECISION = 0.50


def main():
    client = MlflowClient()
    ui = os.getenv("MLFLOW_UI_URL", mlflow.get_tracking_uri()).rstrip("/")
    exp = client.get_experiment_by_name(EXPERIMENT)
    runs = client.search_runs([exp.experiment_id], max_results=100)

    print(f"{'run':<14} {'type':<20} {'recall':>7} {'precision':>9} {'auc':>6}  link")
    for r in sorted(runs, key=lambda r: -r.data.metrics["recall"]):
        m = r.data.metrics
        print(f"{r.info.run_name:<14} {r.data.tags.get('model_type', ''):<20} {m['recall']:7.3f} "
              f"{m['precision']:9.3f} {m['roc_auc']:6.3f}  {ui}/#/experiments/{exp.experiment_id}/runs/{r.info.run_id}")

    eligible = [r for r in runs if r.data.metrics["precision"] >= MIN_PRECISION]
    ranked = sorted(eligible, key=lambda r: (r.data.metrics["recall"], r.data.metrics["roc_auc"]), reverse=True)
    champion_run, challenger_run = ranked[0], ranked[1]

    for alias, run in (("champion", champion_run), ("challenger", challenger_run)):
        m = run.data.metrics
        version = mlflow.register_model(f"runs:/{run.info.run_id}/model", MODEL_NAME)
        description = (f"{run.info.run_name} ({run.data.tags.get('model_type')}). Test set: "
                       f"recall {m['recall']:.3f}, precision {m['precision']:.3f}, ROC AUC {m['roc_auc']:.3f}. "
                       f"Registered as {alias}: "
                       + ("highest recall among runs with precision >= 0.50."
                          if alias == "champion" else "second-best recall; kept ready for rollback."))
        client.update_model_version(MODEL_NAME, version.version, description=description)
        client.set_registered_model_alias(MODEL_NAME, alias, version.version)
        print(f"\nversion {version.version} -> @{alias}: {description}")

    client.update_registered_model(MODEL_NAME, description=(
        "Predicts the probability that a loan applicant defaults. Serve with models:/loan-default@champion."))


if __name__ == "__main__":
    main()
