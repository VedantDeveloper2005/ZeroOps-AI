# ZeroOps AI

An Azure-first application launch platform for reviewing source and releasing
commit-pinned GitHub projects to verified Azure App Service endpoints. ZIP
uploads are supported for review and planning, not isolated-worker deployment.

## Local Runbook

1. Install dependencies:

```bash
npm install
```

2. Start the frontend:

```bash
npm run dev
```

3. Start the backend:

```bash
cd backend
pip install -r requirements.txt
export APP_ENV=development
uvicorn main:app --reload --port 8000
```

In PowerShell, use `$env:APP_ENV = "development"` before starting Uvicorn.

The dashboard expects the FastAPI backend for repository analysis, deployments, logs, monitoring, security status, and settings data. If Azure Key Vault or required Azure hosting configuration is unavailable, launch stays blocked instead of showing synthetic production data.

## Product Flow

- Landing page -> Dashboard
- Repositories -> Connect Repository
- Analyze -> application review and build plan
- Deploy -> verified Azure release when hosting is connected
- Logs, Monitoring, Autoscaling, Security, Infrastructure, and Incidents remain available as supporting proof points

## Verification

```bash
npm run lint
npm run build
python -m py_compile backend/main.py backend/config.py backend/services/ai.py backend/services/app_service.py backend/services/git.py backend/services/pipeline.py backend/services/vault.py
```

## Azure App Service

ZeroOps is production-prepared as three isolated runtimes:

- Next.js frontend App Service
- FastAPI backend App Service
- Deployment worker Azure Container App

See [docs/azure-app-service.md](docs/azure-app-service.md) for startup commands, required app settings, websocket notes, and troubleshooting.

## Configuration

Production configuration is Azure Key Vault–only. Set `APP_ENV=production`
and `AZURE_KEYVAULT_URL` as bootstrap app settings, enable a managed identity,
and store every application value in Key Vault. Browser endpoint URLs remain
public build configuration because Next.js embeds `NEXT_PUBLIC_*` values in
the client bundle. See [docs/production-key-vault.md](docs/production-key-vault.md).
