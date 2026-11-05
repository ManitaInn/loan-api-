"""Verify a release on the live app (run by the pipeline after every deploy).

Usage:
  python scripts/verify_release.py --expect-sha <sha>        # after a normal deploy
  python scripts/verify_release.py --expect-not-sha <sha>    # after a rollback

Environment: APP_URL (e.g. https://loan-api-xxxx.onrender.com), API_KEY,
             MERGED_AT (ISO time of the merge, optional: used to report merge-to-live time).

Checks, in order:
  1. /health answers 200 and reports the expected commit (waits up to --timeout seconds:
     Render's free plan may need ~1 minute to wake up and switch to the new image)
  2. API key: missing -> 401, wrong -> 403, correct -> 200
  3. Business sanity: probabilities are in [0, 1], a clearly safe applicant is approved,
     a clearly risky applicant is declined
Exits 1 on the first failure, so the pipeline can roll back.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

SAFE = {"amount_usd": 800, "term_months": 24, "monthly_income_usd": 1800, "age": 45, "existing_loans": 0}
RISKY = {"amount_usd": 5000, "term_months": 3, "monthly_income_usd": 200, "age": 22, "existing_loans": 3}


def call(method, url, body=None, headers=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as err:
        return err.code, None
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None, None


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--expect-sha")
    group.add_argument("--expect-not-sha")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    base = os.environ["APP_URL"].rstrip("/")
    key = os.environ["API_KEY"]
    started = time.time()

    # 1. wait for the new release to be live
    print(f"Waiting for {base}/health ...")
    while True:
        status, body = call("GET", f"{base}/health")
        live_sha = (body or {}).get("git_sha")
        if status == 200 and ((args.expect_sha and live_sha == args.expect_sha) or
                              (args.expect_not_sha and live_sha not in (None, args.expect_not_sha))):
            break
        if time.time() - started > args.timeout:
            fail(f"release not live after {args.timeout}s (last status {status}, live git_sha {live_sha})")
        time.sleep(10)
    live_at = datetime.now(timezone.utc)
    print(f"PASS /health 200: {json.dumps(body)}")
    print(f"     live after {time.time() - started:.0f}s of waiting")
    if os.getenv("MERGED_AT"):
        merged = datetime.fromisoformat(os.environ["MERGED_AT"].replace("Z", "+00:00"))
        print(f"TIMING merge to live: {(live_at - merged).total_seconds():.0f}s "
              f"(merged {merged.isoformat()}, live {live_at.isoformat(timespec='seconds')})")

    # 2. the three API-key checks (the key itself is never printed)
    url = f"{base}/predictions"
    checks = [("no key", {}, 401), ("wrong key", {"X-API-Key": "wrong-key"}, 403), ("correct key", {"X-API-Key": key}, 200)]
    for name, headers, expected in checks:
        status, _ = call("POST", url, SAFE, headers)
        if status != expected:
            fail(f"API key check '{name}': expected {expected}, got {status}")
        print(f"PASS API key check '{name}': {status}")

    # 3. business sanity checks
    _, safe = call("POST", url, SAFE, {"X-API-Key": key})
    _, risky = call("POST", url, RISKY, {"X-API-Key": key})
    for label, res in (("safe", safe), ("risky", risky)):
        if not res or not 0 <= res["default_probability"] <= 1:
            fail(f"{label} applicant: probability out of range: {res}")
    print(f"     safe applicant  -> {safe}")
    print(f"     risky applicant -> {risky}")
    if not safe["approved"]:
        fail("a clearly safe applicant was declined")
    if risky["approved"]:
        fail("a clearly risky applicant was approved")
    print("PASS business checks: safe approved, risky declined")
    print(f"RELEASE VERIFIED: {body.get('git_sha')}")


if __name__ == "__main__":
    main()
