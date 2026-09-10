# ZeroOps Demo Application (Python / FastAPI)

This repository serves as the official, controlled demo application for the **ZeroOps AI** university presentation on September 17, 2026.

## Structure

```
.
├── app.py              # Main FastAPI application (GET / and GET /health)
├── test_app.py         # Deterministic pytest unit tests
├── requirements.txt    # Application and test dependencies
├── Dockerfile          # Azure App Service container definition
└── README.md           # Instructions for presenter
```

## Presentation Steps

### 1. Initial Deployment
- Repository is imported into ZeroOps AI.
- ZeroOps detects:
  - Framework: `FastAPI`
  - Language: `Python`
  - Container Support: `Dockerfile` (Port 8000)
  - Target: `Azure App Service`
- Approve plan and trigger pipeline.
- Tests pass (`pytest test_app.py`), application builds and deploys to Azure App Service.
- Public endpoint returns HTTP 200 at `/health`.

### 2. Incremental Change (Application Code Only)
- Edit `app.py`: change `APP_VERSION = "1.0.0"` to `APP_VERSION = "1.1.0"`.
- Commit and push to GitHub:
  ```bash
  git commit -am "Update app version to 1.1.0"
  git push
  ```
- ZeroOps detects commit via webhook, classifies change as `APPLICATION_CODE_CHANGE`.
- ZeroOps reuses existing architecture plan (no expensive re-analysis).
- Pipeline runs unit tests, updates App Service deployment, and exposes version `1.1.0`.

### 3. Intentional Failure Demo (Unit Test Failure)
- In `app.py`, change `/health` response status code from `200` to `500`:
  ```python
  @app.get("/health")
  def health_check():
      return JSONResponse(status_code=500, content={"status": "error"})
  ```
- Commit and push:
  ```bash
  git commit -am "Simulate degraded health endpoint"
  git push
  ```
- ZeroOps pipeline runs `unit_tests` stage, which executes `pytest test_app.py`.
- Test fails (`assert 500 == 200`).
- Pipeline stops immediately before deployment.
- Pipeline UI marks `unit_tests` stage as `FAILED`, displays test traceback, and AI Root Cause Analysis suggests fix.

### 4. Recovery Demo
- Revert `/health` back to status code `200`.
- Commit and push:
  ```bash
  git commit -am "Fix health endpoint status code"
  git push
  ```
- Pipeline runs cleanly, succeeds, and verifies live application.
