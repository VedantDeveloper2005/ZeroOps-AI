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
- Startup command: `gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app`
- Working directory: `/home/site/wwwroot`

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

Missing optional integrations are reported through health checks and empty or unavailable dashboard states. Deployment and log flows require the backend services they depend on.

## WebSocket Notes

- Enable WebSockets in the backend App Service configuration.
- Use `wss://<backend-app>.azurewebsites.net` in `NEXT_PUBLIC_WS_BASE_URL`.
- Keep `WEB_CONCURRENCY=1` for the MVP because deployment event replay buffers are in memory.
- If WebSockets are unavailable, deployment and log views show the recorded backend state and an unavailable stream message.

## Health Checks

Backend health endpoints:

- `GET /health` (Returns `{"status": "ok"}` to verify backend is alive)
- `GET /healthz` (Returns `{"status": "ok"}`)
- `GET /api/health` (Detailed status including integration availability flags for Docker, Kubernetes, and OpenAI)

Use `/health` or `/healthz` for App Service health checks. `/api/health` includes integration availability flags for Docker, Kubernetes, and OpenAI.

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
- If AI analysis fails, verify `OPENAI_API_KEY` or the configured local analyzer path.
- If AKS or Docker is unavailable, deployment status should remain queued, failed, or unavailable instead of showing a synthetic live URL.
- If deployment streams appear out of order under scale-out, keep backend `WEB_CONCURRENCY=1` or replace in-memory event buffers with shared storage before multi-instance production scale.
