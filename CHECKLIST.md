# Loan API image: requirements checklist

Image: `YOUR_DOCKERHUB_USER/loan-api:1.0.0` (also tagged `latest`)
Built from `Dockerfile.prod` with `docker compose build` / `docker build -f Dockerfile.prod`.

> For each requirement: the command I ran, then its output (paste it under **Output**).

---

## 1. Small, pinned base image (`python:3.12-slim`) and a small final image

**How it is met:** both stages use `python:3.12-slim`; dependencies are pinned in `requirements.txt`;
the runtime model is plain JSON, so scikit-learn and NumPy are not in the image.

```bash
docker image ls YOUR_DOCKERHUB_USER/loan-api
```
**Output:**
```
PASTE HERE
```

## 2. Multi-stage build: build tools stay out of the final image

**How it is met:** stage `builder` installs the dependencies into `/opt/venv`; stage `runtime` copies
only `/opt/venv`, `main.py` and `model/`.

```bash
docker history YOUR_DOCKERHUB_USER/loan-api:1.0.0
```
**Output:**
```
PASTE HERE
```

## 3. Runs as a non-root user

**How it is met:** `USER app` in `Dockerfile.prod`.

```bash
docker run --rm YOUR_DOCKERHUB_USER/loan-api:1.0.0 whoami
docker inspect --format '{{.Config.User}}' YOUR_DOCKERHUB_USER/loan-api:1.0.0
```
**Output:**
```
PASTE HERE   (expected: app / app)
```

## 4. Health check

**How it is met:** `HEALTHCHECK` calls `GET /health` every 30 s.

```bash
docker compose up -d --build
docker compose ps
curl -s http://localhost:8000/health
```
**Output:**
```
PASTE HERE   (expected: api ... (healthy) and {"status":"ok","model_version":"1.0.0"})
```

## 5. Configuration through environment variables (`MODEL_PATH`), no hard-coded paths

**How it is met:** `main.py` reads `MODEL_PATH` (and the optional `DATABASE_URL`) from the environment.

```bash
docker run --rm -e MODEL_PATH=/app/model/missing.json YOUR_DOCKERHUB_USER/loan-api:1.0.0
```
**Output (fails on purpose, proving the variable is used):**
```
PASTE HERE   (expected: FileNotFoundError ... /app/model/missing.json)
```

## 6. Small build context and no secrets in the image or the repository

**How it is met:** `.dockerignore` excludes `.git`, `.env*`, keys and caches; no password, token or key is
written in `Dockerfile.prod` or the code. The only password in the repository is the development-only
Postgres password in `compose.yaml` (allowed exception), and it is not in the image.

```bash
docker history --no-trunc YOUR_DOCKERHUB_USER/loan-api:1.0.0 | grep -iE "password|secret|token|key" || echo "no secrets in layers"
docker inspect --format '{{json .Config.Env}}' YOUR_DOCKERHUB_USER/loan-api:1.0.0
docker run --rm YOUR_DOCKERHUB_USER/loan-api:1.0.0 ls -la /app
git grep -niE "password|secret|token|api_key" -- . ':!CHECKLIST.md'
```
**Output:**
```
PASTE HERE   (expected: only PATH/MODEL_PATH/PYTHON* in Env; /app has main.py and model/; git grep finds only compose.yaml)
```

## 7. Vulnerability scan with Trivy: no unhandled HIGH or CRITICAL findings

**How it is met:** slim base, `apt-get upgrade` in the runtime stage, latest pinned Python packages,
no scikit-learn/NumPy at runtime.

```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest \
  image --severity HIGH,CRITICAL --ignore-unfixed YOUR_DOCKERHUB_USER/loan-api:1.0.0
```
**Output:**
```
PASTE HERE
```

**Notes on findings** (one per HIGH/CRITICAL, if any):
- _CVE-ID / package_: rebuilt and fixed, **or** no fixed version published yet (Trivy "Fixed Version" is empty); will rebuild when Debian/PyPI publishes the fix.

---

## Published and pulled from the registry

```bash
docker image rm YOUR_DOCKERHUB_USER/loan-api:1.0.0 YOUR_DOCKERHUB_USER/loan-api:latest
docker run --rm -p 8000:8000 YOUR_DOCKERHUB_USER/loan-api:1.0.0
```
Docker Hub: https://hub.docker.com/r/YOUR_DOCKERHUB_USER/loan-api (tags `1.0.0` and `latest`)
