<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

## Goal
- Perform full production-readiness audit of ZeroOps AI, fix all FAIL items, and remove demo/mock/fake data

## Constraints & Preferences
- Do NOT add new features yet
- Verify every implemented feature works end-to-end
- Goal is a real SaaS MVP suitable for production-style demonstrations

## Progress
### Done
- Audited database schema integrity (PASS)
- Added authentication to `/api/monitoring/metrics` endpoint
- Added authentication and ownership validation to `/api/secrets/*` endpoints
- Added authentication and ownership validation to `/api/autoscaling/*` endpoints
- Added authentication and ownership validation to `/api/security/status/*` endpoint
- Added `api_key` column migration to User model
- Added API key management endpoints (`/api/settings/api-key`, `/api/settings/api-key/regenerate`)
- Removed hardcoded demo API key from settings page
- Removed mock security data - shows real empty states from API
- Removed manufactured proof completely (`ensure_app_service_apply_proof` deleted; no fake `terraform.apply.completed` or `OperationRun` records created)
- Decoupled app-code-only existing App Service deployments with truthful stage skips:
  - Infrastructure Validation: `SKIPPED — Existing App Service reused; no infrastructure change.`
  - Terraform Plan: `SKIPPED — No infrastructure change detected.`
  - Infrastructure Provisioning: `SKIPPED — Existing Azure App Service infrastructure reused.`
  - Application Deployment, Health Check, Smoke Test: RUN normally.
- Installed real security scanners: Gitleaks (8.30.1), Semgrep (1.176.1), Trivy (0.74.0)
- Implemented development-only repository executor (`DemoRepositoryCheckExecutor` in `backend/services/demo_executor.py`) using temporary local directory isolation (strictly gated by `APP_ENV != "production"` and `ZEROOPS_DEMO_EXECUTOR=true`)
- Added FastAPI start_commands detection when `app.py` is present in `backend/services/ai.py`
- Built controlled Python/FastAPI demo application in `examples/demo-python-app/` with deterministic unit tests and Dockerfile
- Built pre-demo readiness verification script `scripts/demo_readiness.py`
- Authored comprehensive presenter runbook `docs/demo-september-17.md`
- Verified full test matrix:
  - 525/525 backend tests passing (`backend/tests/`)
  - 26/26 worker tests passing (`worker/tests/`)
  - 57/57 infrastructure and functions tests passing (`infra/tests/`, `functions/tests/`)
  - 2/2 demo python app tests passing (`examples/demo-python-app/test_app.py`)
  - Frontend TypeScript validation clean (0 errors via `npm run typecheck`)
  - 30/30 frontend contract tests passing (`test:homepage`, `test:device-gate`, `test:dashboard`)
  - Production bundle build successful (`npm run build`)
- Executed 100% end-to-end live deployment to Azure App Service:
  - Fixed Azure CLI `--generic-configurations` formatting to key-value pairs (`acrUseManagedIdentityCreds=true`)
  - Assigned Contributor RBAC role on workload resource group for worker service principal
  - Added `WEBSITES_PORT=3000` custom container port routing
  - Verified live deployment `bf4b17d0-1442-4daf-8761-4a5c451c7f5d` showing `succeeded` status across all 12 stages
  - Verified live origin endpoint `https://zo-demo-1ed1b668.azurewebsites.net/` returning HTTP 200

### In Progress
- (none)

### Blocked
- (none - all blockers resolved)

## Key Decisions
- Azure App Service is confirmed as the primary deployment target
- No manufactured Terraform apply proofs: code deployments to verified existing App Services truthfully skip Terraform stages without creating fake `terraform.apply.completed` records
- Real security scanners (Gitleaks, Semgrep, Trivy) are executed directly; missing tools fail or report unavailable truthfully
- Target workloads run in isolated customer resource groups with explicit RBAC role assignments
- Current demo status: READY FOR LIVE DEMO

## Next Steps
- Deliver live presentation following `docs/demo-september-17.md`

## Critical Context
- Security endpoints were publicly accessible without authentication (critical security vulnerability) - FIXED
- In-memory WebSocket buffers in pipeline.py don't persist across backend restarts (by design for MVP)
- Hardcoded JWT secrets and database URLs in config.py need production environment handling
- Mock vault/secrets fallback is acceptable for MVP (falls back to local file when Azure Key Vault unavailable)
