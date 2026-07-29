import asyncio
import json
import time
import uuid
import logging
from datetime import datetime
from typing import Callable, Dict, List
from fastapi import WebSocket
from sqlalchemy.future import select

try:
    from backend.services import ai, app_service, azure_connector, deployment_targets, git, vault
    from backend.database import AsyncSessionLocal
    from backend import models
except ImportError:
    from services import ai, app_service, azure_connector, deployment_targets, git, vault
    from database import AsyncSessionLocal
    import models

# Active websockets registry: deploy_id -> list of WebSockets
# Kept for compatibility with same-process callers. The production WebSocket
# route uses the database-backed stream below so worker processes do not depend
# on this process-local registry.
connections: Dict[str, List[WebSocket]] = {}

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
    """Broadcast a transient message to same-process listeners, if any."""
    if deploy_id in connections:
        payload = json.dumps(message)
        tasks = [ws.send_text(payload) for ws in connections[deploy_id]]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


def _snapshot_events(
    deployment,
    logs,
    seen_log_ids: set[str],
    stage_states: dict[str, tuple],
    last_status: str | None,
) -> tuple[list[dict], str | None]:
    """Convert authoritative database state into de-duplicated stream events."""
    events: list[dict] = []
    for log_entry in logs:
        log_id = str(log_entry.id)
        if log_id in seen_log_ids:
            continue
        seen_log_ids.add(log_id)
        events.append({
            "type": "log",
            "text": log_entry.message,
            "lineType": str(log_entry.level or "info").lower(),
            "line_number": log_entry.line_number,
            "timestamp": log_entry.timestamp.isoformat() if log_entry.timestamp else None,
        })

    metadata = deployment.infrastructure_metadata or {}
    stages = metadata.get("stages") if isinstance(metadata, dict) else []
    if isinstance(stages, list):
        for stage in stages:
            if not isinstance(stage, dict) or stage.get("id") is None:
                continue
            stage_key = str(stage["id"])
            signature = (
                stage.get("label"),
                stage.get("status") or "pending",
                stage.get("duration") or "",
            )
            if stage_states.get(stage_key) == signature:
                continue
            stage_states[stage_key] = signature
            events.append({
                "type": "stage",
                "id": stage["id"],
                "label": stage.get("label"),
                "status": signature[1],
                "duration": signature[2],
            })

    current_status = deployment.status
    if current_status != last_status:
        events.append({
            "type": "status",
            "status": current_status,
            "live_url": deployment.live_url,
            "failure_reason": deployment.failure_reason if current_status == "failed" else None,
        })
    return events, current_status


async def stream_deployment_updates(
    deploy_id: str,
    websocket: WebSocket,
    *,
    poll_interval: float = 0.75,
) -> None:
    """Stream deployment progress from the shared database.

    The API and deployment worker can run in separate processes or instances.
    Database polling makes logs, stage transitions, and terminal state visible
    regardless of which process executed the pipeline.
    """
    deployment_id = uuid.UUID(deploy_id)
    seen_log_ids: set[str] = set()
    stage_states: dict[str, tuple] = {}
    last_status: str | None = None
    last_log_line = 0
    page_size = 500
    terminal_statuses = {"running", "failed", "stopped", "rolled_back"}

    while True:
        async with AsyncSessionLocal() as db:
            deployment_result = await db.execute(
                select(models.Deployment).filter(models.Deployment.id == deployment_id)
            )
            deployment = deployment_result.scalars().first()
            if deployment is None:
                await websocket.send_text(json.dumps({
                    "type": "status",
                    "status": "unavailable",
                }))
                return

            logs_result = await db.execute(
                select(models.DeploymentLog)
                .filter(
                    models.DeploymentLog.deployment_id == deployment_id,
                    models.DeploymentLog.line_number > last_log_line,
                )
                .order_by(
                    models.DeploymentLog.line_number.asc(),
                    models.DeploymentLog.timestamp.asc(),
                )
                .limit(page_size)
            )
            logs = logs_result.scalars().all()

        events, last_status = _snapshot_events(
            deployment,
            logs,
            seen_log_ids,
            stage_states,
            last_status,
        )
        for event in events:
            await websocket.send_text(json.dumps(event))

        if logs:
            last_log_line = max(last_log_line, max(log.line_number for log in logs))

        # A deployment status is terminal only after the final page of stored
        # logs has been delivered. Closing here prevents a completed release
        # from leaving a database-polling socket open forever.
        if deployment.status in terminal_statuses and len(logs) < page_size:
            return
        if len(logs) == page_size:
            continue
        await asyncio.sleep(poll_interval)


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


async def run_deployment_pipeline(
    deploy_id: str,
    repo_name: str,
    branch: str,
    clone_token: str | None = None,
    *,
    commit_sha: str | None = None,
    lease_guard: Callable[[], bool] | None = None,
):
    """Run one immutable release while its queue lease remains current."""
    import secrets
    from sqlalchemy.orm.attributes import flag_modified

    print(f"Starting database-backed pipeline deployment {deploy_id} for {repo_name} (branch: {branch})")
    project_id_raw = normalize_project_id(repo_name)
    live_url = None
    release = None
    workspace_path: str | None = None
    
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

    def require_current_lease() -> None:
        if lease_guard is not None and not lease_guard():
            raise RuntimeError(
                "The deployment worker lost its queue lease; release processing stopped."
            )

    async def update_stage(stage_id: int, status: str, duration: str = ""):
        require_current_lease()
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
    
    # The worker crosses the release side-effect boundary by changing the
    # deployment to building under its lease. Never revive a reconciled failure.
    require_current_lease()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(models.Deployment).filter(models.Deployment.id == uuid.UUID(deploy_id))
        )
        deployment = result.scalars().first()
        if not deployment:
            print(f"Deployment record {deploy_id} not found in DB!")
            return
            
        if deployment.status != "building":
            raise RuntimeError(
                f"Deployment {deploy_id} is not authorized to start from status {deployment.status}."
            )
        
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
            target_status = deployment_targets.status_payload(azure_connection)
            if not target_status["any_ready"]:
                raise RuntimeError("Azure hosting needs setup before this application can launch.")

            requested_provider = (deployment.infrastructure_metadata or {}).get("target_provider", "auto")
            initial_hint = {
                "framework": project.framework,
                "language": project.language,
                "deployment_strategy": (deployment.infrastructure_metadata or {}).get("target_reason"),
            }
            selected_target = deployment_targets.choose_target(
                initial_hint,
                azure_connection,
                requested_provider,
            )
            namespace_prefix = deployment_targets.namespace_prefix(selected_target, deployment.user_id)
            project_id_raw = normalize_project_id(
                f"{namespace_prefix}-{project.name}-{str(project.id)[:8]}"
            )
            image_ref = deployment.image or deployment_targets.image_ref_for_target(
                selected_target,
                project_id_raw,
                deployment.version or "latest",
            )
            
            # ──────────────────────────────────────────────
            # Stage 1: Repository Verification
            # ──────────────────────────────────────────────
            step_start = time.time()
            await update_stage(1, "active", "...")
            await p_logger.log(f"$ zeroops deploy --repo {repo_name} --env production", "command")
            await p_logger.log("ZeroOps AI deployment engine online", "info")
            await p_logger.log(f"> Project identity resolved: {project_id_raw}", "info")
            await p_logger.log(f"> Immutable source revision: {commit_sha}", "info")
            await p_logger.log(f"> Cloud target: {selected_target.label} ({selected_target.reason})", "info")
            await p_logger.log("> Launch settings confirmed. Your live address will be created after verification.", "info")
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
                repo_path = git.prepare_local_source(project.source_path, deploy_id)
                workspace_path = repo_path
                await p_logger.log(f"$ zeroops source use-upload {project.full_name}", "command")
            else:
                await p_logger.log(f"$ git clone --branch {branch} https://github.com/{repo_name}.git .", "command")
                repo_path = git.clone_repo(
                    repo_name,
                    clone_token,
                    branch=branch,
                    commit_sha=commit_sha,
                    workspace_key=deploy_id,
                )
                workspace_path = repo_path
            await p_logger.log("  Source prepared successfully on local filesystem.", "success")
            step_dur = f"{round(time.time() - step_start, 1)}s"
            await update_stage(2, "completed", step_dur)
            await p_logger.flush_to_db(db)

            # ──────────────────────────────────────────────
            # Stage 3: Analyze Repository
            # ──────────────────────────────────────────────
            step_start = time.time()
            await update_stage(3, "active", "...")
            await p_logger.log("▸ Analyzing repository structure...", "info")
            try:
                metadata = ai.analyze_repository(repo_path, project_id_raw)
                await p_logger.log("  ◆ Model-assisted repository interpretation returned.", "success")
            except (ValueError, RuntimeError) as ai_err:
                await p_logger.log(f"  ⚠ AI provider unavailable: {ai_err}. Using local analyzer.", "warning")
                metadata = ai.analyze_repo_local(repo_path, project_id_raw)
            
            await p_logger.log(f"  ◆ Framework: {metadata.get('framework')} ({metadata.get('version')})", "info")
            await p_logger.log(f"  ◆ Core language: {metadata.get('language')}", "info")
            resources = metadata.get("resources") or {}
            if resources.get("cpu") or resources.get("memory"):
                await p_logger.log(
                    f"  ◆ Recorded resource guidance: CPU {resources.get('cpu') or 'not provided'}, "
                    f"memory {resources.get('memory') or 'not provided'}",
                    "info",
                )
            else:
                await p_logger.log("  ◆ Resource limits were not inferred from source code.", "info")
            
            # Save AI Analysis in DB
            analysis = models.AIAnalysis(
                user_id=deployment.user_id,
                project_id=deployment.project_id,
                framework=metadata.get("framework"),
                framework_version=metadata.get("version"),
                language=metadata.get("language"),
                risk_score=metadata.get("risk_score", 0),
                confidence=metadata.get("confidence", 0),
                cpu_recommendation=resources.get("cpu"),
                memory_recommendation=resources.get("memory"),
                storage_recommendation=resources.get("storage"),
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
                await p_logger.log(f"  ⚠️ Analyzer warning: {vuln}", "warning")
            await p_logger.log("  ✓ Repository analysis recorded.", "success")
            step_dur = f"{round(time.time() - step_start, 1)}s"
            await update_stage(3, "completed", step_dur)
            await p_logger.flush_to_db(db)

            # ──────────────────────────────────────────────
            # Stage 4: Generate Build Specification
            # ──────────────────────────────────────────────
            step_start = time.time()
            await update_stage(4, "active", "...")
            await p_logger.log("▸ Generating build specification...", "info")
            await p_logger.log(f"  ◆ Build Command: {metadata.get('build_commands') or 'None'}", "info")
            await p_logger.log(f"  ◆ Startup Command: {metadata.get('start_commands') or 'None'}", "info")
            await p_logger.log("  ✓ Build instructions prepared.", "success")
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
            client_secret = azure_connector.get_credential_secret(deployment.user_id)
            if not client_secret:
                raise RuntimeError("Azure credentials are unavailable. Reconnect Azure and try again.")
            await p_logger.log("▸ Building your application securely in Azure…", "info")
            for log_line in app_service.build_image(
                connection=selected_target.connection,
                client_secret=client_secret,
                repo_path=repo_path,
                image_ref=image_ref,
                generated_dockerfile=metadata.get("dockerfile"),
            ):
                await p_logger.log(log_line.strip(), "success" if "ready" in log_line.lower() else "info")
                
            build_dur = f"{round(time.time() - build_start, 1)}s"
            await update_stage(7, "completed", build_dur)
            await p_logger.flush_to_db(db)

            # ──────────────────────────────────────────────
            # Stage 8: Deploy Application
            # ──────────────────────────────────────────────
            step_start = time.time()
            await update_stage(8, "active", "...")
            await p_logger.log("▸ Publishing your application…", "info")
            env_result = await db.execute(
                select(models.EnvironmentVariable).filter(
                    models.EnvironmentVariable.environment_id == env.id
                )
            )
            runtime_variables: dict[str, tuple[str, bool]] = {}
            for variable in env_result.scalars().all():
                if variable.is_secret:
                    value = vault.get_project_secret(str(project.id), variable.key)
                    if not value:
                        raise RuntimeError(
                            f"{variable.key} is marked as a secret but is unavailable in Azure Key Vault."
                        )
                    runtime_variables[variable.key] = (value, True)
                else:
                    runtime_variables[variable.key] = (variable.value, False)
            deploy_start = time.time()
            for deployment_result in app_service.deploy_image(
                connection=selected_target.connection,
                client_secret=client_secret,
                app_name=project_id_raw,
                image_ref=image_ref,
                metadata=metadata,
                environment_variables=runtime_variables,
            ):
                if isinstance(deployment_result, app_service.AppServiceRelease):
                    release = deployment_result
                    live_url = release.live_url
                    await p_logger.log("  ✓ Azure has prepared a ready version.", "success")
                    continue
                await p_logger.log(str(deployment_result).strip(), "info")
            if not release:
                raise RuntimeError("Azure did not return a ready application version.")
                
            deploy_dur = f"{round(time.time() - deploy_start, 1)}s"
            await update_stage(8, "completed", deploy_dur)
            await p_logger.flush_to_db(db)

            # ──────────────────────────────────────────────
            # Stage 9: Health Validation
            # ──────────────────────────────────────────────
            step_start = time.time()
            await update_stage(9, "active", "...")
            await p_logger.log("▸ Starting application health check validation...", "info")
            app_service.verify_public_endpoint(live_url)
            await p_logger.log("  ✓ Your public address is responding.", "success")
            step_dur = f"{round(time.time() - step_start, 1)}s"
            await update_stage(9, "completed", step_dur)
            await p_logger.flush_to_db(db)

            # ──────────────────────────────────────────────
            # Stage 10: Generate Live URL
            # ──────────────────────────────────────────────
            step_start = time.time()
            await update_stage(10, "active", "...")
            await p_logger.log("Resolving public route metadata...", "info")
            if not live_url:
                raise RuntimeError("No verified public address was returned by Azure.")
            await p_logger.log(f"  Your app is live: {live_url}", "success")
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
            meta["region"] = (
                getattr(selected_target.connection, "region", None)
                or deployment.project.region
                or "eastus"
            )
            meta["image"] = image_ref
            meta["application_name"] = release.app_name if release else None
            meta["revision"] = release.revision if release else None
            meta["target_provider"] = selected_target.provider
            meta["target_reason"] = selected_target.reason
            meta["target"] = deployment_targets.metadata_for_target(selected_target)
            meta["azure"] = meta["target"]
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

            evaluation_result = await db.execute(
                select(models.DecisionEvaluation).filter(
                    models.DecisionEvaluation.deployment_id == deployment.id
                )
            )
            evaluation = evaluation_result.scalars().first()
            if evaluation:
                evaluation.status = "successful"
                evaluation.outcome_metadata = {
                    "outcome": "Deployment completed and the public endpoint passed runtime health validation.",
                    "completed_at": datetime.utcnow().isoformat(),
                }
                
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

                evaluation_result = await db.execute(
                    select(models.DecisionEvaluation).filter(
                        models.DecisionEvaluation.deployment_id == deployment.id
                    )
                )
                evaluation = evaluation_result.scalars().first()
                if evaluation:
                    evaluation.status = "failed"
                    # Do not copy raw exceptions into the accuracy ledger:
                    # provider responses or command output can contain secrets.
                    evaluation.outcome_metadata = {
                        "outcome": "Deployment pipeline failed before runtime health validation.",
                        "completed_at": datetime.utcnow().isoformat(),
                    }
                    
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
                        confidence=failure_analysis_res.get("confidence", 0),
                        impact="Deployment Halted"
                    )
                    db.add(db_failure_analysis)
                except Exception as analysis_err:
                    print(f"Failed to generate failure analysis: {analysis_err}")
                
                await db.commit()
                await p_logger.flush_to_db(db)

        await broadcast_message(deploy_id, {"type": "status", "status": "failed"})
    finally:
        if workspace_path:
            try:
                git.cleanup_workspace(workspace_path)
            except Exception as cleanup_error:
                print(f"Failed to clean deployment workspace {workspace_path}: {cleanup_error}")
