# ZeroOps Azure App Service Deployment Plan

Status: Ready for Validation

## Target

Deploy ZeroOps as two Azure App Service apps:

- Frontend: Node.js App Service running Next.js 16 with `npm run build` and `npm start`.
- Backend: Python App Service running FastAPI with Gunicorn and Uvicorn workers.

User workloads continue to deploy into AKS through the backend services and fall back to deterministic simulation when AKS, Docker, Azure, OpenAI, or WebSockets are unavailable.

## App Service Configuration

- Enable WebSockets on the backend App Service.
- Keep backend `WEB_CONCURRENCY=1` for the MVP so in-memory deployment event buffers and websocket streams stay synchronized.
- Set frontend `ZEROOPS_BACKEND_URL` for Next.js server rewrites.
- Set frontend `NEXT_PUBLIC_WS_BASE_URL` to the backend `wss://` URL for browser websocket connections.
- Set backend `CORS_ORIGINS` or `FRONTEND_ORIGIN` to the frontend App Service origin.

## Validation

- `npm run lint`
- `npm run build`
- `npm start` with `PORT` set by App Service
- `python -m py_compile` for backend modules
- backend `/api/health` and `/healthz`
- frontend route smoke test
- fallback deployment flow with backend/websocket unavailable

## Notes

No production deployment is executed by this plan. Use Azure validation before running any deployment command.
