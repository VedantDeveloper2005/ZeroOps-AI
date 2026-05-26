# Azure App Service Deployment Guide

This guide deploys the ZeroOps SaaS control plane to Azure App Service. User applications still deploy to AKS through the ZeroOps backend.

## Recommended Topology

- `zeroops-web`: Linux Node.js App Service for the Next.js frontend.
- `zeroops-api`: Linux Python App Service for the FastAPI backend.

Use separate App Services so Node and Python runtimes can be managed independently and so backend WebSockets can be enabled explicitly.

## Frontend App Service

Runtime:

- Node.js 20 LTS or newer compatible runtime.
- Build command: `npm install && npm run build`
- Startup command: `npm start`

Required app settings:

```text
NODE_ENV=production
ZEROOPS_BACKEND_URL=https://<backend-app>.azurewebsites.net
NEXT_PUBLIC_API_BASE_URL=https://<backend-app>.azurewebsites.net
NEXT_PUBLIC_WS_BASE_URL=wss://<backend-app>.azurewebsites.net
DEPLOYMENT_VERSION=<release-id>
```

`ZEROOPS_BACKEND_URL` is used by Next.js rewrites for `/api/*` and `/ws/*`. `NEXT_PUBLIC_WS_BASE_URL` is used by browser websocket clients and must use `wss://` in production.

## Backend App Service

Runtime:

- Python 3.11+.
- Startup command: `bash startup.sh`
- Working directory: `backend`

Required app settings:

```text
APP_ENV=production
FRONTEND_ORIGIN=https://<frontend-app>.azurewebsites.net
CORS_ORIGINS=https://<frontend-app>.azurewebsites.net
WEB_CONCURRENCY=1
GUNICORN_TIMEOUT=180
```

Optional app settings:

```text
OPENAI_API_KEY=<openai-key>
GITHUB_TOKEN=<github-pat>
AZURE_KEYVAULT_URL=https://<vault-name>.vault.azure.net/
ZEROOPS_BACKEND_URL=https://<backend-app>.azurewebsites.net
```

Missing optional settings keep fallback demo mode active. The backend will still analyze demo repositories, simulate deployments, stream logs, and complete deployment flows.

## WebSocket Notes

- Enable WebSockets in the backend App Service configuration.
- Use `wss://<backend-app>.azurewebsites.net` in `NEXT_PUBLIC_WS_BASE_URL`.
- Keep `WEB_CONCURRENCY=1` for the MVP because deployment event replay buffers are in memory.
- If WebSockets are unavailable, the frontend automatically falls back to deterministic deployment and log simulation.

## Health Checks

Backend health endpoints:

- `GET /healthz`
- `GET /api/health`

Use `/healthz` for App Service health checks. `/api/health` includes integration availability flags for Docker, Kubernetes, and OpenAI.

## Verification Commands

Frontend:

```bash
npm run lint
npm run build
PORT=3000 npm start
```

Backend:

```bash
cd backend
pip install -r requirements.txt
python -m py_compile main.py config.py services/ai.py services/builder.py services/git.py services/k8s.py services/pipeline.py services/vault.py
bash startup.sh
```

## Production Troubleshooting

- If `/api/*` calls fail from the frontend, verify `ZEROOPS_BACKEND_URL` and backend CORS settings.
- If websocket streams fail, verify App Service WebSockets are enabled and `NEXT_PUBLIC_WS_BASE_URL` starts with `wss://`.
- If AI analysis fails, verify `OPENAI_API_KEY`; otherwise fallback analysis should still render.
- If AKS or Docker is unavailable, deployment simulation should still complete and show `https://web-app.zeroops.dev`.
- If deployment streams appear out of order under scale-out, keep backend `WEB_CONCURRENCY=1` or replace in-memory event buffers with shared storage before multi-instance production scale.
