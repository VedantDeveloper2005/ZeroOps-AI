# ZeroOps AI - Live Presentation Runbook (September 17, 2026)

## Purpose & Scope
This runbook provides the step-by-step procedure for demonstrating **ZeroOps AI** live during the university project presentation on **September 17, 2026**.

The demonstration proves a truthful, end-to-end DevOps/DevSecOps lifecycle for a web application deployed to **Azure App Service**, including AI architectural planning, automated pipeline stage execution, incremental change detection, failure prevention, and AI root cause diagnosis.

---

## Pre-Demo Checklist

Execute these verification checks at least 30 minutes prior to the live demonstration:

1. **Confirm Backend Healthy**:
   - Start backend: `uvicorn backend.main:app --host 127.0.0.1 --port 8000`
   - Verify `http://127.0.0.1:8000/health` returns `200 OK`.
2. **Confirm Frontend Healthy**:
   - Start frontend: `npm run dev`
   - Verify `http://localhost:3000` renders without console errors.
3. **Confirm PostgreSQL Reachable**:
   - Verify local PostgreSQL container or managed Azure PostgreSQL database is online.
   - Run: `python scripts/demo_readiness.py` to confirm database connectivity.
4. **Confirm Worker & Demo Executor**:
   - Ensure environment variables are set:
     - `APP_ENV=development`
     - `ZEROOPS_DEMO_EXECUTOR=true`
5. **Confirm Azure Authentication**:
   - Ensure Azure CLI session or Service Principal credentials are valid:
     - `az account show` (must show active target subscription).
6. **Confirm Azure App Service Plan**:
   - Confirm target Resource Group and App Service plan exist in your Azure subscription.
7. **Confirm Security Tools / Fallbacks**:
   - `scripts/demo_readiness.py` should show installed scanners or indicate `unavailable` status cleanly without crashing.
8. **Confirm GitHub Webhook Configuration**:
   - Ensure `GITHUB_WEBHOOK_SECRET` matches the webhook secret configured in the GitHub demo repository settings.
   - If demoing locally, start ngrok or a webhook proxy: `ngrok http 8000` and point GitHub webhook to `https://<ngrok-id>/api/webhooks/github`.
9. **Confirm Demo Repository Branch**:
   - Ensure `examples/demo-python-app/` has been pushed to a fresh GitHub repository on `main` branch.
10. **Rehearsal Run**:
    - Perform one complete rehearsal deployment using the steps below.

---

## Pre-Demo Environment Launch

### Terminal 1: Backend API
```powershell
$env:APP_ENV = "development"
$env:ZEROOPS_DEMO_EXECUTOR = "true"
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### Terminal 2: Frontend UI
```powershell
npm run dev
```

### Terminal 3: Webhook Tunnel (for live GitHub push)
```powershell
ngrok http 8000
```
*Configure the GitHub repository webhook URL: `https://<your-ngrok-subdomain>.ngrok-free.app/api/webhooks/github` (Content-type: application/json, Secret: your GITHUB_WEBHOOK_SECRET).*

---

## Live Demonstration Script

### Act 1: Initial Repository Analysis & Deployment

1. **User Authentication & Dashboard**:
   - Open browser at `http://localhost:3000`.
   - Log into ZeroOps with presenter credentials.
   - Show clean dashboard showing projects and cloud health status.

2. **Connect GitHub & Select Repository**:
   - Navigate to **Deploy / New Project**.
   - Select the GitHub organization and demo repository (`demo-python-app`).
   - Click **Analyze Repository**.

3. **Repository Analysis & Stack Detection**:
   - Highlight the real deterministic analysis:
     - Framework: **FastAPI**
     - Language: **Python 3.11**
     - Container: **Dockerfile** (Port 8000)
     - Target Recommendation: **Azure App Service (Linux Container)**
   - Explain that ZeroOps inspects source manifests directly and bounds AI suggestions to evidence.

4. **Architecture Plan & Cost Explanation**:
   - Review generated infrastructure architecture blueprint.
   - Show estimated compute tier (B1 / Basic for demo application).
   - Point out that security checks and health probe endpoints (`/health`) are detected automatically.

5. **Approval & Pipeline Start**:
   - Click **Approve Plan & Deploy**.
   - The UI transitions to the live **Pipeline** view.

6. **Visible Pipeline Execution**:
   - Show the real-time stage progression:
     - `source`: Clones and isolates repository commit.
     - `change_detection`: Initial commit (full analysis baseline).
     - `unit_tests`: Executes `pytest test_app.py` in isolated workspace.
     - `code_quality` / `security_scanner`: SAST & secret checks (Gitleaks, Semgrep or graceful `unavailable` if tool missing).
     - `build`: Builds container or package bundle.
     - `app_service_deploy`: Deploys to target Azure App Service.
     - `health_check`: Probes `https://<app-name>.azurewebsites.net/health` until 200 OK.
     - `smoke_test`: Verifies root metadata.
   - Show live streaming execution logs in the terminal drawer.

7. **Verify Live Application**:
   - Click the live URL shown in the deployment card.
   - Browser displays:
     ```json
     {
       "app": "ZeroOps Demo",
       "version": "1.0.0",
       "status": "running",
       "message": "Deployed automatically via ZeroOps AI pipeline"
     }
     ```

---

### Act 2: Change-Aware Incremental Push

1. **Make Code Change**:
   - In your local clone of the demo repository, open `app.py`.
   - Update version string:
     ```python
     APP_VERSION = os.getenv("APP_VERSION", "1.1.0")
     ```
2. **Commit and Push**:
   ```bash
   git commit -am "Update app version to 1.1.0"
   git push origin main
   ```
3. **Webhook Reception & Diff Classification**:
   - Show ZeroOps UI automatically catching the webhook event without a manual refresh.
   - Point to the **Change Detection** summary in the deployment:
     - Classification: `APPLICATION_CODE_CHANGE`
     - Changed file: `app.py`
     - Intelligence action: **Architecture analysis reused** (skips redundant heavy re-analysis).
4. **Targeted Pipeline Execution**:
   - Pipeline reruns unit tests and redeploys to Azure App Service.
5. **Verify Updated Application**:
   - Refresh the live URL:
     ```json
     {
       "app": "ZeroOps Demo",
       "version": "1.1.0",
       "status": "running"
     }
     ```

---

### Act 3: Intentional Failure & AI Root Cause Diagnosis

1. **Inject Deterministic Test Failure**:
   - In `app.py`, break the `/health` endpoint logic:
     ```python
     @app.get("/health")
     def health_check():
         return JSONResponse(status_code=500, content={"status": "degraded", "code": 500})
     ```
2. **Commit and Push**:
   ```bash
   git commit -am "Simulate degraded health endpoint"
   git push origin main
   ```
3. **Pipeline Failure & Blocked Deployment**:
   - ZeroOps catches webhook and launches pipeline.
   - During `unit_tests` stage, `pytest test_app.py` fails (`assert response.status_code == 200` received 500).
   - Deployment halts immediately. Azure App Service is **NOT** updated with bad code.
   - `unit_tests` stage turns **RED (FAILED)** in the UI.
4. **Inspect Failure Traceback & AI Diagnosis**:
   - Click on the failed `unit_tests` stage.
   - Show the exact test traceback:
     ```
     FAILED test_app.py::test_health_endpoint - assert 500 == 200
     ```
   - Point to the **AI Root Cause Diagnosis** card:
     - **Summary**: Unit test failed on HTTP status assertion for `/health`.
     - **Likely Root Cause**: `app.py` line 21 returning status 500 instead of 200.
     - **Recommended Fix**: Restore status_code=200 in `health_check()` function.
     - **Confidence**: High.

---

### Act 4: Recovery & Pipeline Restoration

1. **Revert the Error**:
   - In `app.py`, change status code back to 200:
     ```python
     @app.get("/health")
     def health_check():
         return JSONResponse(status_code=200, content={"status": "healthy", "code": 200})
     ```
2. **Commit and Push**:
   ```bash
   git commit -am "Fix health endpoint status code"
   git push origin main
   ```
3. **Successful Recovery**:
   - Webhook triggers new pipeline run.
   - All tests pass, pipeline progresses to completion, and Azure App Service remains healthy and responsive.

---

## Architectural Boundaries & "Do Not Claim"

During the presentation, adhere strictly to truthful reporting of implemented capabilities:

- **DO DEMO**:
  - Real GitHub connection and signed webhook ingestion.
  - Real Git diff analysis and change classification (`APPLICATION_CODE_CHANGE`).
  - Real analysis reuse preventing unnecessary full LLM scans.
  - Real isolated subprocess execution (`DemoRepositoryCheckExecutor`) with credential redaction.
  - Real unit test execution and deterministic failure prevention.
  - Real Azure App Service deployment, public health check, and live URL.
  - Real AI failure root cause diagnosis with structured summary, cause, and fix.

- **DO NOT CLAIM (Future Work / In-Progress)**:
  - **Do NOT claim AKS provisioning is live in the demo**: Multi-tenant Kubernetes provisioning is partially implemented in backend services for architecture discussions, but is not the primary demo target.
  - **Do NOT claim Terraform VMSS Service Bus apply is active**: The pipeline for this demo targets direct Azure App Service deployment; Terraform infrastructure apply stages are truthfully skipped when no infrastructure change is detected.
  - **Do NOT claim full Azure Monitor collector**: Telemetry displayed is real HTTP health, smoke tests, and deployment logs; synthetic CPU/memory graphs are not generated.
  - **Do NOT claim automated self-healing / auto-remediation**: AI provides root cause diagnosis and recommendations; it does not autonomously mutate user source code on GitHub.
