"""Step 6: move the `champion` alias to another version (promotion or rollback).

Usage:  MLFLOW_TRACKING_URI=http://localhost:5000 python set_champion.py <version>
Then restart FastAPI: it loads models:/loan-default@champion at startup.
"""
import sys

from mlflow import MlflowClient

MODEL_NAME = "loan-default"


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python set_champion.py <version>")
    target = sys.argv[1]
    client = MlflowClient()
    before = client.get_model_version_by_alias(MODEL_NAME, "champion").version
    client.set_registered_model_alias(MODEL_NAME, "champion", target)
    others = {v.version for v in client.search_model_versions(f"name='{MODEL_NAME}'")} - {target}
    if before in others:   # keep the previous champion one step away as the challenger
        client.set_registered_model_alias(MODEL_NAME, "challenger", before)
    print("aliases now:", client.get_registered_model(MODEL_NAME).aliases)
    print(f"champion moved: version {before} -> version {target}. Restart FastAPI to load it.")


if __name__ == "__main__":
    main()
