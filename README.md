# ZeroOps AI

AI-powered autonomous cloud deployment platform for turning GitHub repositories into Kubernetes-ready deployments.

## Demo Runbook

1. Install dependencies:

```bash
npm install
```

2. Start the frontend:

```bash
npm run dev
```

3. Optional backend:

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The frontend is demo-safe without the backend. If FastAPI, Docker, Kubernetes, Azure Key Vault, or OpenAI are unavailable, ZeroOps falls back to a guided autonomous deployment simulation with realistic repositories, AI analysis, pipeline logs, namespace isolation, HPA, ingress, HTTPS, monitoring, and security states.

## Primary Demo Flow

- Landing page -> Dashboard
- Repositories -> Connect Repository
- Analyze -> AI repository analysis and Kubernetes plan
- Deploy -> live pipeline or guided fallback
- Logs, Monitoring, Autoscaling, Security, Infrastructure, and Incidents remain available as supporting proof points

## Verification

```bash
npm run lint
npm run build
python -m py_compile backend/main.py backend/config.py backend/services/ai.py backend/services/builder.py backend/services/git.py backend/services/k8s.py backend/services/pipeline.py backend/services/vault.py
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
