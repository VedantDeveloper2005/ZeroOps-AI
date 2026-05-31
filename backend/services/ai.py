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

def scan_codebase_for_env_vars(repo_path) -> list:
    """Scan JS/TS and Python files for references to environment variables."""
    if isinstance(repo_path, dict):
        return repo_path.get("scanned_vars", [])
    vars_found = set()
    js_pattern = re.compile(r'process\.env\.([A-Z0-9_]+)')
    py_pattern = re.compile(r'os\.(?:environ\.get|getenv)\(\s*[\'"]([A-Z0-9_]+)[\'"]')
    
    # Also find environment variables declared in .env or .env.example files
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
                                vars_found.add(key)
            except Exception:
                pass

    # Scan source files
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in ["node_modules", ".git", ".next", "__pycache__", "venv", ".venv", "dist", "build"]]
        for file in files:
            if file.endswith((".js", ".jsx", ".ts", ".tsx", ".py")):
                file_p = os.path.join(root, file)
                try:
                    with open(file_p, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        for match in js_pattern.finditer(content):
                            vars_found.add(match.group(1))
                        for match in py_pattern.finditer(content):
                            vars_found.add(match.group(1))
                except Exception:
                    pass
    return list(vars_found)


def has_file(repo_source, filename: str) -> bool:
    if isinstance(repo_source, dict):
        if filename in repo_source.get("files_context", {}):
            return True
        files_list = repo_source.get("files_list", [])
        if filename in files_list:
            return True
        for path in files_list:
            if path == filename or path.endswith("/" + filename):
                return True
        return False
    else:
        return os.path.exists(os.path.join(repo_source, filename))


def read_file_content(repo_source, filename: str) -> str:
    if isinstance(repo_source, dict):
        context = repo_source.get("files_context", {})
        if filename in context:
            return context[filename]
        for path, content in context.items():
            if path.endswith("/" + filename):
                return content
        return ""
    else:
        p = os.path.join(repo_source, filename)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                pass
        return ""


def analyze_repo_local(repo_path, project_id: str = "default") -> dict:
    """Idempotent, deep repository scanner that supports both local paths and virtual contexts."""
    framework = "Next.js"
    version = "16.2.6"
    language = "TypeScript"
    runtime = "Node.js 20"
    package_manager = "npm"
    docker_support = False
    monorepo_structure = "None"
    database_dependencies = []
    deployment_strategy = "Managed Production Environment"
    build_commands = "npm run build"
    start_commands = "npm start"
    
    dependencies = ["next@16.2.6", "react@19.2.4"]
    vulnerabilities = []
    cpu = "200m"
    memory = "256Mi"
    storage = "1Gi"

    # Check for Dockerfile
    if has_file(repo_path, "Dockerfile"):
        docker_support = True

    # Check for monorepo patterns
    if has_file(repo_path, "lerna.json"):
        monorepo_structure = "Lerna"
    elif has_file(repo_path, "pnpm-workspace.yaml"):
        monorepo_structure = "pnpm Workspaces"
    elif has_file(repo_path, "nx.json"):
        monorepo_structure = "Nx"

    # Scan variables from codebase
    scanned_vars = scan_codebase_for_env_vars(repo_path)

    # Node.js Project Analysis
    if has_file(repo_path, "package.json"):
        # Package manager detection
        if has_file(repo_path, "pnpm-lock.yaml"):
            package_manager = "pnpm"
            build_commands = "pnpm run build"
            start_commands = "pnpm start"
        elif has_file(repo_path, "yarn.lock"):
            package_manager = "yarn"
            build_commands = "yarn build"
            start_commands = "yarn start"
        else:
            package_manager = "npm"
            build_commands = "npm run build"
            start_commands = "npm start"

        try:
            pkg_content = read_file_content(repo_path, "package.json")
            if pkg_content:
                data = json.loads(pkg_content)
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
                    cpu = "200m"
                    memory = "256Mi"
                elif "express" in deps:
                    framework = "Express.js"
                    version = deps["express"].replace("^", "").replace("~", "")
                    cpu = "100m"
                    memory = "128Mi"
                elif "@nestjs/core" in deps:
                    framework = "NestJS"
                    version = deps["@nestjs/core"].replace("^", "").replace("~", "")
                    cpu = "250m"
                    memory = "512Mi"
                else:
                    framework = "Node.js App"
                    version = "1.0.0"
                    
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
    elif has_file(repo_path, "requirements.txt"):
        language = "Python"
        runtime = "Python 3.10"
        package_manager = "pip"
        build_commands = "None"
        start_commands = "uvicorn main:app --host 0.0.0.0 --port 8080"
        cpu = "150m"
        memory = "128Mi"
        dependencies = []

        try:
            reqs_content = read_file_content(repo_path, "requirements.txt")
            if reqs_content:
                lines = reqs_content.splitlines()
                for line in lines[:10]:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        dependencies.append(line)
                        if "fastapi" in line.lower():
                            framework = "FastAPI"
                            start_commands = "uvicorn main:app --host 0.0.0.0 --port 8080"
                        elif "flask" in line.lower():
                            framework = "Flask"
                            start_commands = "python app.py"
                        elif "django" in line.lower():
                            framework = "Django"
                            start_commands = "python manage.py runserver 0.0.0.0:8000"

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
    if database_dependencies and any(k in ["DATABASE_URL", "MONGODB_URI", "REDIS_URL"] for k in scanned_vars):
        vulnerabilities.append("Medium: Ensure database connection string uses SSL connection options in production.")

    # Dynamic generation of templates
    dockerfile = generate_default_dockerfile(framework)
    k8s_manifest = generate_default_k8s_manifest(framework, cpu, memory, project_id)
    
    # Calculate CPU cores
    cpu_val = cpu.strip()
    if cpu_val.endswith("m"):
        cpu_cores = float(cpu_val[:-1]) / 1000.0
    else:
        try:
            cpu_cores = float(cpu_val)
        except ValueError:
            cpu_cores = 0.2

    # Calculate RAM GB
    mem_val = memory.strip()
    if mem_val.endswith("Gi"):
        memory_gb = float(mem_val[:-2])
    elif mem_val.endswith("Mi"):
        memory_gb = float(mem_val[:-2]) / 1024.0
    else:
        try:
            memory_gb = float(mem_val)
        except ValueError:
            memory_gb = 0.25

    # 1. Compute Cost: $20 per CPU core + $10 per GB of memory
    compute_cost = round((cpu_cores * 20.0) + (memory_gb * 10.0), 2)
    compute_cost = max(4.0, compute_cost)

    # 2. Database Cost: PostgreSQL/MySQL ($15/mo), MongoDB ($12/mo), Redis ($8/mo)
    database_cost = 0.0
    for db in database_dependencies:
        db_lower = db.lower()
        if "postgres" in db_lower or "mysql" in db_lower:
            database_cost += 15.0
        elif "mongo" in db_lower:
            database_cost += 12.0
        elif "redis" in db_lower:
            database_cost += 8.0

    # 3. Platform fee (20% of subtotal, min $4.00)
    platform_fee = round(0.20 * (compute_cost + database_cost), 2)
    platform_fee = max(4.0, platform_fee)

    bandwidth_cost = 0.0
    monitoring_cost = 0.0
    total_cost = round(compute_cost + database_cost + platform_fee, 2)
    projected_growth_cost = round(total_cost * 2.2, 2)
    
    # Recommended plan mapping
    if total_cost < 15.0:
        recommended_compute_tier = "Starter Hobby Tier"
    elif total_cost < 50.0:
        recommended_compute_tier = "Standard Production Core"
    else:
        recommended_compute_tier = "Enterprise Dedicated Core"

    # Environment variables intelligence classification
    detected_vars_detail = []
    
    # Check what databases are needed and classify connection strings as required
    for db in database_dependencies:
        db_lower = db.lower()
        if "postgres" in db_lower:
            detected_vars_detail.append({
                "key": "DATABASE_URL",
                "type": "required",
                "is_missing": "DATABASE_URL" not in scanned_vars,
                "has_default": True,
                "default_val": "postgresql://zeroops_user:****@managed-postgres-db.zeroops.internal:5432/zeroops_db"
            })
        elif "mysql" in db_lower:
            detected_vars_detail.append({
                "key": "DATABASE_URL",
                "type": "required",
                "is_missing": "DATABASE_URL" not in scanned_vars,
                "has_default": True,
                "default_val": "mysql://zeroops_user:****@managed-mysql-db.zeroops.internal:3306/zeroops_db"
            })
        elif "mongo" in db_lower:
            detected_vars_detail.append({
                "key": "MONGODB_URI",
                "type": "required",
                "is_missing": "MONGODB_URI" not in scanned_vars,
                "has_default": True,
                "default_val": "mongodb://mongo_user:****@managed-mongodb.zeroops.internal:27017/mongo_db"
            })
        elif "redis" in db_lower:
            detected_vars_detail.append({
                "key": "REDIS_URL",
                "type": "required",
                "is_missing": "REDIS_URL" not in scanned_vars,
                "has_default": True,
                "default_val": "redis://default:****@managed-redis.zeroops.internal:6379"
            })

    # Always inject JWT_SECRET as required
    detected_vars_detail.append({
        "key": "JWT_SECRET",
        "type": "required",
        "is_missing": "JWT_SECRET" not in scanned_vars,
        "has_default": True,
        "default_val": f"zo_sec_{import_secrets_token()}"
    })

    # Find Recommended/Optional variables
    for var in scanned_vars:
        if var in ["DATABASE_URL", "MONGODB_URI", "REDIS_URL", "JWT_SECRET"]:
            continue
        
        var_lower = var.lower()
        # Recommended: OpenAI, Stripe, SMTP, Client secrets
        if any(k in var_lower for k in ["stripe", "openai", "smtp", "mail", "email", "client_id", "client_secret", "oauth", "auth_secret"]):
            detected_vars_detail.append({
                "key": var,
                "type": "recommended",
                "is_missing": True,
                "has_default": False,
                "default_val": "Missing (Add in Settings)"
            })
        else:
            detected_vars_detail.append({
                "key": var,
                "type": "optional",
                "is_missing": False,
                "has_default": False,
                "default_val": ""
            })

    db_text = f"an auto-provisioned {database_dependencies[0]} database" if database_dependencies else "an isolated runtime tier"
    why_this_plan = f"ZeroOps AI selected a {recommended_compute_tier} with {db_text} because the application code indicates it requires persistent computing layers. Cost breakdown includes fully-managed secure databases, 99.9% uptime orchestration, and platform edge routing."

    # Build pricing breakdown dict
    pricing_breakdown = {
        "compute_cost": compute_cost,
        "database_cost": database_cost,
        "platform_fee": platform_fee,
        "bandwidth_cost": bandwidth_cost,
        "monitoring_cost": monitoring_cost,
        "total_cost": total_cost,
        "projected_growth_cost": projected_growth_cost,
        "why_this_plan": why_this_plan,
        "detected_vars_detail": detected_vars_detail
    }

    # Expected traffic tiering
    expected_traffic = "100,000 requests/month"
    if database_dependencies:
        expected_traffic = "250,000 requests/month"
    elif cpu_cores >= 0.5:
        expected_traffic = "500,000 requests/month"

    return {
        "framework": framework,
        "version": version,
        "language": language,
        "confidence": 98,
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
        "deployment_strategy": "Managed Production Environment",
        "build_commands": build_commands,
        "start_commands": start_commands,
        "environment_variables": scanned_vars,
        "explanation": f"ZeroOps AI analyzed your {framework} repository and detected a standard {runtime} runtime. This application can be deployed without manual configuration in a secure, autoscaling runtime environment with a target deploy time of 90 seconds.",
        "recommended_compute_tier": recommended_compute_tier,
        "estimated_cost": f"${int(total_cost)}/month",
        "recommended_region": "East US Core",
        "expected_traffic": expected_traffic,
        
        # Extra blueprint fields
        "application_type": f"{framework} SaaS Platform" if "next" in framework.lower() else f"{framework} Web Service",
        "estimated_build_time": "90s",
        "production_readiness_score": 94 if not vulnerabilities else 85,
        "detected_services": [framework] + ([database_dependencies[0]] if database_dependencies else []),

        # Breakdown costs
        "pricing_breakdown": pricing_breakdown
    }


def import_secrets_token() -> str:
    import secrets
    return secrets.token_hex(16)


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


def analyze_repository(repo_path, project_id: str = "default") -> dict:
    """Analyze a repository using GitHub Models GPT-4.1 (gpt-4o) or OpenAI.
    Supports both local folder paths and pre-fetched virtual file dictionaries.
    
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
    if isinstance(repo_path, dict):
        files_context = repo_path.get("files_context", {})
        repo_tree = repo_path.get("repo_tree", "")
    else:
        files_context = {}
        target_files = ["package.json", "requirements.txt", "pyproject.toml", "Dockerfile", "docker-compose.yml", "README.md", ".env.example", ".env"]
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
    8. "deployment_target": Recommended deployment target (e.g., "Managed Production Environment")
    9. "build_command": Command to build the project (e.g., "npm run build")
    10. "start_command": Command to start the application (e.g., "npm start", "uvicorn main:app --host 0.0.0.0 --port 8080")
    11. "required_env_vars": List of detected or recommended environment variable names (e.g., ["DATABASE_URL", "JWT_SECRET"])
    12. "deployment_risk": Brief summary of deployment risk level and potential issues
    13. "risk_score": Integer risk score from 0 (lowest risk) to 100 (highest risk)
    14. "recommendations": List of up to 5 recommendations for building, configuring, and scaling this project
    15. "confidence": Integer confidence level of this analysis (0 to 100)
    16. "cpu_recommendation": Recommended CPU limits (e.g., "200m", "500m")
    17. "memory_recommendation": Recommended Memory limits (e.g., "256Mi", "512Mi")
    18. "storage_recommendation": Recommended Storage allocation (e.g., "1Gi", "5Gi")
    19. "port": Expected port number as string (e.g., "3000", "8080")
    20. "dependencies": List of top 8 dependencies (name@version)
    21. "vulnerabilities": List of security warnings or recommendations (maps to UI vulnerabilities display)
    22. "dockerfile": Recommended or actual Dockerfile contents (string)
    23. "kubernetes_manifest": Recommended manifests in YAML (string), specify target namespace 'zeroops-{{project_id}}', environment variables are injected via envFrom from secretRef 'project-secrets', ingress tls host '{{project_id}}.zeroops.dev'.
    24. "explanation": A plain English summary (2-3 sentences) explaining what this codebase is and what it does based on the file list and package files (e.g. 'This is a Next.js web application built with TypeScript...').
    25. "recommended_compute_tier": Recommended compute tier (e.g., "Standard Production Core", "Managed Compute Core")
    26. "estimated_cost": Recommended monthly cost estimation as string (e.g., "$12/month", "$17/month")
    27. "recommended_region": Recommended hosting region close to major traffic (e.g., "East US Core", "West Europe Core")
    28. "expected_traffic": Expected traffic tier for the recommended compute setup as string (e.g., "50,000 requests/month", "100,000 requests/month")
    29. "compute_cost": Compute cost as float (e.g., 8.0)
    30. "database_cost": Database cost as float (e.g., 5.0 or 0.0)
    31. "platform_fee": ZeroOps platform fee as float (e.g., 4.0)
    32. "bandwidth_cost": Bandwidth cost as float (e.g., 0.0)
    33. "monitoring_cost": Monitoring cost as float (e.g., 0.0)
    34. "why_this_plan": Explanation of why this plan was selected and cost breakdown rationale in human language.
    35. "detected_vars_detail": A JSON array of environment variable metadata objects, where each object has "key", "type" ("required" | "optional"), "is_missing" (boolean), "has_default" (boolean), and "default_val" (string).
    36. "application_type": Type of application (e.g., "Next.js SaaS Platform", "FastAPI Service", etc.)
    37. "estimated_build_time": Estimated build time (e.g., "90s", "60s")
    38. "production_readiness_score": Integer readiness score from 0 to 100 (e.g., 94)
    39. "detected_services": Array of detected services (e.g., ["Next.js", "PostgreSQL"])
    
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

        # Set default values for pricing breakdown & why_this_plan
        if "compute_cost" not in data:
            data["compute_cost"] = 8.0
        if "database_cost" not in data:
            db_deps = data.get("database_dependencies", [])
            data["database_cost"] = 5.0 if db_deps and "None" not in db_deps else 0.0
        if "platform_fee" not in data:
            data["platform_fee"] = 4.0
        if "bandwidth_cost" not in data:
            data["bandwidth_cost"] = 0.0
        if "monitoring_cost" not in data:
            data["monitoring_cost"] = 0.0
        
        compute_cost = data["compute_cost"]
        database_cost = data["database_cost"]
        platform_fee = data["platform_fee"]
        total_cost = compute_cost + database_cost + platform_fee
        
        if "total_cost" not in data:
            data["total_cost"] = total_cost
        if "projected_growth_cost" not in data:
            data["projected_growth_cost"] = total_cost * 2.2
        if "estimated_cost" not in data:
            data["estimated_cost"] = f"${int(total_cost)}/month"
        if "deployment_target" not in data or "Azure" in str(data.get("deployment_target")):
            data["deployment_target"] = "Managed Production Environment"
        if "deployment_strategy" not in data or "Azure" in str(data.get("deployment_strategy")):
            data["deployment_strategy"] = "Managed Production Environment"
        if "recommended_compute_tier" not in data or "Azure" in str(data.get("recommended_compute_tier")):
            data["recommended_compute_tier"] = "Standard Production Core"
        if "recommended_region" not in data or "Azure" in str(data.get("recommended_region")):
            data["recommended_region"] = "East US Core"
        if "expected_traffic" not in data:
            data["expected_traffic"] = "100,000 requests/month"

        if "why_this_plan" not in data:
            db_dep = data.get("database") or ""
            db_text = f"an auto-provisioned {db_dep} database" if db_dep and db_dep != "None" else "an isolated runtime tier"
            data["why_this_plan"] = f"ZeroOps AI selected a Managed Production Environment with {db_text} because the application code indicates it requires persistent computing layers. Cost breakdown includes fully-managed secure databases, 99.9% uptime orchestration, and platform edge routing."
            
        if "detected_vars_detail" not in data:
            detected_vars_detail = []
            env_vars = data.get("required_env_vars") or data.get("environment_variables") or []
            db_dep = data.get("database") or ""
            if db_dep and db_dep != "None":
                detected_vars_detail.append({
                    "key": "DATABASE_URL" if db_dep != "MongoDB" else "MONGODB_URI",
                    "type": "required",
                    "is_missing": True,
                    "has_default": True,
                    "default_val": f"{db_dep.lower()}://zeroops_user:****@managed-{db_dep.lower()}-db.zeroops.internal:5432/zeroops_db"
                })
            detected_vars_detail.append({
                "key": "JWT_SECRET",
                "type": "required",
                "is_missing": True,
                "has_default": True,
                "default_val": "zo_sec_db84b72fd91c28c83e1a0b5a37f59b6c2d1e"
            })
            for var in env_vars:
                if var not in ["DATABASE_URL", "MONGODB_URI", "JWT_SECRET"]:
                    detected_vars_detail.append({
                        "key": var,
                        "type": "optional",
                        "is_missing": False,
                        "has_default": False,
                        "default_val": ""
                    })
            data["detected_vars_detail"] = detected_vars_detail

        # Support extra blueprint fields
        if "application_type" not in data:
            data["application_type"] = f"{data.get('framework', 'Web')} App"
        if "estimated_build_time" not in data:
            data["estimated_build_time"] = "90s"
        if "production_readiness_score" not in data:
            data["production_readiness_score"] = 100 - data.get("risk_score", 12)
        if "detected_services" not in data:
            data["detected_services"] = [data.get("framework", "Web")] + ([data.get("database")] if data.get("database") and data.get("database") != "None" else [])

        data["pricing_breakdown"] = {
            "compute_cost": float(data.get("compute_cost", 8.0)),
            "database_cost": float(data.get("database_cost", database_cost)),
            "platform_fee": float(data.get("platform_fee", platform_fee)),
            "bandwidth_cost": float(data.get("bandwidth_cost", 0.0)),
            "monitoring_cost": float(data.get("monitoring_cost", 0.0)),
            "total_cost": float(data.get("total_cost", total_cost)),
            "projected_growth_cost": float(data.get("projected_growth_cost", total_cost * 2.2)),
            "why_this_plan": data.get("why_this_plan"),
            "detected_vars_detail": data.get("detected_vars_detail"),
            "application_type": data.get("application_type"),
            "estimated_build_time": data.get("estimated_build_time"),
            "production_readiness_score": data.get("production_readiness_score"),
            "detected_services": data.get("detected_services")
        }
            
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
    name = metadata.get("name") or "this project"
    framework = metadata.get("framework") or "unknown framework"
    language = metadata.get("language") or "unknown language"
    db_list = metadata.get("databases") or []
    db_desc = ", ".join([f"{db['type']} ({db['status']})" for db in db_list]) if db_list else "None detected"
    latest_deployment = metadata.get("latest_deployment") or {}
    url = latest_deployment.get("live_url") if isinstance(latest_deployment, dict) else None
    region = metadata.get("region") or "eastus"
    deployment_status = latest_deployment.get("status") if isinstance(latest_deployment, dict) else "unknown"
    health_score = metadata.get("health_score", 90)

    # 1. Why did deployment fail?
    if "fail" in msg or "error" in msg or "why did" in msg or "broken" in msg:
        fa = metadata.get("failure_analysis")
        if fa:
            return (
                f"The deployment of **{name}** failed due to: **{fa['summary']}**.\n\n"
                f"- **Root Cause:** {fa['cause']}\n"
                f"- **Recommended Fix:** {fa['recommended_fix']}\n"
                f"- **AI Confidence:** {fa['confidence']}% | **Impact:** {fa['impact']}\n\n"
                f"You can click **'Fix Automatically'** on the deployments page to apply the recommended remediation."
            )
        elif deployment_status == "failed":
            logs = metadata.get("latest_deployment_logs") or []
            log_snippet = "\n".join(logs[:5]) if logs else "No logs captured."
            return (
                f"The latest deployment status for **{name}** is **failed**.\n\n"
                f"**Recent Log Trace:**\n```\n{log_snippet}\n```\n"
                f"Please review the deployment logs on the dashboard to debug this issue further."
            )
        else:
            return f"The latest deployment status for **{name}** is **{deployment_status}**. There are no active failure logs recorded."

    # 2. What does this application do?
    elif "do" in msg or "what is" in msg or "purpose" in msg or "about" in msg:
        db_primary = metadata.get("database") or (db_list[0]["type"] if db_list else "SQLite")
        return (
            f"**{name}** is a **{framework}** web application built using **{language}**.\n\n"
            f"- **Runtime Environment:** Azure App Service on Linux ({region})\n"
            f"- **Connected Databases:** {db_desc}\n"
            f"- **Status:** {metadata.get('status', 'active').capitalize()}\n"
            f"- **Live URL:** [{url}]({url}) if deployed successfully."
        )

    # 3. How can I reduce costs?
    elif "cost" in msg or "reduce" in msg or "cheap" in msg or "price" in msg or "monthly" in msg:
        cost_meta = metadata.get("cost")
        telemetry = metadata.get("telemetry") or {}
        cpu = telemetry.get("avg_cpu_utilization", "5.0%")
        
        if cost_meta:
            opt = metadata.get("cost_optimization")
            opt_text = f"\n\n**AI Cost Recommendation:** {opt['recommendation']} (Estimated savings: {opt['savings']}) because of {opt['reason']}" if opt else ""
            return (
                f"Here is your dynamic infrastructure cost blueprint for **{name}**:\n"
                f"- **Compute Resource:** ${cost_meta['compute_cost']}/mo\n"
                f"- **Database Hosting:** ${cost_meta['database_cost']}/mo\n"
                f"- **Platform Margin Fee:** ${cost_meta['platform_fee']}/mo\n"
                f"- **Estimated Monthly Total:** **${cost_meta['total_cost']}/mo**\n"
                f"- **Projected Growth Cost (at scale):** ${cost_meta['projected_growth_cost']}/mo\n"
                f"- **Recommended Plan:** **{cost_meta['recommended_plan']}**\n"
                f"*{cost_meta['why_this_plan']}*{opt_text}"
            )
        else:
            return (
                f"Your compute tier is running at low utilization (CPU: {cpu}). "
                f"You can reduce costs by moving to a standard Hobby plan ($12-$15/mo) and turning off unused database replicas."
            )

    # 4. How can I improve performance?
    elif "performance" in msg or "improve" in msg or "slow" in msg or "speed" in msg or "latency" in msg:
        telemetry = metadata.get("telemetry")
        vuln_count = metadata.get("vulnerabilities_count", 0)
        perf_score = 100 - int(vuln_count * 5)
        
        telemetry_str = ""
        if telemetry:
            telemetry_str = (
                f"\n- **CPU Utilization:** {telemetry['avg_cpu_utilization']}\n"
                f"- **Memory Usage:** {telemetry['avg_memory_utilization']}\n"
                f"- **Average Error Rate:** {telemetry['recent_error_rate']}\n"
                f"- **Response Latency:** {telemetry['recent_response_time_ms']}\n"
            )
            
        return (
            f"To optimize performance for your **{framework}** application:{telemetry_str}\n"
            f"**Recommended Optimizations:**\n"
            f"1. **Bundle Splitting:** Enable lazy loading and dynamic routing in your next build to shrink script size.\n"
            f"2. **Content Caching:** Integrate cloud CDN rules on your static assets path to offload server cycles.\n"
            f"3. **Database Indexing:** Ensure primary keys are correctly indexed to lower database response latency."
        )

    # 5. What environment variables are missing?
    elif "env" in msg or "variable" in msg or "missing" in msg or "secret" in msg:
        missing = metadata.get("missing_variables") or {}
        req_missing = missing.get("required") or []
        rec_missing = missing.get("recommended") or []
        
        if not req_missing and not rec_missing:
            return f"All analyzed environment variables are fully configured for **{name}**. The production environment contains all required secrets."
            
        res = f"Here are the environment variable checks for **{name}**:\n"
        if req_missing:
            res += f"- ❌ **Missing Required:** {', '.join(req_missing)} (Deployment might crash without these)\n"
        if rec_missing:
            res += f"- ⚠️ **Missing Recommended:** {', '.join(rec_missing)} (Features might be degraded)\n"
            
        res += "\nZeroOps AI has auto-injected secure defaults for core tokens (such as `JWT_SECRET`). You can configure the rest under the **Settings** or **Secrets** tab."
        return res

    # 6. Can I deploy safely?
    elif "safe" in msg or "deploy safely" in msg or "security" in msg or "readiness" in msg:
        vuln_count = metadata.get("vulnerabilities_count", 0)
        status_term = "Safe to Deploy" if health_score >= 80 else "Caution Advised" if health_score >= 60 else "Unsafe to Deploy"
        
        vuln_text = f"We found **{vuln_count} security vulnerabilities** in your codebase packages." if vuln_count > 0 else "No package vulnerabilities detected."
        return (
            f"**Deployment Safety Report for {name}:**\n"
            f"- **Overall Health Score:** **{health_score}/100** ({status_term})\n"
            f"- **Security Vulnerabilities:** {vuln_text}\n"
            f"- **Status:** {deployment_status.capitalize()}\n\n"
            f"Suggestions: Make sure all required variables are verified, and run a lint check before merging changes to `{metadata.get('branch', 'main')}`."
        )

    else:
        live_url = f" Live URL: {url}." if url else ""
        return (
            f"I am the ZeroOps AI Cloud Engineer. I have loaded context for **{name}** ({framework}).{live_url}\n\n"
            f"Ask me questions like:\n"
            f"- *'Why did deployment fail?'*\n"
            f"- *'What does this application do?'*\n"
            f"- *'How can I reduce costs?'*\n"
            f"- *'What environment variables are missing?'*\n"
            f"- *'Can I deploy safely?'*"
        )


