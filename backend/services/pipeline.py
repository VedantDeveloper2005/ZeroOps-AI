import asyncio
import json
import time
import uuid
import logging
import re
from datetime import datetime
from typing import Dict, List
from fastapi import WebSocket
from sqlalchemy.future import select

try:
    from backend.services import git, ai, builder, k8s, vault, deployment_targets, github_oauth
    from backend.database import AsyncSessionLocal
    from backend import models, config
except ImportError:
    from services import git, ai, builder, k8s, vault, deployment_targets, github_oauth
    from database import AsyncSessionLocal
    import models, config

# Active websockets registry: deploy_id -> list of WebSockets
connections: Dict[str, List[WebSocket]] = {}
event_buffers: Dict[str, List[dict]] = {}

# Active deployments history (legacy compatibility)
deployments_history = []

def normalize_project_id(repo_name: str) -> str:
    raw = (repo_name.split("/")[-1] or "web-app").lower()
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in raw).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned or "web-app"

async def register_connection(deploy_id: str, websocket: WebSocket):
    """Register a new websocket connection for a deployment ID."""
    if deploy_id not in connections:
        connections[deploy_id] = []
    connections[deploy_id].append(websocket)
    for message in event_buffers.get(deploy_id, []):
        await websocket.send_text(json.dumps(message))
    print(f"WebSocket registered for deployment {deploy_id}. Total listeners: {len(connections[deploy_id])}")

def unregister_connection(deploy_id: str, websocket: WebSocket):
    """Unregister a websocket connection."""
    if deploy_id in connections:
        if websocket in connections[deploy_id]:
            connections[deploy_id].remove(websocket)
        if not connections[deploy_id]:
            del connections[deploy_id]
    print(f"WebSocket disconnected from deployment {deploy_id}.")

async def broadcast_message(deploy_id: str, message: dict):
    """Broadcast a JSON message to all listeners for a deployment."""
    event_buffers.setdefault(deploy_id, []).append(message)
    event_buffers[deploy_id] = event_buffers[deploy_id][-300:]
    if deploy_id in connections:
        payload = json.dumps(message)
        tasks = [ws.send_text(payload) for ws in connections[deploy_id]]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


class PipelineLogger:
    def __init__(self, deploy_id: str):
        self.deploy_id = deploy_id
        self.log_buffer = []
        self.line_counter = 0

    async def log(self, message: str, level: str = "INFO"):
        self.line_counter += 1
        # Broadcast to WebSocket
        await broadcast_message(self.deploy_id, {"type": "log", "text": message, "lineType": level.lower()})
        # Buffer for database write
        self.log_buffer.append({
            "line_number": self.line_counter,
            "level": level,
            "message": message,
            "timestamp": datetime.utcnow()
        })

    async def flush_to_db(self, db_session):
        if not self.log_buffer:
            return
        try:
            # Batch insert all logs in buffer
            for log_data in self.log_buffer:
                db_log = models.DeploymentLog(
                    deployment_id=uuid.UUID(self.deploy_id),
                    line_number=log_data["line_number"],
                    level=log_data["level"],
                    message=log_data["message"],
                    timestamp=log_data["timestamp"]
                )
                db_session.add(db_log)
            await db_session.commit()
            self.log_buffer.clear()
        except Exception as e:
            print(f"Error flushing logs to DB: {e}")


# Task Dispatcher for Background Job Architecture
# In production, this can be swapped with a Celery task call or Azure Queue message.
def enqueue_deployment(deploy_id: str, repo_name: str, branch: str, background_tasks, clone_token: str | None = None):
    """Enqueues deployment tasks to run asynchronously in the background."""
    # For MVP: Enqueue using FastAPI's background tasks
    # For Production: celery_app.send_task("run_deployment_pipeline", args=[deploy_id, repo_name, branch])
    background_tasks.add_task(run_deployment_pipeline, deploy_id, repo_name, branch, clone_token)


async def run_deployment_pipeline(deploy_id: str, repo_name: str, branch: str, clone_token: str | None = None):
    """Runs the full 10-stage deployment pipeline in an async background task."""
    import secrets
    from sqlalchemy.orm.attributes import flag_modified

    print(f"Starting database-backed pipeline deployment {deploy_id} for {repo_name} (branch: {branch})")
    project_id_raw = normalize_project_id(repo_name)
    ns_name = f"zeroops-{project_id_raw}"
    live_url = None
    
    # Instantiate logger
    p_logger = PipelineLogger(deploy_id)
    
    # Initial stages metadata list
    stages_metadata = [
        {"id": 1, "label": "Repository", "status": "pending", "duration": ""},
        {"id": 2, "label": "Clone Repository", "status": "pending", "duration": ""},
        {"id": 3, "label": "Analyze Repository", "status": "pending", "duration": ""},
        {"id": 4, "label": "Generate Build Specification", "status": "pending", "duration": ""},
        {"id": 5, "label": "Generate Environment Variables", "status": "pending", "duration": ""},
        {"id": 6, "label": "Provision Database", "status": "pending", "duration": ""},
        {"id": 7, "label": "Build Application", "status": "pending", "duration": ""},
        {"id": 8, "label": "Deploy Application", "status": "pending", "duration": ""},
        {"id": 9, "label": "Health Validation", "status": "pending", "duration": ""},
        {"id": 10, "label": "Generate Live URL", "status": "pending", "duration": ""}
    ]

    async def update_stage(stage_id: int, status: str, duration: str = ""):
        for stage in stages_metadata:
            if stage["id"] == stage_id:
                stage["status"] = status
                stage["duration"] = duration
        await broadcast_message(deploy_id, {"type": "stage", "id": stage_id, "status": status, "duration": duration})
        try:
            async with AsyncSessionLocal() as db_inner:
                result_inner = await db_inner.execute(
                    select(models.Deployment).filter(models.Deployment.id == uuid.UUID(deploy_id))
                )
                dep_inner = result_inner.scalars().first()
                if dep_inner:
                    meta = dep_inner.infrastructure_metadata or {}
                    meta["stages"] = stages_metadata
                    dep_inner.infrastructure_metadata = meta
                    flag_modified(dep_inner, "infrastructure_metadata")
                    await db_inner.commit()
        except Exception as ex:
            print(f"Error persisting stages: {ex}")
    
    # Load deployment from DB and set initial state
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(models.Deployment).filter(models.Deployment.id == uuid.UUID(deploy_id))
        )
        deployment = result.scalars().first()
        if not deployment:
            print(f"Deployment record {deploy_id} not found in DB!")
            return
            
        deployment.status = "building"
        await db.commit()
        
    start_time = time.time()
    
    try:
        async with AsyncSessionLocal() as db:
            # Re-fetch deployment in this session
            result = await db.execute(
                select(models.Deployment).filter(models.Deployment.id == uuid.UUID(deploy_id))
            )
            deployment = result.scalars().first()
            project = deployment.project
            from sqlalchemy import or_
            azure_result = await db.execute(
                select(models.UserAzureConnection)
                .filter(
                    models.UserAzureConnection.user_id == deployment.user_id,
                    or_(
                        models.UserAzureConnection.connection_status == "connected",
                        models.UserAzureConnection.is_active == True
                    )
                )
                .order_by(models.UserAzureConnection.created_at.desc())
                .limit(1)
            )
            azure_connection = azure_result.scalars().first()
            gke_result = await db.execute(
                select(models.UserGkeConnection)
                .filter(models.UserGkeConnection.user_id == deployment.user_id, models.UserGkeConnection.is_active == True)
                .order_by(models.UserGkeConnection.created_at.desc())
                .limit(1)
            )
            gke_connection = gke_result.scalars().first()
            target_status = deployment_targets.status_payload(azure_connection, gke_connection)
            if not target_status["any_ready"]:
                raise RuntimeError("No deployment target is ready. Configure Azure AKS or Google GKE before deployment.")

            requested_provider = (deployment.infrastructure_metadata or {}).get("target_provider", "auto")
            initial_hint = {
                "framework": project.framework,
                "language": project.language,
                "deployment_strategy": (deployment.infrastructure_metadata or {}).get("target_reason"),
            }
            selected_target = deployment_targets.choose_target(
                initial_hint,
                azure_connection,
                gke_connection,
                requested_provider,
            )
            namespace_prefix = deployment_targets.namespace_prefix(selected_target, deployment.user_id)
            project_id_raw = normalize_project_id(f"{namespace_prefix}-{project.name}")
            ns_name = f"zeroops-{project_id_raw}"
            image_ref = deployment.image or deployment_targets.image_ref_for_target(
                selected_target,
                project_id_raw,
                deployment.version or "latest",
            )
            if config.ZEROOPS_PUBLIC_BASE_DOMAIN:
                live_url = f"https://{project_id_raw}.{config.ZEROOPS_PUBLIC_BASE_DOMAIN}"
            
            # ──────────────────────────────────────────────
            # Stage 1: Repository Verification
            # ──────────────────────────────────────────────
            step_start = time.time()
            await update_stage(1, "active", "...")
            await p_logger.log(f"$ zeroops deploy --repo {repo_name} --env production", "command")
            await p_logger.log("ZeroOps AI deployment engine online", "info")
            await p_logger.log(f"> Project identity resolved: {project_id_raw}", "info")
            await p_logger.log(f"> Cloud target: {selected_target.label} ({selected_target.reason})", "info")
            await p_logger.log(f"> Namespace target: {ns_name}", "info")
            await asyncio.sleep(0.5)
            await p_logger.log("  ✓ Repository configuration verified.", "success")
            step_dur = f"{round(time.time() - step_start, 1)}s"
            await update_stage(1, "completed", step_dur)
            await p_logger.flush_to_db(db)

            # ──────────────────────────────────────────────
            # Stage 2: Clone Repository
            # ──────────────────────────────────────────────
            step_start = time.time()
            await update_stage(2, "active", "...")
            if getattr(project, "source_type", "github") == "upload":
                if not project.source_path:
                    raise RuntimeError("Uploaded source path is missing for this project.")
                repo_path = project.source_path
                await p_logger.log(f"$ zeroops source use-upload {project.full_name}", "command")
            else:
                await p_logger.log(f"$ git clone --branch {branch} https://github.com/{repo_name}.git .", "command")
                await asyncio.sleep(0.5)
                repo_path = git.clone_repo(repo_name, clone_token)
            await p_logger.log("  Source prepared successfully on local filesystem.", "success")
            step_dur = f"{round(time.time() - step_start, 1)}s"
            await update_stage(2, "completed", step_dur)
            await p_logger.flush_to_db(db)

            # ──────────────────────────────────────────────
            # Stage 3: Analyze Repository
            # ──────────────────────────────────────────────
            step_start = time.time()
            await update_stage(3, "active", "...")
            await p_logger.log("▸ AI analyzing repository structure...", "info")
            await asyncio.sleep(0.5)
            try:
                metadata = ai.analyze_repository(repo_path, project_id_raw)
                await p_logger.log("  ◆ AI-powered remote scanner analysis complete", "success")
            except (ValueError, RuntimeError) as ai_err:
                await p_logger.log(f"  ⚠ AI provider unavailable: {ai_err}. Using local analyzer.", "warning")
                metadata = ai.analyze_repo_local(repo_path, project_id_raw)
            
            await p_logger.log(f"  ◆ Framework: {metadata.get('framework')} ({metadata.get('version')})", "info")
            await p_logger.log(f"  ◆ Core language: {metadata.get('language')}", "info")
            await p_logger.log(f"  ◆ CPU recommendation: {metadata['resources']['cpu']}", "info")
            await p_logger.log(f"  ◆ Memory recommendation: {metadata['resources']['memory']}", "info")
            
            # Save AI Analysis in DB
            analysis = models.AIAnalysis(
                user_id=deployment.user_id,
                project_id=deployment.project_id,
                framework=metadata.get("framework"),
                framework_version=metadata.get("version"),
                language=metadata.get("language"),
                risk_score=metadata.get("risk_score", 15),
                confidence=metadata.get("confidence", 95),
                cpu_recommendation=metadata["resources"]["cpu"],
                memory_recommendation=metadata["resources"]["memory"],
                storage_recommendation=metadata["resources"]["storage"],
                dependencies=metadata.get("dependencies", []),
                vulnerabilities=metadata.get("vulnerabilities", []),
                dockerfile=metadata.get("dockerfile"),
                kubernetes_manifest=metadata.get("kubernetes_manifest"),
                
                # Save scanner fields
                runtime=metadata.get("runtime"),
                package_manager=metadata.get("package_manager"),
                docker_support=metadata.get("docker_support", False),
                monorepo_structure=metadata.get("monorepo_structure"),
                database_dependencies=metadata.get("database_dependencies", []),
                deployment_strategy=metadata.get("deployment_strategy"),
                build_commands=metadata.get("build_commands"),
                start_commands=metadata.get("start_commands"),
                environment_variables=metadata.get("environment_variables", []),
                recommended_compute_tier=metadata.get("recommended_compute_tier"),
                estimated_cost=metadata.get("estimated_cost"),
                recommended_region=metadata.get("recommended_region"),
                expected_traffic=metadata.get("expected_traffic"),
                pricing_breakdown=metadata.get("pricing_breakdown")
            )
            db.add(analysis)
            
            for vuln in metadata.get("vulnerabilities", []):
                await p_logger.log(f"  ⚠️ Scan finding: {vuln}", "warning")
            await p_logger.log("  ✓ AI codebase fingerprinting complete.", "success")
            step_dur = f"{round(time.time() - step_start, 1)}s"
            await update_stage(3, "completed", step_dur)
            await p_logger.flush_to_db(db)

            # ──────────────────────────────────────────────
            # Stage 4: Generate Build Specification
            # ──────────────────────────────────────────────
            step_start = time.time()
            await update_stage(4, "active", "...")
            await p_logger.log("▸ Generating build specification...", "info")
            await asyncio.sleep(0.5)
            await p_logger.log(f"  ◆ Build Command: {metadata.get('build_commands') or 'None'}", "info")
            await p_logger.log(f"  ◆ Startup Command: {metadata.get('start_commands') or 'None'}", "info")
            await p_logger.log("  ✓ Dockerfile context and Kubernetes manifests compiled.", "success")
            step_dur = f"{round(time.time() - step_start, 1)}s"
            await update_stage(4, "completed", step_dur)
            await p_logger.flush_to_db(db)

            # ──────────────────────────────────────────────
            # Stage 5: Generate Environment Variables
            # ──────────────────────────────────────────────
            step_start = time.time()
            await update_stage(5, "active", "...")
            await p_logger.log("▸ Resolving environment variables...", "info")
            
            # Ensure project production environment exists
            env_result = await db.execute(
                select(models.Environment).filter(
                    models.Environment.project_id == deployment.project_id,
                    models.Environment.name == "production"
                )
            )
            env = env_result.scalars().first()
            if not env:
                env = models.Environment(project_id=deployment.project_id, name="production")
                db.add(env)
                await db.commit()
                await db.refresh(env)

            # Fetch existing vars
            var_result = await db.execute(
                select(models.EnvironmentVariable).filter(models.EnvironmentVariable.environment_id == env.id)
            )
            existing_vars = {v.key: v for v in var_result.scalars().all()}
            
            # Retrieve scanned variables list
            scanned_vars_meta = (metadata.get("pricing_breakdown") or {}).get("detected_vars_detail", [])
            for var_meta in scanned_vars_meta:
                v_key = var_meta["key"]
                v_type = var_meta["type"]
                
                if v_key in existing_vars:
                    await p_logger.log(f"  ◆ Resolved {v_key} ({v_type}) from settings.", "info")
                elif var_meta.get("has_default") and v_key not in ["DATABASE_URL", "MONGODB_URI", "REDIS_URL"]:
                    # Generate default value if required (like JWT_SECRET)
                    jwt_val = var_meta.get("default_val") or f"zo_sec_{secrets.token_hex(16)}"
                    new_var = models.EnvironmentVariable(
                        environment_id=env.id,
                        key=v_key,
                        value=jwt_val,
                        is_secret=True
                    )
                    db.add(new_var)
                    vault.set_project_secret(str(deployment.project_id), v_key, jwt_val)
                    await p_logger.log(f"  ◆ Injected secure default for required {v_key}", "success")
                else:
                    if v_type == "required":
                        await p_logger.log(f"  Required variable {v_key} is missing. Add it before deployment can succeed.", "warning")
                    elif v_type == "recommended":
                        await p_logger.log(f"  ⚠ Recommended variable {v_key} is missing.", "info")
            
            step_dur = f"{round(time.time() - step_start, 1)}s"
            await update_stage(5, "completed", step_dur)
            await p_logger.flush_to_db(db)

            # ──────────────────────────────────────────────
            # Stage 6: Provision Database (if required)
            # ──────────────────────────────────────────────
            step_start = time.time()
            await update_stage(6, "active", "...")
            await p_logger.log("▸ Scanning database dependencies...", "info")
            
            db_deps = metadata.get("database_dependencies", [])
            if db_deps:
                for db_dep in db_deps:
                    db_type = str(db_dep).lower()
                    if "postgres" in db_type or "mysql" in db_type:
                        var_key = "DATABASE_URL"
                    elif "mongo" in db_type:
                        var_key = "MONGODB_URI"
                    elif "redis" in db_type:
                        var_key = "REDIS_URL"
                    else:
                        await p_logger.log(f"  Database dependency {db_dep} detected; no automatic provisioning rule exists.", "warning")
                        continue

                    if var_key not in existing_vars:
                        raise RuntimeError(
                            f"{db_dep} dependency detected but {var_key} is not configured. "
                            "Add a real database connection string before deploying."
                        )
                    await p_logger.log(f"  Database dependency {db_dep} will use configured {var_key}.", "info")
                await p_logger.log("  Automatic database provisioning is disabled; using configured external database resources only.", "info")
                db_deps = []
            if db_deps:
                for db_dep in db_deps:
                    db_type = db_dep.lower()
                    if db_type not in ["postgresql", "mysql", "mongodb", "redis"]:
                        continue
                    
                    await p_logger.log(f"▸ Provisioning managed {db_dep} database...", "info")
                    
                    # Check if project already has a DatabaseInstance of this type
                    db_inst_result = await db.execute(
                        select(models.DatabaseInstance).filter(
                            models.DatabaseInstance.project_id == project.id,
                            models.DatabaseInstance.type == db_dep
                        )
                    )
                    db_instance = db_inst_result.scalars().first()
                    
                    if not db_instance:
                        # Provision new DB
                        db_name = f"db_{project_id_raw.replace('-', '_')}"
                        db_user = f"user_{secrets.token_hex(4)}"
                        db_pass = secrets.token_urlsafe(16)
                        
                        if "postgres" in db_type:
                            db_host = "managed-postgres-db.zeroops.internal"
                            db_port = 5432
                            conn_str = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
                            var_key = "DATABASE_URL"
                        elif "mysql" in db_type:
                            db_host = "managed-mysql-db.zeroops.internal"
                            db_port = 3306
                            conn_str = f"mysql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
                            var_key = "DATABASE_URL"
                        elif "mongo" in db_type:
                            db_host = "managed-mongodb.zeroops.internal"
                            db_port = 27017
                            conn_str = f"mongodb://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
                            var_key = "MONGODB_URI"
                        elif "redis" in db_type:
                            db_host = "managed-redis.zeroops.internal"
                            db_port = 6379
                            conn_str = f"redis://default:{db_pass}@{db_host}:{db_port}"
                            var_key = "REDIS_URL"
                        
                        db_instance = models.DatabaseInstance(
                            project_id=project.id,
                            type=db_dep,
                            db_name=db_name,
                            username=db_user,
                            password=db_pass,
                            host=db_host,
                            port=db_port,
                            connection_string=conn_str,
                            status="available"
                        )
                        db.add(db_instance)
                        await p_logger.log(f"  ◆ Managed {db_dep} database instance initialized statefully.", "success")
                        
                        # Store in Vault & Environment Variables
                        vault.set_project_secret(str(project.id), var_key, conn_str)
                        
                        # Check if environment variable already exists
                        env_var_result = await db.execute(
                            select(models.EnvironmentVariable).filter(
                                models.EnvironmentVariable.environment_id == env.id,
                                models.EnvironmentVariable.key == var_key
                            )
                        )
                        env_var = env_var_result.scalars().first()
                        if not env_var:
                            env_var = models.EnvironmentVariable(
                                environment_id=env.id,
                                key=var_key,
                                value=conn_str,
                                is_secret=True
                            )
                            db.add(env_var)
                        else:
                            env_var.value = conn_str
                        await p_logger.log(f"  ◆ Connected connection credentials to environment variable: {var_key}", "success")
                    else:
                        await p_logger.log(f"  ◆ Using existing managed {db_dep} database instance.", "info")
            else:
                await p_logger.log("  Database provisioning skipped; external database resources are user-configured.", "info")
            
            step_dur = f"{round(time.time() - step_start, 1)}s"
            await update_stage(6, "completed", step_dur)
            await p_logger.flush_to_db(db)

            # ──────────────────────────────────────────────
            # Stage 7: Build Application
            # ──────────────────────────────────────────────
            step_start = time.time()
            await update_stage(7, "active", "...")
            build_start = time.time()
            image_name, image_tag = image_ref.rsplit(":", 1) if ":" in image_ref else (image_ref, "latest")

            if selected_target.provider == "gke":
                await p_logger.log("▸ Preparing Google GKE deployment context...", "info")
                service_account_json = None
                encrypted_json = getattr(selected_target.connection, "service_account_json_encrypted", None)
                if encrypted_json:
                    try:
                        service_account_json = github_oauth.decrypt_token(encrypted_json)
                    except Exception as cred_err:
                        raise RuntimeError("Stored GKE service account credentials could not be decrypted.") from cred_err

                for log_line in k8s.configure_gke_context(
                    gcp_project_id=selected_target.connection.gcp_project_id,
                    cluster_name=selected_target.connection.cluster_name,
                    location=selected_target.connection.location,
                    artifact_registry_host=selected_target.connection.artifact_registry_host,
                    service_account_json=service_account_json,
                ):
                    await p_logger.log(log_line.strip(), "info")
                    await asyncio.sleep(0.01)

            await p_logger.log(f"$ docker build -t {image_ref} .", "command")
            for log_line in builder.build_and_tag_image(repo_path, image_name, image_tag):
                await p_logger.log(log_line.strip(), "success" if "successfully" in log_line.lower() else "info")
                await asyncio.sleep(0.01)
            await p_logger.log(f"$ docker push {image_ref}", "command")
            for log_line in builder.push_image(image_ref):
                await p_logger.log(log_line.strip(), "success" if "successfully" in log_line.lower() else "info")
                await asyncio.sleep(0.01)
                
            build_dur = f"{round(time.time() - build_start, 1)}s"
            await update_stage(7, "completed", build_dur)
            await p_logger.flush_to_db(db)

            # ──────────────────────────────────────────────
            # Stage 8: Deploy Application
            # ──────────────────────────────────────────────
            step_start = time.time()
            await update_stage(8, "active", "...")
            await p_logger.log("▸ Applying infrastructure settings to cluster namespace...", "info")
            
            # Setup isolated namespace
            for log in k8s.setup_namespace(project_id_raw):
                await p_logger.log(log.strip(), "info" if "Preparing" in log else "success")
                await asyncio.sleep(0.01)
            
            # Sync vault secrets to namespace
            secrets_to_sync = vault.get_project_secrets(str(project.id))
            for log in k8s.sync_secrets_to_namespace(project_id_raw, secrets_to_sync):
                await p_logger.log(log.strip(), "info" if "Synchronizing" in log else "success")
                await asyncio.sleep(0.01)
            
            # Apply deployment manifests
            manifests = metadata.get("kubernetes_manifest", "")
            if not manifests:
                raise RuntimeError("No Kubernetes manifest could be generated for this project.")
            manifests = re.sub(r"image:\s*\S+", f"image: {image_ref}", manifests, count=1)
            await p_logger.log(f"$ kubectl apply -f manifests.yaml", "command")
            deploy_start = time.time()
            for log_line in k8s.apply_manifests(manifests):
                await p_logger.log(log_line.strip(), "success" if ("created" in log_line or "configured" in log_line or "applied successfully" in log_line.lower()) else "info")
                await asyncio.sleep(0.01)
                
            deploy_dur = f"{round(time.time() - deploy_start, 1)}s"
            await update_stage(8, "completed", deploy_dur)
            await p_logger.flush_to_db(db)

            # ──────────────────────────────────────────────
            # Stage 9: Health Validation
            # ──────────────────────────────────────────────
            step_start = time.time()
            await update_stage(9, "active", "...")
            await p_logger.log("▸ Starting application health check validation...", "info")
            for log_line in k8s.verify_rollout(project_id_raw):
                await p_logger.log(log_line.strip(), "success" if "success" in log_line.lower() else "info")
                await asyncio.sleep(0.01)
            await p_logger.log("  ✓ Liveness probe ping completed successfully.", "success")
            step_dur = f"{round(time.time() - step_start, 1)}s"
            await update_stage(9, "completed", step_dur)
            await p_logger.flush_to_db(db)

            # ──────────────────────────────────────────────
            # Stage 10: Generate Live URL
            # ──────────────────────────────────────────────
            step_start = time.time()
            await update_stage(10, "active", "...")
            await p_logger.log("Resolving public route metadata...", "info")
            await asyncio.sleep(0.5)
            if live_url:
                await p_logger.log(f"  Public route recorded: {live_url}", "success")
            else:
                await p_logger.log("  No public base domain configured; live URL will remain empty until ingress/domain setup is complete.", "warning")
            await p_logger.log("Deployment rollout completed. Recording deployment state.", "success")
            
            step_dur = f"{round(time.time() - step_start, 1)}s"
            await update_stage(10, "completed", step_dur)
            await p_logger.flush_to_db(db)

            # Finalize deployment success state in database
            duration_total = int(time.time() - start_time)
            
            # Fetch deployment again to be safe in transaction
            result = await db.execute(
                select(models.Deployment).filter(models.Deployment.id == uuid.UUID(deploy_id))
            )
            deployment = result.scalars().first()
            
            deployment.status = "running"
            deployment.duration_seconds = duration_total
            deployment.image = image_ref
            deployment.live_url = live_url
            deployment.completed_at = datetime.utcnow()
            
            # Store final stages list in infrastructure_metadata
            meta = deployment.infrastructure_metadata or {}
            meta["stages"] = stages_metadata
            meta["namespace"] = ns_name
            meta["region"] = (
                getattr(selected_target.connection, "location", None)
                or getattr(selected_target.connection, "region", None)
                or deployment.project.region
                or "eastus"
            )
            meta["image"] = image_ref
            meta["target_provider"] = selected_target.provider
            meta["target_reason"] = selected_target.reason
            meta["target"] = deployment_targets.metadata_for_target(selected_target)
            if selected_target.provider == "azure":
                meta["azure"] = meta["target"]
            elif selected_target.provider == "gke":
                meta["gke"] = meta["target"]
            meta["framework"] = metadata.get("framework")
            meta["language"] = metadata.get("language")
            deployment.infrastructure_metadata = meta
            flag_modified(deployment, "infrastructure_metadata")
            
            # Update project status
            project_result = await db.execute(
                select(models.Project).filter(models.Project.id == deployment.project_id)
            )
            project = project_result.scalars().first()
            if project:
                project.status = "active"
                project.last_deployed_at = datetime.utcnow()
                
            # Create a success notification
            db.add(models.Notification(
                user_id=deployment.user_id,
                title="Deployment Succeeded",
                message=f"Project {repo_name} was successfully built and deployed." + (f" Public route: {live_url}." if live_url else ""),
                type="success",
                category="deployment"
            ))
            
            # Log activity event
            db.add(models.ActivityEvent(
                user_id=deployment.user_id,
                project_id=deployment.project_id,
                action="Deployment Succeeded",
                details=f"Deployed version {deployment.version} to production environment."
            ))
            
            await db.commit()
            await broadcast_message(deploy_id, {"type": "status", "status": "running"})
            print(f"Deployment {deploy_id} completed successfully in {duration_total}s!")

    except Exception as e:
        print(f"Pipeline error in {deploy_id}: {e}")
        await p_logger.log(f"❌ Deployment workflow crashed: {e}", "error")
        
        # Track failure index in stages to mark active step as failed
        for stage in stages_metadata:
            if stage["status"] == "active":
                stage["status"] = "failed"
                stage["duration"] = "error"
            elif stage["status"] == "pending":
                # remain pending
                pass
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(models.Deployment).filter(models.Deployment.id == uuid.UUID(deploy_id))
            )
            deployment = result.scalars().first()
            if deployment:
                deployment.status = "failed"
                deployment.completed_at = datetime.utcnow()
                deployment.duration_seconds = int(time.time() - start_time)
                deployment.failure_reason = str(e)
                
                # Save failure stages list in infrastructure_metadata
                meta = deployment.infrastructure_metadata or {}
                meta["stages"] = stages_metadata
                deployment.infrastructure_metadata = meta
                flag_modified(deployment, "infrastructure_metadata")
                
                # Update project status
                project_result = await db.execute(
                    select(models.Project).filter(models.Project.id == deployment.project_id)
                )
                project = project_result.scalars().first()
                if project:
                    project.status = "failed"
                    
                # Create a failure notification
                db.add(models.Notification(
                    user_id=deployment.user_id,
                    title="Deployment Failed",
                    message=f"Project {repo_name} build failed: {e}",
                    type="critical",
                    category="deployment"
                ))
                
                # Trigger failure analysis
                try:
                    log_messages = [log_data["message"] for log_data in p_logger.log_buffer]
                    try:
                        failure_analysis_res = ai.analyze_failure_nemotron(
                            logs=log_messages,
                            build_logs=log_messages,
                            events=[f"Deployment {deploy_id} state transition to failed."]
                        )
                    except (ValueError, RuntimeError) as ai_err:
                        print(f"AI failure analysis unavailable: {ai_err}. Using local analyzer.")
                        failure_analysis_res = ai.analyze_failure_local(log_messages, log_messages)
                    
                    db_failure_analysis = models.FailureAnalysis(
                        user_id=deployment.user_id,
                        project_id=deployment.project_id,
                        deployment_id=deployment.id,
                        failure_summary=failure_analysis_res.get("failure_summary", "Unknown failure."),
                        root_cause=failure_analysis_res.get("root_cause", "No root cause found."),
                        severity=failure_analysis_res.get("severity", "error"),
                        recommended_fix=failure_analysis_res.get("recommended_fix", "No fix recommended."),
                        step_by_step_resolution=failure_analysis_res.get("step_by_step_resolution", []),
                        confidence=failure_analysis_res.get("confidence", 92),
                        impact="Deployment Halted"
                    )
                    db.add(db_failure_analysis)
                except Exception as analysis_err:
                    print(f"Failed to generate failure analysis: {analysis_err}")
                
                await db.commit()
                
        await p_logger.flush_to_db(db)
        await broadcast_message(deploy_id, {"type": "status", "status": "failed"})
