import json

from backend.services import ai


def test_local_node_analysis_does_not_invent_capacity_port_or_scores(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {"next": "16.2.12"},
                "scripts": {"build": "next build"},
            }
        ),
        encoding="utf-8",
    )

    result = ai.analyze_repo_local(str(tmp_path), "truth-test")

    assert result["framework"] == "Next.js"
    assert result["build_commands"] == "npm run build"
    assert result["start_commands"] is None
    assert result["port"] is None
    assert result["resources"] == {"cpu": None, "memory": None, "storage": None}
    assert result["confidence"] == 0
    assert result["risk_score"] == 0
    assert result["dockerfile"] is None


def test_local_analysis_returns_only_repository_dockerfile(tmp_path):
    dockerfile = "FROM node:22-alpine\nEXPOSE 4321\n"
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {}, "scripts": {}}),
        encoding="utf-8",
    )
    (tmp_path / "Dockerfile").write_text(dockerfile, encoding="utf-8")

    result = ai.analyze_repo_local(str(tmp_path), "docker-truth-test")

    assert result["dockerfile"] == dockerfile
    assert result["port"] == "4321"


AZURE_DEMO_PACKAGE = {
    "scripts": {
        "dev": "vite",
        "build": "vite build",
        "preview": "vite preview",
    },
    "dependencies": {
        "canvas-confetti": "^1.9.4",
        "lucide-react": "^1.31.0",
        "react": "^19.2.8",
        "react-dom": "^19.2.8",
    },
    "devDependencies": {
        "@vitejs/plugin-react": "^6.0.4",
        "vite": "^8.2.0",
    },
}

AZURE_DEMO_DOCKERFILE = """FROM node:20-alpine AS builder
WORKDIR /app
COPY . .
RUN npm run build
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY package.json ./
EXPOSE 8080
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "8080"]
"""

AZURE_DEMO_APP = """import React, { useEffect, useState } from 'react';
export default function App() {
  const [requestCount, setRequestCount] = useState(42);
  const [uptime, setUptime] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setUptime(value => value + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  return <main>
    <p>Healthy (200 OK)</p><code>GET /api/health</code>
    <p>Requests Handled: {requestCount}</p>
    <button onClick={() => setRequestCount(value => value + 1)}>Ping</button>
    <p>Process Uptime: {uptime}s</p><small>Active Node process</small>
  </main>;
}
"""


def _assert_azure_demo_facts(result):
    assert result["framework"] == "React"
    assert result["version"] == "19.2.8"
    assert result["runtime"] == "Node.js 20"
    assert result["application_type"] == "React single-page application (Vite 8.2.0)"
    assert result["build_commands"] == "npm run build"
    assert result["start_commands"] == "npm run dev -- --host 0.0.0.0 --port 8080"
    assert result["port"] == "8080"
    assert result["deployment_strategy"] == "Docker container"
    findings = "\n".join(result["vulnerabilities"])
    assert "development server in the runtime image" in findings
    assert "will not serve the built application correctly" in findings
    assert "hardcodes 'Healthy (200 OK)'" in findings
    assert "not measured request telemetry" in findings
    assert "not server process uptime" in findings


def test_azure_demo_filesystem_analysis_is_source_grounded(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "package.json").write_text(json.dumps(AZURE_DEMO_PACKAGE), encoding="utf-8")
    (tmp_path / "Dockerfile").write_text(AZURE_DEMO_DOCKERFILE, encoding="utf-8")
    (tmp_path / "src" / "App.jsx").write_text(AZURE_DEMO_APP, encoding="utf-8")

    _assert_azure_demo_facts(ai.analyze_repo_local(str(tmp_path), "azure-demo-local"))


def test_azure_demo_virtual_context_analysis_matches_filesystem_facts():
    context = {
        "files_list": ["package.json", "Dockerfile", "src/App.jsx"],
        "files_context": {
            "package.json": json.dumps(AZURE_DEMO_PACKAGE),
            "Dockerfile": AZURE_DEMO_DOCKERFILE,
            "src/App.jsx": AZURE_DEMO_APP,
        },
        "scanned_vars": [],
    }

    _assert_azure_demo_facts(ai.analyze_repo_local(context, "azure-demo-virtual"))
