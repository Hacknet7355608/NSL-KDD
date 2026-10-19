# NSL-KDD ｜ Network Intrusion Detection System

[中文](README.md) ｜ **English**

Given the features of a single network connection (protocol type, byte counts, error rates, …),
the service classifies it into one of five categories: `normal` / `DoS` / `Probe` / `R2L` / `U2R`.

The project wires a full DevOps + MLOps toolchain into one end-to-end pipeline:

**Git branching → DVC data versioning → MLflow experiment tracking → FastAPI service → automated tests → Docker image → GitHub Actions pipeline → per-environment builds**

> Course: DevOps & MLOps
> Team: `21`
> Members: A (data & training), B (service & tests), C (containers, configuration & pipeline)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Repository Layout](#2-repository-layout)
3. [Local Development](#3-local-development)
4. [Configuration Management (12-Factor)](#4-configuration-management-12-factor)
5. [API Endpoints](#5-api-endpoints)
6. [From Commit to Production (graded requirements)](#6-from-commit-to-production-graded-requirements)
7. [CI Pipeline in Detail](#7-ci-pipeline-in-detail)
8. [Tests](#8-tests)
9. [Automated Code Quality](#9-automated-code-quality)
10. [Team Responsibilities](#10-team-responsibilities)
11. [Troubleshooting](#11-troubleshooting)
12. [Further Documentation](#12-further-documentation)

---

## 1. Project Overview

| Item | Value |
|---|---|
| Task | NSL-KDD network traffic **5-class classification** |
| Model | scikit-learn RandomForest (trained from scratch; two experiments: baseline + improved) |
| Data versions | DVC v1 (raw) / v2 (5-class labels merged, categorical features encoded, constant columns dropped); remote storage on Azure Blob |
| Experiment tracking | MLflow 2 with local `file:./mlruns` backend |
| Service | FastAPI + Uvicorn, 6 endpoints |
| Python | **3.12** (identical across local, CI and the image) |
| Tests | pytest, 6 test files, **36 test cases** |
| Image | `python:3.12-slim` (pulled through an Azure container registry mirror), non-root user, `HEALTHCHECK` |
| Pipeline | GitHub Actions, 4 jobs |
| Configuration | 12-Factor: everything comes from environment variables; secrets never enter code or images |

---

## 2. Repository Layout

```
NSL-KDD/
├── app/                            # Service code
│   ├── __init__.py
│   ├── main.py                     # FastAPI entrypoint: / /health /config /model-info /sample /predict
│   ├── model.py                    # Model loading + feature-order validation (degrades to 503)
│   ├── schemas.py                  # Pydantic request/response models
│   └── settings.py                 # Config layer: env vars -> typed Settings (12-Factor)
│
├── ml/                             # Data & training
│   ├── data_pipeline.py            # v1 raw txt -> v2 cleaned & encoded
│   ├── train.py                    # Training + MLflow logging + export to models/
│   ├── configs/
│   │   ├── baseline.json           # Experiment 1: smaller model
│   │   └── improved.json           # Experiment 2: larger, deeper model
│   ├── registry/
│   │   └── current_model.md        # Production model registry (run_id / data version / metrics / rollback target)
│   ├── README_data.md              # Data source, v1 -> v2 changes, version-to-commit mapping
│   ├── README_experiments.md       # Comparison of the two experiments, rationale for the production model
│   └── PROVENANCE.md               # Model lineage: run_id <-> commit <-> data version
│
├── models/                         # Training artifacts (committed, used by the image and CI)
│   ├── model.joblib
│   └── model_meta.json             # feature_names / classes / run_id / data version / metrics / encoders
│
├── tests/                          # Tests (36 cases)
│   ├── conftest.py                 # Fixture: trains a tiny model on the fly (no real dataset needed)
│   ├── test_service.py             # Startup, health check, model metadata
│   ├── test_prediction.py          # Prediction contract
│   ├── test_validation.py          # Input validation and edge cases
│   ├── test_model_missing.py       # Graceful degradation when the model is missing
│   └── test_settings.py            # Config layer: env vars, secret masking, fail-fast
│
├── data/                           # Data (only .dvc pointers in Git, never the data itself)
│   ├── raw.dvc                     # v1
│   └── processed.dvc               # v2
│
├── .github/workflows/ci.yml        # GitHub Actions pipeline
├── .pre-commit-config.yaml         # Local pre-commit hooks
├── .env.example                    # Local config template (no real secrets, safe to commit)
├── Dockerfile
├── .dockerignore
├── requirements.txt                # Runtime dependencies (baked into the image)
├── requirements-dev.txt            # Test / lint dependencies
├── requirements-ml.txt             # Training dependencies (never in the image)
├── pyproject.toml                  # ruff / pytest / coverage configuration
├── DEPLOYMENT.md                   # Environments, secrets, builds, rollback, enablement order
└── README.md                       # Chinese version
```

---

## 3. Local Development

### 3.1 Dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\activate                 # macOS/Linux: source .venv/bin/activate

pip install -r requirements-dev.txt      # service + tests + linting
pip install -r requirements-ml.txt       # only needed for training
```

> Why three requirement files: `requirements-ml.txt` pulls in pandas / mlflow / dvc[azure] /
> matplotlib — several hundred MB — while the runtime image only needs the six packages in
> `requirements.txt`. Bundling them would grow the image from ~700 MB to well over 1.2 GB,
> which would make the "slim" claim meaningless.

### 3.2 Local configuration

```powershell
Copy-Item .env.example .env      # copy the template, then fill in values
```

`.env` is excluded by both `.gitignore` and `.dockerignore` — **it never enters Git and never
enters the image**.

### 3.3 Fetch data (DVC pointers + Azure remote)

```powershell
dvc pull
```

### 3.4 Preprocessing and training

```powershell
python ml/data_pipeline.py                    # v1 -> v2
python ml/train.py --all                      # run both experiments, write artifacts to models/
mlflow ui --backend-store-uri ./mlruns        # open http://127.0.0.1:5000
```

### 3.5 Run the service

```powershell
uvicorn app.main:app --reload --port 8000     # interactive docs: http://127.0.0.1:8000/docs
```

### 3.6 Tests and static checks

```powershell
pytest -q --cov=app --cov-report=term-missing
ruff check .
ruff format --check .
```

### 3.7 Enable pre-commit hooks (once per developer)

```powershell
pre-commit install
pre-commit run --all-files
```

### 3.8 Build and run the image

```powershell
docker build --build-arg APP_ENV=dev -t nsl-kdd:dev .
docker run -d --name nids -p 8000:8000 nsl-kdd:dev
curl http://127.0.0.1:8000/health
docker exec nids ls /app/models          # model.joblib / model_meta.json
docker exec nids ls /app/data            # should fail: data is not baked into the image
```

---

## 4. Configuration Management (12-Factor)

Implements **12-Factor App — Factor III: Config**. Configuration is separated from code, so the
same build artifact can run in multiple environments.

### 4.1 Configuration variables

| Variable | Default | Sensitive | Description |
|---|---|---|---|
| `APP_ENV` | `dev` | No | Environment label (`dev` / `staging` / `production`); **never used in business branches** |
| `LOG_LEVEL` | `INFO` | No | Log level |
| `MODEL_PATH` | `models/model.joblib` | No | Model file path |
| `MODEL_META_PATH` | `models/model_meta.json` | No | Model metadata path |
| `APP_API_KEY` | empty | **Yes** | API key; mandatory in production |

### 4.2 Where configuration comes from

| Scenario | Source | Injection mechanism |
|---|---|---|
| Local development | `.env` in the repo root (template: `.env.example`) | uvicorn reads the process environment / `python-dotenv` |
| CI pull-request checks | No business config required | `docker build --build-arg APP_ENV=ci` + keyless smoke test |
| Merge to `staging` | GitHub Secrets `STAGING_*` | write `.env`, then `docker run --env-file .env` |
| Merge to `main` | GitHub Secrets `PROD_*` | same as above |

### 4.3 Three hard rules

1. **`.env` never enters Git or the image** — the repository only contains `.env.example` with no real values.
2. **No configuration values inside the image** — secrets are not part of the build, so neither
   `docker history` nor `docker save` can expose them.
3. **Secrets never appear in logs** — CI masks `.env` values with `sed 's/=.*/=***/'`, and the
   application's `GET /config` only reports `api_key_configured: true/false`, never the value.

### 4.4 Implementation

| Location | Purpose |
|---|---|
| `app/settings.py` → `Settings(BaseModel)` | `Field(alias="APP_ENV")` binds each field to an environment variable, with type validation and defaults |
| `get_settings()` | Builds the settings object from `os.environ` (`extra="ignore"` skips unrelated variables) |
| `validate_for_env()` | **Fail fast**: exits immediately when `APP_ENV=production` and `APP_API_KEY` is missing |
| `safe_view()` | Produces the redacted summary served by `GET /config` |

> Running the same image under `staging` and `production` yields a different `app_env` from
> `GET /config` while the image stays byte-identical — direct evidence of the Build / Release /
> Run separation.

---

## 5. API Endpoints

| Method | Path | Description | Notes |
|---|---|---|---|
| GET | `/` | Service information | Version and docs link |
| GET | `/health` | Health check | Always 200; `{"status":"ok","model_loaded":bool}` |
| GET | `/config` | Effective configuration (redacted) | `app_env` / `log_level` / `model_path` / `api_key_configured` |
| GET | `/model-info` | Model metadata | Feature count, classes, run_id, data version, encoders |
| GET | `/sample` | A valid all-zero payload | Lets you try `/predict` from `/docs` in one click |
| POST | `/predict` | 5-class prediction | Returns label, confidence and the 5-class probability vector |

**Graceful degradation**: when the model is missing, `/health` still returns 200
(`model_loaded=false`) while `/predict` returns 503 with an explanation — the container never
fails to start because of a missing model.

---

## 6. From Commit to Production (graded requirements)

### 6.1 How code flows

```
(1) Local dev                       (2) Remote                          (3) Automation (GitHub Actions)
--------------                      -----------                         ------------------------------
git commit ────────────────────►   feature/xxx
(pre-commit runs ruff first)
                                         │
                                         │ PR
                                         ▼
                                      dev        ──►  lint-and-test  (ruff check + format + pytest)
                                         │                      │
                                         │                      ▼
                                         │              docker-build  (build + /health smoke test)
                                         │                      │
                                         │      ✓ both checks green required to merge (branch protection)
                                         │
                                         │ PR
                                         ▼
                                    staging      ──►  lint-and-test
                                         │                      │
                                         │                      ▼
                                         │              build-staging
                                         │              (STAGING_* → .env → build nsl-kdd:staging)
                                         │
                                         │ PR
                                         ▼
                                      main       ──►  lint-and-test
                                                                  │
                                                                  ▼
                                                           build-prod
                                                           (PROD_* → .env → build nsl-kdd:prod)
```

**In one sentence**:
`commit → (pre-commit + ruff) → push → PR into dev → full test suite + static checks + image build → merge to dev → PR into staging → build the staging image → PR into main → build the production image`.

### 6.2 Which branch triggers which pipeline

| Branch / event | Jobs that run |
|---|---|
| push to `feature/*` | **None** (only checked when a PR is opened) |
| PR into `dev` / `staging` / `main` | `lint-and-test` → `docker-build` |
| push to `dev` (i.e. a merge) | `lint-and-test` → `docker-build` |
| push to `staging` (i.e. a merge) | `lint-and-test` → `docker-build` → **`build-staging`** |
| push to `main` (i.e. a merge) | `lint-and-test` → `docker-build` → **`build-prod`** |
| Manual `Run workflow` | `lint-and-test` → `docker-build` (the two environment jobs are skipped by their `if` conditions) |

> `build-staging` / `build-prod` **only run on merge (push) events** — by design. The course
> requires "**Merges to** staging/main → create the .env file → build the corresponding image".
> Seeing them marked as skipped on a pull request is expected behaviour.

### 6.3 Environment mapping

| GitHub Environment | Branch | `APP_ENV` | Image tag | Notes |
|---|---|---|---|---|
| (none) | `dev` | `ci` | `nsl-kdd:ci` | Build + smoke validation only |
| `staging` | `staging` | `staging` | `nsl-kdd:staging` | Uses environment-level `STAGING_*` secrets |
| `prod` | `main` | `production` | `nsl-kdd:prod` | Uses environment-level `PROD_*` secrets, **requires manual approval** |

### 6.4 Protection rules

`dev`, `staging` and `main` are all protected:

- Merging requires a pull request — **direct pushes are rejected**
- The `lint-and-test` and `docker-build` status checks must pass
- Rules cannot be bypassed (`Do not allow bypassing the above settings`)

In other words: **a pull request cannot be merged while CI is failing** — the Merge button turns
grey and shows `Required status checks have not passed`.

See sections 7 and 8 of `DEPLOYMENT.md` for the enablement order and the evidence checklist.

---

## 7. CI Pipeline in Detail

Configuration file: `.github/workflows/ci.yml`

| Job | Trigger | What it does | If it fails |
|---|---|---|---|
| `lint-and-test` | All PRs / pushes to the three branches | `pip install -r requirements-dev.txt` → `ruff check .` → `ruff format --check .` → `pytest -q --cov=app` | Downstream jobs are skipped; the PR cannot be merged |
| `docker-build` | Same, `needs: lint-and-test` | `docker build` + start the container and smoke-test `/health` | The PR cannot be merged |
| `build-staging` | `push` to `staging` | Write `.env` → build `nsl-kdd:staging` → start with `--env-file` and verify `/health` | The branch pipeline turns red |
| `build-prod` | `push` to `main` | Write `.env` → build `nsl-kdd:prod` → start with `--env-file` and verify `/health` | The branch pipeline turns red; with approval configured it first waits in `Waiting` |

Two details worth highlighting:

- **The smoke test is real**: it derives success from an explicit `exit 1` instead of letting the
  `for` loop end normally — otherwise 20 consecutive failures would still be reported as success,
  turning the check into a fake safety net.
- **`.env` has a real consumer**: it is runtime configuration, not a build input, injected through
  `docker run --env-file`. Build and configuration are separated, so a single image can run in all
  three environments.

---

## 8. Tests

| File | Functionality covered | Edge cases |
|---|---|---|
| `tests/test_service.py` | Startup, health check, model metadata | Unknown route 404, metadata completeness |
| `tests/test_prediction.py` | Prediction contract | All-zero input, negative values, 1e6, decimals, idempotency, submitting `/sample` directly |
| `tests/test_validation.py` | Input validation | Missing fields, extra fields, string/null/list types, empty object, missing body, wrong method, non-JSON |
| `tests/test_model_missing.py` | Missing-model degradation | 503 without a model, corrupted metadata, `/health` still 200 |
| `tests/test_settings.py` | Configuration layer | Env-var reading, default fallbacks, no secret leakage, fail-fast in production, `/health` contract preserved |

**36 test cases** in total. The fixture in `conftest.py` trains a tiny model on the fly, so the
suite **does not depend on the real dataset** and runs in CI without `dvc pull`.

```powershell
pytest -q --cov=app --cov-report=term-missing
```

---

## 9. Automated Code Quality

Two gates, identical rules:

| Gate | Location | What runs |
|---|---|---|
| Pre-commit (local) | `.pre-commit-config.yaml` | `ruff --fix`, `ruff-format`, end-of-file newline, trailing whitespace, YAML syntax, large files, merge-conflict markers |
| Pull request (CI) | `ci.yml` → `lint-and-test` | `ruff check .`, `ruff format --check .`, `pytest` |

```powershell
pre-commit install          # activate the hooks
pre-commit run --all-files  # full manual run
```

Rules live in `pyproject.toml`:

- `line-length = 100`
- `select = ["E", "F", "I"]` (E/F are equivalent to flake8, I to isort)
- `ignore = ["E501"]`
- `pythonpath = ["."]` — fixes `ModuleNotFoundError: app` in CI

`pytest` and `ruff` are **pinned to exact versions** in `requirements-dev.txt` so that
"green locally" implies "green in CI".

---

## 10. Team Responsibilities

| Member | Owns | Main deliverables |
|---|---|---|
| **A** | Data & training | `ml/data_pipeline.py`, `ml/train.py`, `ml/configs/`, `data/*.dvc`, `models/*`, `ml/README_data.md`, `ml/README_experiments.md`, `ml/PROVENANCE.md`, `ml/registry/current_model.md` |
| **B** | Service & tests | `app/main.py`, `app/model.py`, `app/schemas.py`, `tests/*` (except `test_settings.py`) |
| **C** | Containers, configuration & pipeline | `Dockerfile`, `.dockerignore`, `.github/workflows/ci.yml`, `app/settings.py`, `.env.example`, `.pre-commit-config.yaml`, `requirements*.txt`, `pyproject.toml`, `README.md`, `DEPLOYMENT.md`, branch protection and environments |

---

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ruff format --check` fails | Code is not formatted | Run `ruff format .` and push again (the local pre-commit hook catches this earlier) |
| CI reports `ModuleNotFoundError: app` | Missing `pythonpath` | Ensure `pyproject.toml` contains `pythonpath = ["."]` |
| `docker build` fails with `COPY failed: models not found` | `models/` is not in Git | Make sure `models/model.joblib` is committed |
| Container is healthy but `/predict` returns 503 | The image contains no model | Check `COPY models` in the `Dockerfile` and that `.dockerignore` does not exclude it |
| `build-staging` / `build-prod` show as skipped | The current event is a pull request | Expected; they run when the PR is merged (push) into the matching branch |
| `build-prod` is stuck in `Waiting` | The `prod` environment has required reviewers | Open the run in Actions and click `Approve deployment` |
| The base image cannot be pulled | Docker Hub is unreachable from the network | This project pulls through an Azure registry mirror; if that is unreachable too, switch back to `python:3.12-slim` and configure a registry mirror for Docker |
| `/config` reports `api_key_configured: false` | `APP_API_KEY` was not injected in that environment | Check that the secrets and the environment-level keys are configured |

---

## 12. Further Documentation

| Document | Contents |
|---|---|
| `ml/README_data.md` | Data source, v1 → v2 changes, mapping between data versions and commits |
| `ml/README_experiments.md` | Comparison of the two MLflow experiments, why the production model was chosen, the metric being optimised |
| `ml/PROVENANCE.md` | Model lineage: `run_id` ↔ `code commit` ↔ `data version` ↔ model file |
| `ml/registry/current_model.md` | Registry entry of the current production model and its rollback target |
| `DEPLOYMENT.md` | Environment-to-branch mapping, the four jobs, secrets, build and rollback, order in which CI and branch protection were enabled |
