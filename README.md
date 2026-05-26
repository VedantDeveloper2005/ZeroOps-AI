<<<<<<< HEAD
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
=======
This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
>>>>>>> 7a8a49ab91a776be547d07446a274f5d8f0822b2
