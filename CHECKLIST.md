# Loan API image: requirements checklist

- **Image:** `manitainn/loan-api:1.0.0` (also tagged `latest`, same digest
  `sha256:7f7190af893bec2219262af9b2ec3736d377f410f849621fe163a2df27168cba`)
- **Docker Hub:** https://hub.docker.com/r/manitainn/loan-api
- **Built from:** `Dockerfile.prod` through `compose.yaml` (`context: .`, `dockerfile: Dockerfile.prod`)
- All commands were run in GitHub Codespaces.

---

## 1. Small, pinned base image and a small final image

**How it is met:** both stages use `python:3.12-slim`; every Python dependency is pinned in
`requirements.txt`; the model is plain JSON, so scikit-learn and NumPy are not in the image;
pip is removed after installing.

```bash
docker image ls manitainn/loan-api
```
```
IMAGE                       ID             DISK USAGE   CONTENT SIZE
manitainn/loan-api:1.0.0    7f7190af893b        249MB         59.7MB
manitainn/loan-api:latest   7f7190af893b        249MB         59.7MB
```
Result: **59.7 MB** compressed content.

## 2. Multi-stage build: build tools stay out of the final image

**How it is met:** stage `builder` creates `/opt/venv` and installs the dependencies; stage
`runtime` starts again from `python:3.12-slim` and copies only `/opt/venv`, `main.py` and `model/`.

```bash
docker history manitainn/loan-api:1.0.0
```
```
CREATED BY                                      SIZE
CMD ["uvicorn" "main:app" "--host" "0.0.0.0"…   0B
HEALTHCHECK {Test:[CMD-SHELL python -c "impo…   0B
EXPOSE [8000/tcp]                               0B
USER app                                        0B
COPY --chown=app:app model/ model/ # buildkit   16.4kB
COPY --chown=app:app main.py . # buildkit       12.3kB
COPY /opt/venv /opt/venv # buildkit             55.4MB
WORKDIR /app                                    8.19kB
RUN /bin/sh -c groupadd --system app && user…   41kB
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFER…   0B
RUN /bin/sh -c apt-get update && apt-get upg…   9.59MB
CMD ["python3"]                                 0B      <- python:3.12-slim base layers below
...
```
(Output from the first build; after removing pip in requirement 7 the same layers remain, with
a slightly smaller venv layer.) Only the finished virtual environment is copied from the builder (`COPY /opt/venv /opt/venv`);
no compiler, pip cache or requirements file is in the runtime layers.

## 3. Runs as a non-root user

**How it is met:** `groupadd/useradd --system app` and `USER app` in `Dockerfile.prod`.

```bash
docker run --rm manitainn/loan-api:1.0.0 whoami
docker inspect --format 'User={{.Config.User}}' manitainn/loan-api:1.0.0
```
```
app
User=app
```

## 4. Health check

**How it is met:** `HEALTHCHECK` in `Dockerfile.prod` calls `GET /health` every 30 s; the
`db` service in `compose.yaml` has its own `pg_isready` check and `api` waits for it
(`depends_on: condition: service_healthy`).

```bash
docker compose up -d && sleep 20 && docker compose ps && curl -s localhost:8000/health
```
```
NAME              IMAGE                  STATUS                    PORTS
loan-api--api-1   local/loan-api:1.0.0   Up 20 seconds (healthy)   0.0.0.0:8000->8000/tcp
loan-api--db-1    postgres:16-alpine     Up 25 seconds (healthy)   5432/tcp
{"status":"ok","model_version":"1.0.0"}
```

## 5. Configuration through environment variables (`MODEL_PATH`)

**How it is met:** `main.py` reads `MODEL_PATH` (default `/app/model/model.json`, set with
`ENV` in `Dockerfile.prod`) and the optional `DATABASE_URL`; nothing is hard-coded.

```bash
docker run --rm -e MODEL_PATH=/app/model/missing.json manitainn/loan-api:1.0.0
```
```
FileNotFoundError: [Errno 2] No such file or directory: '/app/model/missing.json'
ERROR:    Application startup failed. Exiting.
```
Changing the variable changes the file the API loads, which proves the path is configurable.

## 6. No secrets in the image or the repository

**How it is met:** `.dockerignore` excludes `.git`, `.env*`, keys and caches; `Dockerfile.prod`
copies only `main.py` and `model/`; no password, token or key is written in the code or the
Dockerfiles. The only password in the repository is the **development-only** Postgres password in
`compose.yaml` (the allowed exception), and it is not baked into the image.

```bash
docker history --no-trunc manitainn/loan-api:1.0.0 | grep -iE "password|secret|token" || echo "no secrets in image layers"
docker inspect --format '{{json .Config.Env}}' manitainn/loan-api:1.0.0
docker run --rm manitainn/loan-api:1.0.0 ls -la /app
git grep -niE "password|secret|token|api_key" -- . ':!CHECKLIST.md'
```
```
no secrets in image layers
["PATH=/opt/venv/bin:/usr/local/bin:...","LANG=C.UTF-8","GPG_KEY=7169605F62C7...(official Python release signing key, public)",
 "PYTHON_VERSION=3.12.16","PYTHON_SHA256=b5796915...","PYTHONDONTWRITEBYTECODE=1","PYTHONUNBUFFERED=1",
 "MODEL_PATH=/app/model/model.json"]
-rw-rw-rw- 1 app  app  3706 main.py
drwxr-xr-x 2 app  app  4096 model
.dockerignore:1:# Keep the build context small and secret-free.
Dockerfile.prod:1:# Production image: multi-stage, slim, pinned, non-root, health-checked, no secrets.
compose.yaml:11:      DATABASE_URL: postgresql://loan:loan_dev_password@db:5432/loans
compose.yaml:21:      POSTGRES_PASSWORD: loan_dev_password   # development-only password (allowed exception)
```
`GPG_KEY` and `PYTHON_SHA256` come from the official `python:3.12-slim` image: they are the public
key and checksum used to verify the Python download, not secrets. Trivy's secret scanner also
reported no secrets.

## 7. Vulnerability scan with Trivy

**How it is met:** slim base, `apt-get upgrade` in the runtime stage, latest pinned Python
packages, no scikit-learn/NumPy at runtime, and pip removed from the final image.

```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest \
  image --quiet --severity HIGH,CRITICAL manitainn/loan-api:1.0.0
```

**First scan (before the fix):**
```
manitainn/loan-api:1.0.0 (debian 13.7)   Total: 45 (HIGH: 45, CRITICAL: 0)
Python (python-pkg)                      Total: 1  (HIGH: 1,  CRITICAL: 0)
  setuptools  CVE-2025-47273  HIGH  fixed  70.3.0 -> 78.1.1  Path Traversal in PackageIndex
```

**Final scan (after rebuilding):**
```
manitainn/loan-api:1.0.0 (debian 13.7)   Total: 45 (HIGH: 45, CRITICAL: 0)
```
No Python findings remain, and there are **0 CRITICAL** findings.

### Notes on each HIGH finding

| Finding | Packages | Decision |
|---|---|---|
| **CVE-2025-47273** (setuptools 70.3.0, path traversal) | setuptools code bundled inside **pip** (both the base image's system pip and the venv's pip) | **Rebuilt and fixed.** The API never uses pip at runtime, so `Dockerfile.prod` now runs `pip uninstall -y pip` in the builder venv and in the runtime stage. Python findings went from 1 to 0, and the image shrank from 61.9 MB to 59.7 MB. |
| CVE-2026-76642, CVE-2026-78408, CVE-2026-78409, CVE-2026-78410 (util-linux mount/nsenter issues) | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | **Cannot be fixed yet:** Debian status "affected", no fixed version published. `apt-get upgrade` already installs the newest available version. The container never runs `mount` or `nsenter`, and it runs as the unprivileged `app` user. Will rebuild when Debian publishes the fix. |
| CVE-2025-69720 (ncurses buffer overflow) | libncursesw6, libtinfo6, ncurses-base, ncurses-bin | **Cannot be fixed yet:** no fixed version in Debian 13. The API never uses a terminal UI. Will rebuild when fixed. |
| CVE-2026-16742 (systemd-homed privilege escalation) | libsystemd0, libudev1 | **Cannot be fixed yet:** no fixed version. systemd-homed is not installed or running in the container; only the libraries are present. |
| CVE-2026-54369 (acl symlink traversal) | libacl1 | **Cannot be fixed yet:** no fixed version. The API does not manage file ACLs. |
| CVE-2026-119373 (sqlite FTS5 heap overflow) | libsqlite3-0 | **Cannot be fixed yet:** no fixed version. The API uses Postgres, not SQLite. |
| CVE-2026-9538 (perl Archive::Tar DoS) | perl-base | **Cannot be fixed yet:** Debian status "fix_deferred". Perl is part of the base OS and is not used by the API. |

All 45 Debian findings come from the official `python:3.12-slim` base image and have **no fixed
version available**. I will rebuild and re-scan when Debian publishes fixes.

---

## Published and pulled from the registry

```bash
docker push manitainn/loan-api:1.0.0 && docker push manitainn/loan-api:latest
```
```
1.0.0: digest: sha256:7f7190af893bec2219262af9b2ec3736d377f410f849621fe163a2df27168cba size: 856
latest: digest: sha256:7f7190af893bec2219262af9b2ec3736d377f410f849621fe163a2df27168cba size: 856
```

After deleting every local copy of the image:
```bash
docker compose down && docker image rm manitainn/loan-api:1.0.0 manitainn/loan-api:latest local/loan-api:1.0.0
docker run --rm -p 8000:8000 manitainn/loan-api:1.0.0
```
```
Unable to find image 'manitainn/loan-api:1.0.0' locally
1.0.0: Pulling from manitainn/loan-api
...
Status: Downloaded newer image for manitainn/loan-api:1.0.0
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     127.0.0.1:57698 - "GET /health HTTP/1.1" 200 OK
```
The published image runs on its own, with no local files and no database.
`POST /predictions` in `/docs` returned **200** (see the submitted screenshot).