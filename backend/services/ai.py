import os
import json
import re
import time
import logging
from openai import OpenAI

# Structured observability logger for all AI requests
ai_logger = logging.getLogger("zeroops.ai.observability")
ai_logger.setLevel(logging.INFO)
try:
    from backend.config import (
        OPENAI_API_KEY, GITHUB_MODELS_API_KEY, GITHUB_MODELS_ENDPOINT, GITHUB_MODELS_MODEL,
        NVIDIA_API_KEY, NVIDIA_ENDPOINT, NVIDIA_MODEL
    )
except ImportError:
    from config import (
        OPENAI_API_KEY, GITHUB_MODELS_API_KEY, GITHUB_MODELS_ENDPOINT, GITHUB_MODELS_MODEL,
        NVIDIA_API_KEY, NVIDIA_ENDPOINT, NVIDIA_MODEL
    )

def analyze_repo_local(repo_path: str, project_id: str = "default") -> dict:
    """Idempotent, deep local repository scanner when OpenAI is not configured."""
    framework = "Next.js"
    version = "16.2.6"
    language = "TypeScript"
    runtime = "Node.js 20"
    package_manager = "npm"
    docker_support = False
    monorepo_structure = "None"
    database_dependencies = []
    deployment_strategy = "Azure App Service"
    build_commands = "npm run build"
    start_commands = "npm start"
    environment_variables = ["DATABASE_URL", "JWT_SECRET"]
    
    dependencies = ["next@16.2.6", "react@19.2.4"]
    vulnerabilities = []
    cpu = "200m"
    memory = "256Mi"
    storage = "1Gi"

    # Check for Dockerfile
    if os.path.exists(os.path.join(repo_path, "Dockerfile")):
        docker_support = True

    # Check for monorepo patterns
    if os.path.exists(os.path.join(repo_path, "lerna.json")):
        monorepo_structure = "Lerna"
    elif os.path.exists(os.path.join(repo_path, "pnpm-workspace.yaml")):
        monorepo_structure = "pnpm Workspaces"
    elif os.path.exists(os.path.join(repo_path, "nx.json")):
        monorepo_structure = "Nx"

    # Check for .env or .env.example
    env_keys = []
    for env_file in [".env.example", ".env"]:
        env_p = os.path.join(repo_path, env_file)
        if os.path.exists(env_p):
            try:
                with open(env_p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key = line.split("=", 1)[0].strip()
                            if key:
                                env_keys.append(key)
            except Exception:
                pass
    if env_keys:
        environment_variables = list(set(env_keys))

    # Node.js Project Analysis
    if os.path.exists(os.path.join(repo_path, "package.json")):
        # Package manager detection
        if os.path.exists(os.path.join(repo_path, "pnpm-lock.yaml")):
            package_manager = "pnpm"
            build_commands = "pnpm run build"
            start_commands = "pnpm start"
        elif os.path.exists(os.path.join(repo_path, "yarn.lock")):
            package_manager = "yarn"
            build_commands = "yarn build"
            start_commands = "yarn start"
        else:
            package_manager = "npm"
            build_commands = "npm run build"
            start_commands = "npm start"

        try:
            with open(os.path.join(repo_path, "package.json"), "r", encoding="utf-8") as f:
                data = json.load(f)
                deps = data.get("dependencies", {})
                dev_deps = data.get("devDependencies", {})
                scripts = data.get("scripts", {})
                
                # Build & Start commands
                if "build" in scripts:
                    build_commands = f"{package_manager} run build"
                if "start" in scripts:
                    start_commands = f"{package_manager} start"
                elif "dev" in scripts:
                    start_commands = f"{package_manager} run dev"

                # Framework detection
                if "next" in deps:
                    framework = "Next.js"
                    version = deps["next"].replace("^", "").replace("~", "")
                    deployment_strategy = "Azure App Service"
                    cpu = "200m"
                    memory = "256Mi"
                elif "express" in deps:
                    framework = "Express.js"
                    version = deps["express"].replace("^", "").replace("~", "")
                    deployment_strategy = "Azure Container Apps"
                    cpu = "100m"
                    memory = "128Mi"
                elif "@nestjs/core" in deps:
                    framework = "NestJS"
                    version = deps["@nestjs/core"].replace("^", "").replace("~", "")
                    deployment_strategy = "Azure Kubernetes Service (AKS)"
                    cpu = "250m"
                    memory = "512Mi"
                else:
                    framework = "Node.js App"
                    version = "1.0.0"
                    deployment_strategy = "Azure App Service"
                    
                if "typescript" in deps or "typescript" in dev_deps:
                    language = "TypeScript"
                else:
                    language = "JavaScript"
                    
                dependencies = [f"{k}@{v}" for k, v in list(deps.items())[:8]]

                # Database dependencies detection
                db_keywords = {
                    "pg": "PostgreSQL",
                    "postgres": "PostgreSQL",
                    "mysql": "MySQL",
                    "mysql2": "MySQL",
                    "mongodb": "MongoDB",
                    "mongoose": "MongoDB",
                    "sqlite3": "SQLite",
                    "redis": "Redis",
                }
                for dep_name in deps.keys():
                    if dep_name in db_keywords:
                        database_dependencies.append(db_keywords[dep_name])
                database_dependencies = list(set(database_dependencies))
        except Exception:
            pass
            
    # Python Project Analysis
    elif os.path.exists(os.path.join(repo_path, "requirements.txt")):
        language = "Python"
        runtime = "Python 3.10"
        package_manager = "pip"
        build_commands = "None"
        start_commands = "uvicorn main:app --host 0.0.0.0 --port 8080"
        deployment_strategy = "Azure App Service"
        cpu = "150m"
        memory = "128Mi"
        dependencies = []

        try:
            with open(os.path.join(repo_path, "requirements.txt"), "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
                for line in lines[:10]:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        dependencies.append(line)
                        if "fastapi" in line.lower():
                            framework = "FastAPI"
                            start_commands = "uvicorn main:app --host 0.0.0.0 --port 8080"
                            deployment_strategy = "Azure Container Apps"
                        elif "flask" in line.lower():
                            framework = "Flask"
                            start_commands = "python app.py"
                            deployment_strategy = "Azure App Service"
                        elif "django" in line.lower():
                            framework = "Django"
                            start_commands = "python manage.py runserver 0.0.0.0:8000"
                            deployment_strategy = "Azure Kubernetes Service (AKS)"

                # Database dependencies detection
                db_keywords = {
                    "psycopg2": "PostgreSQL",
                    "asyncpg": "PostgreSQL",
                    "pymysql": "MySQL",
                    "pymongo": "MongoDB",
                    "sqlite3": "SQLite",
                    "redis": "Redis",
                }
                for dep in dependencies:
                    dep_name = dep.split("==")[0].split(">=")[0].strip().lower()
                    if dep_name in db_keywords:
                        database_dependencies.append(db_keywords[dep_name])
                database_dependencies = list(set(database_dependencies))
        except Exception:
            pass

    # Basic vulnerability warning if databases detected but no SSL
    if database_dependencies and "DATABASE_URL" in environment_variables:
        vulnerabilities.append("Medium: Ensure DATABASE_URL uses SSL connection options in production.")

    # Dynamic generation of templates
    dockerfile = generate_default_dockerfile(framework)
    k8s_manifest = generate_default_k8s_manifest(framework, cpu, memory, project_id)
    
    return {
        "framework": framework,
        "version": version,
        "language": language,
        "confidence": 0,
        "resources": {
            "cpu": cpu,
            "memory": memory,
            "storage": storage
        },
        "risk_score": 12 if not vulnerabilities else 22,
        "dependencies": dependencies,
        "vulnerabilities": vulnerabilities,
        "dockerfile": dockerfile,
        "kubernetes_manifest": k8s_manifest,
        
        # Real AI analysis fields
        "runtime": runtime,
        "package_manager": package_manager,
        "docker_support": docker_support,
        "monorepo_structure": monorepo_structure,
        "database_dependencies": database_dependencies,
        "deployment_strategy": deployment_strategy,
        "build_commands": build_commands,
        "start_commands": start_commands,
        "environment_variables": environment_variables,
        "explanation": f"Local repository analysis detected a {framework} application built with {language} using {package_manager}. No cloud cost, region, or traffic estimate was generated.",
        "recommended_compute_tier": None,
        "estimated_cost": None,
        "recommended_region": None,
        "expected_traffic": None
    }


def generate_repo_tree(repo_path: str, max_depth: int = 3) -> str:
    lines = []
    def walk(directory: str, current_depth: int = 1):
        if current_depth > max_depth:
            return
        try:
            for entry in os.scandir(directory):
                if entry.name in [".git", "node_modules", "__pycache__", ".next", "venv", ".venv", "dist", "build"]:
                    continue
                indent = "  " * (current_depth - 1)
                if entry.is_dir():
                    lines.append(f"{indent}📁 {entry.name}/")
                    walk(entry.path, current_depth + 1)
                else:
                    lines.append(f"{indent}📄 {entry.name}")
        except Exception:
            pass
    walk(repo_path)
    return "\n".join(lines)


def log_ai_request(provider: str, model: str, latency_s: float, success: bool,
                   tokens_used: int = 0, error: str = ""):
    """Structured observability log for every AI request."""
    status = "SUCCESS" if success else "FAILURE"
    ai_logger.info(
        "AI_REQUEST | provider=%s | model=%s | latency=%.3fs | tokens=%d | status=%s | error=%s",
        provider, model, latency_s, tokens_used, status, error or "none"
    )


def analyze_repository(repo_path: str, project_id: str = "default") -> dict:
    """Analyze a cloned repository using GitHub Models GPT-4.1 (gpt-4o) or OpenAI.
    
    Raises ValueError if no AI API key is configured.
    Raises RuntimeError if the AI API call fails.
    """
    api_key = GITHUB_MODELS_API_KEY or OPENAI_API_KEY
    base_url = GITHUB_MODELS_ENDPOINT if GITHUB_MODELS_API_KEY else None
    model_name = GITHUB_MODELS_MODEL if GITHUB_MODELS_API_KEY else "gpt-4o"
    provider = "github-models" if GITHUB_MODELS_API_KEY else "openai"

    if not api_key:
        ai_logger.error("AI_CONFIG_ERROR | No AI API key configured (GITHUB_MODELS_API_KEY or OPENAI_API_KEY). Cannot analyze repository.")
        raise ValueError(
            "AI provider is not configured. Set GITHUB_MODELS_API_KEY or OPENAI_API_KEY "
            "environment variable to enable repository analysis."
        )

    # Read files in the workspace (up to 3kb each) to send to AI
    files_context = {}
    target_files = ["package.json", "requirements.txt", "pyproject.toml", "Dockerfile", "docker-compose.yml", "README.md"]
    for filename in target_files:
        p = os.path.join(repo_path, filename)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    files_context[filename] = f.read()[:3000]
            except Exception:
                pass

    repo_tree = generate_repo_tree(repo_path)

    prompt = f"""
    You are the ZeroOps AI repository analysis agent. Inspect the following repository contents:
    
    Files Content:
    {json.dumps(files_context, indent=2)}
    
    Repository Directory Tree:
    {repo_tree}
    
    Output a clean JSON containing the following properties:
    1. "framework": Detected framework (e.g., "Next.js", "FastAPI", "Flask", "NestJS", "Express.js", or "Unknown")
    2. "runtime": Recommended runtime (e.g., "Node.js 22", "Python 3.11", etc.)
    3. "language": Programming language (e.g., "TypeScript", "Python", "JavaScript", "Go", "Rust")
    4. "package_manager": Detected package manager (e.g., "npm", "pnpm", "yarn", "pip", "poetry")
    5. "database": Primary database detected or recommended (e.g., "PostgreSQL", "MongoDB", "Redis", "None")
    6. "database_dependencies": List of detected databases (e.g., ["PostgreSQL", "Redis"])
    7. "docker_support": Boolean indicating if a Dockerfile is present in the repository (true/false)
    8. "deployment_target": Recommended deployment target (e.g., "Azure App Service", "Azure Container Apps", "Azure Kubernetes Service")
    9. "build_command": Command to build the project (e.g., "npm run build")
    10. "start_command": Command to start the application (e.g., "npm start", "uvicorn main:app --host 0.0.0.0 --port 8080")
    11. "required_env_vars": List of detected or recommended environment variable names (e.g., ["DATABASE_URL", "JWT_SECRET"])
    12. "deployment_risk": Brief summary of deployment risk level and potential issues
    13. "risk_score": Integer risk score from 0 (lowest risk) to 100 (highest risk)
    14. "recommendations": List of up to 5 recommendations for building, configuring, and scaling this project on Azure
    15. "confidence": Integer confidence level of this analysis (0 to 100)
    16. "cpu_recommendation": Recommended CPU limits (e.g., "200m", "500m")
    17. "memory_recommendation": Recommended Memory limits (e.g., "256Mi", "512Mi")
    18. "storage_recommendation": Recommended Storage allocation (e.g., "1Gi", "5Gi")
    19. "port": Expected port number as string (e.g., "3000", "8080")
    20. "dependencies": List of top 8 dependencies (name@version)
    21. "vulnerabilities": List of security warnings or recommendations (maps to UI vulnerabilities display)
    22. "dockerfile": Recommended or actual Dockerfile contents (string)
    23. "kubernetes_manifest": Recommended Kubernetes manifests in YAML (string), making sure all resource metadata elements specify the target namespace 'zeroops-{{project_id}}', environment variables are injected via envFrom from secretRef 'project-secrets', ingress is configured with class 'nginx', tls host '{{project_id}}.zeroops.dev', and cert-manager annotation cluster-issuer 'letsencrypt-prod'.
    24. "explanation": A plain English summary (2-3 sentences) explaining what this codebase is and what it does based on the file list and package files (e.g. 'This is a Next.js web application built with TypeScript...').
    25. "recommended_compute_tier": Recommended Azure compute tier (e.g., "Azure App Service B1", "Azure App Service B2", "Azure Container Apps Basic")
    26. "estimated_cost": Recommended monthly cost estimation as string (e.g., "$13/month", "$26/month")
    27. "recommended_region": Recommended Azure region close to major traffic (e.g., "East US", "West Europe")
    28. "expected_traffic": Expected traffic tier for the recommended compute setup as string (e.g., "50,000 requests/month", "100,000 requests/month")
    
    Respond ONLY with valid JSON. No markdown codeblocks, no extra explanation text.
    """

    start_time = time.time()
    tokens_used = 0
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        latency = time.time() - start_time
        content = response.choices[0].message.content.strip()
        
        # Extract token usage if available
        if hasattr(response, 'usage') and response.usage:
            tokens_used = getattr(response.usage, 'total_tokens', 0)
        
        log_ai_request(provider, model_name, latency, True, tokens_used)
        
        # Strip code block symbols if AI wraps response
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        data = json.loads(content)
        
        # Tag which provider/model produced this analysis
        data["_ai_provider"] = provider
        data["_ai_model"] = model_name
        
        # Backward compatibility field mapping if model returned nested structure
        if "resources" not in data:
            data["resources"] = {
                "cpu": data.get("cpu_recommendation", "200m"),
                "memory": data.get("memory_recommendation", "256Mi"),
                "storage": data.get("storage_recommendation", "1Gi")
            }
        if "version" not in data:
            data["version"] = data.get("runtime", "1.0.0")
            
        return data
    except Exception as e:
        latency = time.time() - start_time
        log_ai_request(provider, model_name, latency, False, tokens_used, str(e))
        ai_logger.error("AI_API_FAILURE | provider=%s | model=%s | error=%s", provider, model_name, e)
        raise RuntimeError(f"AI Repository Analysis API call failed ({provider}/{model_name}): {e}") from e


def analyze_failure_local(logs: list, build_logs: list) -> dict:
    """High-fidelity local fallback analyzer scanning for common logs patterns."""
    all_logs = "\n".join((logs or []) + (build_logs or []))
    
    summary = "Deployment failed during execution."
    cause = "An unspecified error occurred during the build or container deployment process."
    severity = "error"
    fix = "Review the execution logs and verify the configuration."
    steps = [
        "Check the logs for detailed trace messages.",
        "Verify environment variables and secrets are configured correctly.",
        "Trigger a new deployment."
    ]
    
    if "DATABASE_URL" in all_logs and ("missing" in all_logs or "not found" in all_logs or "connection refused" in all_logs):
        summary = "Build failed because environment variable DATABASE_URL is missing."
        cause = "The application attempted to establish a database connection, but the DATABASE_URL environment variable was either not provided or is invalid."
        severity = "critical"
        fix = "Add DATABASE_URL in project environment settings and verify database credentials."
        steps = [
            "Go to Project Settings > Environment Variables.",
            "Verify that DATABASE_URL is present and points to a valid PostgreSQL database.",
            "Check that database credentials (username, password, port) are correct.",
            "Ensure the database network security rules allow connections from ZeroOps App Service.",
            "Trigger a redeployment."
        ]
    elif "port" in all_logs and ("already in use" in all_logs or "EADDRINUSE" in all_logs):
        summary = "Port collision detected: target port already in use."
        cause = "The application attempted to bind to a port that is already occupied by another service on the host container."
        severity = "error"
        fix = "Configure the application to run on a different port or stop conflicting services."
        steps = [
            "Check the start commands in the repository scanner output.",
            "Ensure the environment variable PORT is set to a free port (e.g., 8080 or 3000).",
            "Verify that no other replica or old container is blocking the port.",
            "Trigger a redeployment."
        ]
    elif "npm ERR!" in all_logs or "yarn error" in all_logs or "SyntaxError" in all_logs:
        summary = "Build failed due to dependency compilation or syntax error."
        cause = "The package builder encountered syntax errors or unresolved dependencies during the build phase (npm run build)."
        severity = "error"
        fix = "Fix compilation and syntax errors in the source repository."
        steps = [
            "Verify dependencies are correctly declared in package.json.",
            "Run npm run build locally to diagnose typescript compiler or linter errors.",
            "Commit fixes and push to trigger a new build."
        ]
    elif "OutOfMemory" in all_logs or "OOMKilled" in all_logs:
        summary = "Container was terminated due to an Out Of Memory (OOM) event."
        cause = "The container exceeded the allocated memory limit defined in the Kubernetes manifest and was terminated by the kernel OOM killer."
        severity = "critical"
        fix = "Increase the memory limit in the deployment configuration or optimize application memory usage."
        steps = [
            "Go to Project Settings > Autoscaling & Resources.",
            "Increase the memory resource limits (e.g., change from 256Mi to 512Mi).",
            "Analyze the application code for memory leaks.",
            "Trigger a redeployment."
        ]

    return {
        "failure_summary": summary,
        "root_cause": cause,
        "severity": severity,
        "recommended_fix": fix,
        "step_by_step_resolution": steps
    }


def analyze_failure_nemotron(logs: list, build_logs: list, events: list = None) -> dict:
    """Analyze a failed deployment using NVIDIA Nemotron.
    
    Raises ValueError if NVIDIA_API_KEY is not configured.
    Raises RuntimeError if the NVIDIA API call fails.
    """
    if not NVIDIA_API_KEY:
        ai_logger.error("AI_CONFIG_ERROR | NVIDIA_API_KEY is not configured. Cannot perform failure analysis.")
        raise ValueError(
            "NVIDIA AI provider is not configured. Set NVIDIA_API_KEY "
            "environment variable to enable failure analysis."
        )

    logs_str = "\n".join(logs) if logs else "No deployment logs available."
    build_logs_str = "\n".join(build_logs) if build_logs else "No build logs available."
    events_str = "\n".join(events) if events else "No infrastructure events available."

    prompt = f"""
    You are an expert systems engineer and root cause analysis AI. You are analyzing a deployment failure in a cloud orchestration platform.
    Below are the deployment logs, build logs, and infrastructure events:
    
    === DEPLOYMENT LOGS ===
    {logs_str}
    
    === BUILD LOGS ===
    {build_logs_str}
    
    === INFRASTRUCTURE EVENTS ===
    {events_str}
    
    Analyze the failure and output a clean JSON with the following fields:
    1. "failure_summary": A concise one-sentence description of the failure (e.g., "Build failed because environment variable DATABASE_URL is missing.")
    2. "root_cause": A detailed explanation of why the failure occurred, citing specific lines or logs.
    3. "severity": The severity level of this issue ("critical", "warning", or "error").
    4. "recommended_fix": A high-level description of how to resolve the failure (e.g., "Add DATABASE_URL in project environment settings.")
    5. "step_by_step_resolution": A list of clear, actionable steps to fix the issue.
    
    Respond ONLY with valid JSON. No markdown codeblocks, no extra explanation text.
    """

    start_time = time.time()
    tokens_used = 0
    try:
        client = OpenAI(api_key=NVIDIA_API_KEY, base_url=NVIDIA_ENDPOINT)
        response = client.chat.completions.create(
            model=NVIDIA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        latency = time.time() - start_time
        content = response.choices[0].message.content.strip()
        
        # Extract token usage if available
        if hasattr(response, 'usage') and response.usage:
            tokens_used = getattr(response.usage, 'total_tokens', 0)
        
        log_ai_request("nvidia-nemotron", NVIDIA_MODEL, latency, True, tokens_used)
        
        # Strip code block symbols if AI wraps response
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        data = json.loads(content)
        data["_ai_provider"] = "nvidia-nemotron"
        data["_ai_model"] = NVIDIA_MODEL
        return data
    except Exception as e:
        latency = time.time() - start_time
        log_ai_request("nvidia-nemotron", NVIDIA_MODEL, latency, False, tokens_used, str(e))
        ai_logger.error("AI_API_FAILURE | provider=nvidia-nemotron | model=%s | error=%s", NVIDIA_MODEL, e)
        raise RuntimeError(f"NVIDIA Nemotron Failure Analysis API call failed: {e}") from e

def generate_default_dockerfile(framework: str) -> str:
    if framework == "FastAPI" or framework == "Flask":
        return """FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]"""
    else: # Default Node/Nextjs
        return """FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]"""

def generate_default_k8s_manifest(framework: str, cpu: str, memory: str, project_id: str = "default") -> str:
    port = 8080 if framework in ["FastAPI", "Flask"] else 3000
    name = "fastapi-service" if framework in ["FastAPI", "Flask"] else "web-app"
    ns_name = f"zeroops-{project_id}"
    return f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  namespace: {ns_name}
  labels:
    app: {name}
spec:
  replicas: 2
  selector:
    matchLabels:
      app: {name}
  template:
    metadata:
      labels:
        app: {name}
    spec:
      containers:
      - name: app
        image: acr.azurecr.io/{name}:v1.0.0
        ports:
        - containerPort: {port}
        resources:
          limits:
            cpu: "{cpu}"
            memory: "{memory}"
          requests:
            cpu: "100m"
            memory: "128Mi"
        envFrom:
        - secretRef:
            name: project-secrets
            optional: true
---
apiVersion: v1
kind: Service
metadata:
  name: {name}-svc
  namespace: {ns_name}
spec:
  selector:
    app: {name}
  ports:
  - protocol: TCP
    port: 80
    targetPort: {port}
  type: ClusterIP
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {name}-ingress
  namespace: {ns_name}
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - {project_id}.zeroops.dev
    secretName: {name}-tls-cert
  rules:
  - host: {project_id}.zeroops.dev
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: {name}-svc
            port:
              number: 80
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {name}-hpa
  namespace: {ns_name}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {name}
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70"""


def generate_chat_response(message: str, project_metadata: dict = None) -> str:
    """Generate a conversational response for the AI DevOps Assistant.
    Calls GitHub Models/OpenAI if available, or falls back to a smart context-aware local responder.
    """
    api_key = GITHUB_MODELS_API_KEY or OPENAI_API_KEY
    base_url = GITHUB_MODELS_ENDPOINT if GITHUB_MODELS_API_KEY else None
    model_name = GITHUB_MODELS_MODEL if GITHUB_MODELS_API_KEY else "gpt-4o"
    provider = "github-models" if GITHUB_MODELS_API_KEY else "openai"

    if api_key:
        prompt = f"""
        You are the ZeroOps AI DevOps Assistant, an autonomic cloud engineer managing the user's project.
        Provide a concise, helpful response (max 3-4 sentences, Vercel-like outcomes focus) to the user's message.
        Always explain outcomes, do not expose unnecessary cloud complexity unless asked.
        
        Project Context:
        {json.dumps(project_metadata or {}, indent=2)}
        
        User Message: "{message}"
        """
        try:
            start_time = time.time()
            client = OpenAI(api_key=api_key, base_url=base_url)
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            latency = time.time() - start_time
            content = response.choices[0].message.content.strip()
            tokens_used = getattr(response.usage, 'total_tokens', 0) if hasattr(response, 'usage') and response.usage else 0
            log_ai_request(provider, model_name, latency, True, tokens_used)
            return content
        except Exception as e:
            log_ai_request(provider, model_name, 0.0, False, error=str(e))
            # Fall back to local responder on API error
            pass

    # Context-aware local responder
    msg = message.lower()
    metadata = project_metadata or {}
    framework = metadata.get("framework") or "this project"
    db = metadata.get("database")
    latest_deployment = metadata.get("latest_deployment") or {}
    url = latest_deployment.get("live_url") if isinstance(latest_deployment, dict) else None
    region = metadata.get("region") or "no region recorded"
    deployment_status = latest_deployment.get("status") if isinstance(latest_deployment, dict) else None

    if "arch" in msg or "diagram" in msg or "flow" in msg:
        return f"I can summarize the recorded metadata: framework={framework}, region={region}, database={db or 'not recorded'}, latest deployment status={deployment_status or 'not recorded'}. No provisioned architecture diagram has been recorded yet."
    elif "cost" in msg or "price" in msg or "optimize" in msg:
        return "No cost estimate has been recorded for this project yet. Connect cloud billing or cost telemetry before applying cost recommendations."
    elif "scale" in msg or "scaling" in msg or "replicas" in msg:
        return "Autoscaling configuration is only available when the backend records it for this project. Check the Autoscaling page for the current saved policy."
    elif "db" in msg or "database" in msg or "postgres" in msg:
        return f"Recorded database dependency: {db or 'none'}. I do not have a recorded database provisioning event for this project."
    elif "error" in msg or "logs" in msg or "fail" in msg:
        return "I can review recorded deployment logs and failure analysis when they exist. No clean-startup result is assumed without backend logs."
    else:
        live_url = f" Live URL: {url}." if url else ""
        return f"I can answer from recorded ZeroOps backend data for {framework}.{live_url} Ask about deployments, logs, scaling, database metadata, or cost telemetry."

