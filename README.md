# ZeroOps AI

An Azure-first application launch platform for turning GitHub repositories and ZIP uploads into verified live applications.

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
uvicorn main:app --reload --port 8000
```

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

ZeroOps is production-prepared for Azure App Service as two apps:

- Next.js frontend App Service
- FastAPI backend App Service

See [docs/azure-app-service.md](docs/azure-app-service.md) for startup commands, required app settings, websocket notes, and troubleshooting.

## Environment Variables

- `OPENAI_API_KEY`: optional, enables OpenAI-backed repository analysis.
- `GITHUB_TOKEN`: optional, enables GitHub API access for private/public repos.
- `AZURE_KEYVAULT_URL`: optional, enables Azure Key Vault secret storage.
- `PORT` and `HOST`: optional FastAPI server settings.
