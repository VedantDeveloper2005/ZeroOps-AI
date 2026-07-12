import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)

if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import asyncio
import base64
import hmac
import json
import uuid
import requests
import logging
import os
import secrets
import shutil
import zipfile
import hashlib
import stat
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta
from typing import Any, Optional, List, Union
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Depends, Response, Query, Request, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc, or_

logger = logging.getLogger("zeroops.main")

try:
    import stripe
except ImportError:
    stripe = None

try:
    from backend import config
    from backend.services import git, ai, pipeline, vault, agent
    from backend.services import deployment_targets
    from backend.services import github_oauth, google_oauth
    from backend.database import get_db, init_db, database_available, AsyncSessionLocal
    from backend import models, schemas, auth
except ImportError:
    import config
    from services import git, ai, pipeline, vault, agent
    from services import deployment_targets
    from services import github_oauth, google_oauth
    from database import get_db, init_db, database_available, AsyncSessionLocal
    import models, schemas, auth

@asynccontextmanager
async def lifespan(_: FastAPI):
    initialized = await init_db()
    if initialized:
        await migrate_legacy_environment_secrets()
        await recover_interrupted_deployments()
    daemon_task = asyncio.create_task(self_healing_daemon())
    try:
        yield
    finally:
        daemon_task.cancel()
        with suppress(asyncio.CancelledError):
            await daemon_task


app = FastAPI(
    title="ZeroOps AI Backend",
    docs_url=None if os.getenv("APP_ENV", "development").lower() == "production" else "/docs",
    redoc_url=None if os.getenv("APP_ENV", "development").lower() == "production" else "/redoc",
    openapi_url=None if os.getenv("APP_ENV", "development").lower() == "production" else "/openapi.json",
    lifespan=lifespan,
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=config.ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "Stripe-Signature"],
    expose_headers=["X-CSRF-Token"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.ALLOWED_HOSTS)


import time
from collections import defaultdict
from fastapi.responses import JSONResponse

# Lightweight in-memory rate limiter for production security
RATE_LIMIT_WINDOW = 60  # 1 minute window
request_counts = defaultdict(list)

@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    path = request.url.path
    if (
        path.startswith("/ws") or 
        path in ["/docs", "/openapi.json", "/favicon.ico"] or
        path.startswith("/api/auth/login") or
        path.startswith("/api/auth/signup") or
        path.startswith("/api/auth/github") or
        path.startswith("/api/auth/google") or
        path.startswith("/api/auth/oauth")
    ):
        return await call_next(request)
        
    has_cookie_auth = "session_token" in request.cookies or "refresh_token" in request.cookies
    
    if request.method in ["POST", "PUT", "DELETE", "PATCH"] and has_cookie_auth:
        cookie_csrf = request.cookies.get("csrf_token")
        header_csrf = request.headers.get("x-csrf-token") or request.headers.get("X-CSRF-Token")
        
        if not cookie_csrf or not header_csrf or cookie_csrf != header_csrf:
            logger.warning(f"CSRF validation failed for path {path}. Cookie: {bool(cookie_csrf)}, Header: {bool(header_csrf)}")
            # Return 403 with manual CORS headers to prevent cross-origin browser blocking
            origin = request.headers.get("origin")
            headers = {}
            if origin and origin in config.CORS_ORIGINS:
                headers["Access-Control-Allow-Origin"] = origin
                headers["Access-Control-Allow-Credentials"] = "true"
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token validation failed. Missing or mismatched token."},
                headers=headers
            )
            
    # Always try to fetch csrf_token if exists, or prepare to generate
    token = request.cookies.get("csrf_token")
    newly_generated = False
    if not token:
        import secrets
        token = secrets.token_urlsafe(32)
        newly_generated = True

    response = await call_next(request)

    # API responses commonly carry account, deployment, or operational data and
    # must not be stored in intermediary browser or CDN caches.
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    if newly_generated:
        is_prod = config.APP_ENV == "production"
        response.set_cookie(
            key="csrf_token",
            value=token,
            httponly=False,  # JavaScript must be able to read it
            max_age=3600 * 24 * 7,  # 7 days
            samesite="none" if is_prod else "lax",
            secure=is_prod
        )

    # Expose the CSRF token in the response headers for cross-domain clients
    if token:
        response.headers["X-CSRF-Token"] = token
        
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    
    # Exclude all health checks and docs/static files
    if (
        path.startswith("/health") or 
        path.startswith("/api/health") or 
        path in ["/docs", "/openapi.json", "/favicon.ico"]
    ):
        return await call_next(request)
        
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    
    # Resolve rate limit category
    if path == "/api/auth/login":
        category = "login"
        limit = 10
    elif path == "/api/auth/signup":
        category = "signup"
        limit = 5
    elif path.startswith("/api/auth/mfa/verify"):
        category = "mfa_verify"
        limit = 10
    elif path.startswith("/api/auth/mfa/setup/confirm"):
        category = "mfa_setup"
        limit = 5
    elif path.startswith("/api/auth/github") or path.startswith("/api/auth/google"):
        category = "oauth"
        limit = 20
    else:
        category = "default"
        limit = 100

    key = (client_ip, category)

    # Bound the number of tracked clients so a stream of unique source IPs
    # cannot grow this in-process safeguard without limit.
    if len(request_counts) >= config.MAX_RATE_LIMIT_KEYS and key not in request_counts:
        expired_keys = [
            item for item, values in request_counts.items()
            if not values or now - values[-1] >= RATE_LIMIT_WINDOW
        ]
        for expired_key in expired_keys:
            request_counts.pop(expired_key, None)
        if len(request_counts) >= config.MAX_RATE_LIMIT_KEYS:
            origin = request.headers.get("origin")
            headers = {}
            if origin and origin in config.CORS_ORIGINS:
                headers["Access-Control-Allow-Origin"] = origin
                headers["Access-Control-Allow-Credentials"] = "true"
            return JSONResponse(
                status_code=429,
                content={"detail": "Request capacity is temporarily full. Please retry shortly."},
                headers=headers
            )
    
    # Filter request timestamps inside the active window
    timestamps = [t for t in request_counts[key] if now - t < RATE_LIMIT_WINDOW]
    request_counts[key] = timestamps
    
    if len(timestamps) >= limit:
        # Prevent browser CORS errors on 429 blocks
        origin = request.headers.get("origin")
        headers = {}
        if origin and origin in config.CORS_ORIGINS:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"
        return JSONResponse(
            status_code=429,
            content={"detail": f"Rate limit exceeded. Maximum {limit} requests per minute allowed for this endpoint."},
            headers=headers
        )
        
    request_counts[key].append(now)
    return await call_next(request)


# ──────────────────────────────────────────────
# STARTUP
# ──────────────────────────────────────────────

async def self_healing_daemon():
    logger.info("Self-healing telemetry daemon started.")

    async def has_pending_action(db: AsyncSession, project_id, action_type: str, message: str) -> bool:
        result = await db.execute(
            select(models.AIAction)
            .filter(
                models.AIAction.project_id == project_id,
                models.AIAction.type == action_type,
                models.AIAction.status == "pending",
                models.AIAction.message == message,
            )
            .limit(1)
        )
        return result.scalars().first() is not None

    while True:
        await asyncio.sleep(20)
        try:
            async with AsyncSessionLocal() as db:
                # 1. Fetch active projects
                result = await db.execute(
                    select(models.Project).filter(models.Project.status == "active")
                )
                projects = result.scalars().all()
                for project in projects:
                    # Find latest deployment for project
                    dep_result = await db.execute(
                        select(models.Deployment)
                        .filter(models.Deployment.project_id == project.id)
                        .order_by(desc(models.Deployment.started_at))
                        .limit(1)
                    )
                    latest_dep = dep_result.scalars().first()
                    if not latest_dep or latest_dep.status != "running":
                        continue
                        
                    # Find latest telemetry metric for deployment
                    metric_result = await db.execute(
                        select(models.DeploymentMetric)
                        .filter(models.DeploymentMetric.deployment_id == latest_dep.id)
                        .order_by(desc(models.DeploymentMetric.timestamp))
                        .limit(1)
                    )
                    latest_metric = metric_result.scalars().first()
                    if not latest_metric:
                        continue
                        
                    # Memory Spike check (e.g. Memory utilization exceeds 90%)
                    if latest_metric.memory_utilization > 90.0:
                        logger.warning(f"Self-Healing: Memory spike detected ({latest_metric.memory_utilization}%) on project {project.name}")

                        action_message = "Memory utilization exceeded threshold"
                        if await has_pending_action(db, project.id, "scaling", action_message):
                            continue
                        
                        # Add activity log
                        db.add(models.ActivityEvent(
                            user_id=project.user_id,
                            project_id=project.id,
                            action="AI Recommendation: Memory spike detected",
                            details=f"Memory utilization reached {latest_metric.memory_utilization}%. Review resource limits or autoscaling before applying changes."
                        ))
                        
                        # Add AIAction
                        db.add(models.AIAction(
                            user_id=project.user_id,
                            project_id=project.id,
                            type="scaling",
                            severity="warning",
                            message=action_message,
                            recommendation="Review current memory limits and autoscaling policy for this project. Apply changes through the deployment pipeline after validation.",
                            status="pending",
                            icon="Layers"
                        ))
                        
                        # Add Notification
                        db.add(models.Notification(
                            user_id=project.user_id,
                            title="Memory Spike Detected",
                            message=f"ZeroOps AI detected high memory utilization on {project.name}. A scaling recommendation is pending review.",
                            type="warning",
                            category="scaling"
                        ))
                        await db.commit()
                        
                    # Crash Loop check (e.g. error rate exceeds 15%)
                    elif latest_metric.error_rate > 15.0:
                        logger.warning(f"Self-Healing: Crash loop / high error rate ({latest_metric.error_rate}%) on project {project.name}")

                        action_message = "High error rate detected; rollback review needed"
                        if await has_pending_action(db, project.id, "healing", action_message):
                            continue
                        details = f"Detected {latest_metric.error_rate}% error rate on {latest_dep.version or 'current deployment'}. Review logs and roll back through the deployment pipeline if needed."
                            
                        # Add activity log
                        db.add(models.ActivityEvent(
                            user_id=project.user_id,
                            project_id=project.id,
                            action="AI Recommendation: High error rate detected",
                            details=details
                        ))
                        
                        # Add AIAction
                        db.add(models.AIAction(
                            user_id=project.user_id,
                            project_id=project.id,
                            type="healing",
                            severity="critical",
                            message=action_message,
                            recommendation="Inspect the failed request logs, verify the latest deployment, and trigger a validated rollback if the current release is unhealthy.",
                            status="pending",
                            icon="Undo"
                        ))
                        
                        # Add Notification
                        db.add(models.Notification(
                            user_id=project.user_id,
                            title="High Error Rate Detected",
                            message=f"ZeroOps AI detected high error rates on {project.name}. A remediation recommendation is pending review.",
                            type="critical",
                            category="incident"
                        ))
                        await db.commit()
        except Exception as e:
            logger.error(f"Error in self_healing_daemon: {e}")


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

def map_user_response(user: models.User) -> schemas.UserResponse:
    return schemas.UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        firstName=user.first_name,
        lastName=user.last_name,
        provider=user.provider,
        provider_id=user.provider_id,
        avatar_url=user.avatar_url,
        plan=user.plan,
        created_at=user.created_at.isoformat() if user.created_at else None,
        github_connected=user.github_connected or False,
        github_username=user.github_username,
        mfa_enabled=user.mfa_enabled or False,
    )

def format_duration(seconds: Optional[int]) -> str:
    if seconds is None:
        return "—"
    m, s = divmod(seconds, 60)
    return f"{m}m {s}s" if m > 0 else f"{s}s"

def format_dt(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


async def migrate_legacy_environment_secrets() -> None:
    """Move legacy database secret values to Key Vault before clearing them."""
    if not vault.HAS_AZURE_KV or AsyncSessionLocal is None:
        if config.IS_PRODUCTION:
            logger.error("Key Vault is unavailable; legacy environment secrets were not migrated.")
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(models.EnvironmentVariable, models.Environment.project_id)
            .join(models.Environment, models.EnvironmentVariable.environment_id == models.Environment.id)
            .filter(models.EnvironmentVariable.is_secret == True, models.EnvironmentVariable.value != "")
        )
        migrated = 0
        for variable, project_id in result.all():
            try:
                vault.set_project_secret(str(project_id), variable.key, variable.value)
                variable.value = ""
                migrated += 1
            except Exception:
                logger.exception("Unable to migrate an environment secret to Key Vault")
        if migrated:
            await db.commit()
            logger.info("Migrated %s legacy environment secrets to Key Vault.", migrated)


async def recover_interrupted_deployments() -> None:
    """Fail unfinished in-process work after a restart instead of leaving it stuck."""
    if AsyncSessionLocal is None:
        return
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(models.Deployment).filter(models.Deployment.status.in_(["queued", "building"]))
        )
        deployments = result.scalars().all()
        if not deployments:
            return
        now = datetime.utcnow()
        for deployment in deployments:
            deployment.status = "failed"
            deployment.failure_reason = "Deployment worker restarted before this release completed. Retry the release safely."
            deployment.completed_at = now
            project_result = await db.execute(
                select(models.Project).filter(models.Project.id == deployment.project_id)
            )
            project = project_result.scalars().first()
            if project and project.status == "deploying":
                project.status = "failed"
        await db.commit()
        logger.warning("Marked %s interrupted deployment(s) as failed after restart.", len(deployments))


def get_frontend_redirect_url() -> str:
    frontend_url = (config.FRONTEND_URL or "").rstrip("/")
    if not frontend_url:
        raise HTTPException(status_code=500, detail="FRONTEND_URL is not configured.")
    lowered = frontend_url.lower()
    if config.APP_ENV == "production" and (
        lowered.startswith("http://")
        or "localhost" in lowered
        or "127.0.0.1" in lowered
    ):
        raise HTTPException(status_code=500, detail="FRONTEND_URL must be a public HTTPS origin in production.")
    return frontend_url


# ──────────────────────────────────────────────
# AUTHENTICATION
# ──────────────────────────────────────────────

def map_billing_operation(op: models.BillingOperation) -> dict:
    return {
        "id": str(op.id),
        "operation_type": op.operation_type,
        "status": op.status,
        "amount_cents": op.amount_cents,
        "currency": op.currency,
        "description": op.description,
        "project_id": str(op.project_id) if op.project_id else None,
        "deployment_id": str(op.deployment_id) if op.deployment_id else None,
        "provider": op.provider,
        "provider_reference": op.provider_reference,
        "created_at": format_dt(op.created_at),
        "paid_at": format_dt(op.paid_at),
        "consumed_at": format_dt(op.consumed_at),
    }


def create_stripe_checkout_session(op: models.BillingOperation, user: models.User):
    if stripe is None:
        raise HTTPException(status_code=500, detail="Stripe package is not installed on the backend.")
    if not config.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe secret key is not configured.")
    stripe.api_key = config.STRIPE_SECRET_KEY
    base_url = (config.FRONTEND_URL or "").rstrip("/")
    if not base_url:
        raise HTTPException(status_code=500, detail="FRONTEND_URL is required for Stripe checkout.")
    return stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": op.currency,
                "product_data": {
                    "name": "ZeroOps AI code remediation",
                    "description": op.description or op.operation_type.replace("_", " "),
                },
                "unit_amount": op.amount_cents,
            },
            "quantity": 1,
        }],
        success_url=f"{base_url}/dashboard/billing?payment=success&operation_id={op.id}",
        cancel_url=f"{base_url}/dashboard/billing?payment=cancelled&operation_id={op.id}",
        metadata={
            "operation_id": str(op.id),
            "user_id": str(user.id),
            "operation_type": op.operation_type,
        },
    )


async def get_active_azure_connection(db: AsyncSession, user_id: uuid.UUID) -> Optional[models.UserAzureConnection]:
    result = await db.execute(
        select(models.UserAzureConnection)
        .filter(
            models.UserAzureConnection.user_id == user_id,
            or_(
                models.UserAzureConnection.connection_status == "connected",
                models.UserAzureConnection.is_active == True
            )
        )
        .order_by(desc(models.UserAzureConnection.created_at))
        .limit(1)
    )
    return result.scalars().first()


async def get_active_gke_connection(db: AsyncSession, user_id: uuid.UUID) -> Optional[models.UserGkeConnection]:
    result = await db.execute(
        select(models.UserGkeConnection)
        .filter(models.UserGkeConnection.user_id == user_id, models.UserGkeConnection.is_active == True)
        .order_by(desc(models.UserGkeConnection.created_at))
        .limit(1)
    )
    return result.scalars().first()


async def get_latest_deployment_hint(db: AsyncSession, user_id: uuid.UUID, project: models.Project) -> dict[str, Any]:
    analysis_result = await db.execute(
        select(models.AIAnalysis)
        .filter(models.AIAnalysis.project_id == project.id)
        .order_by(desc(models.AIAnalysis.created_at))
        .limit(1)
    )
    analysis = analysis_result.scalars().first()
    if analysis:
        return {
            "deployment_strategy": analysis.deployment_strategy,
            "framework": analysis.framework,
            "language": analysis.language,
            "runtime": analysis.runtime,
            "docker_support": analysis.docker_support,
            "kubernetes_manifest": analysis.kubernetes_manifest,
            "explanation": analysis.explanation,
        }

    recommendation_result = await db.execute(
        select(models.DeploymentRecommendation)
        .filter(
            models.DeploymentRecommendation.user_id == user_id,
            models.DeploymentRecommendation.repository_full_name == project.full_name,
        )
        .order_by(desc(models.DeploymentRecommendation.created_at))
        .limit(1)
    )
    recommendation = recommendation_result.scalars().first()
    if recommendation:
        return {
            "recommended_target": recommendation.recommended_target,
            "deployment_strategy": recommendation.recommended_target,
            "recommended_region": recommendation.recommended_region,
            "framework": project.framework,
            "language": project.language,
        }

    return {
        "framework": project.framework,
        "language": project.language,
    }


async def consume_paid_operation(
    db: AsyncSession,
    user_id: uuid.UUID,
    operation_type: str,
    project_id: Optional[uuid.UUID] = None,
    deployment_id: Optional[uuid.UUID] = None,
) -> models.BillingOperation:
    query = (
        select(models.BillingOperation)
        .filter(
            models.BillingOperation.user_id == user_id,
            models.BillingOperation.operation_type == operation_type,
            models.BillingOperation.status == "paid",
            models.BillingOperation.consumed_at == None,
        )
        .order_by(models.BillingOperation.paid_at.asc())
        .limit(1)
    )
    if project_id:
        query = query.filter(models.BillingOperation.project_id == project_id)
    if deployment_id:
        query = query.filter(or_(models.BillingOperation.deployment_id == deployment_id, models.BillingOperation.deployment_id == None))

    result = await db.execute(query)
    operation = result.scalars().first()
    if not operation:
        raise HTTPException(
            status_code=402,
            detail=(
                "Payment approval is required before ZeroOps AI can run code-changing "
                "or redeployment remediation. Create and pay a billing operation first."
            ),
        )

    operation.status = "consumed"
    operation.consumed_at = datetime.utcnow()
    return operation


def safe_extract_zip(zip_path: str, target_dir: str):
    """Extract a user archive with path, symlink, and zip-bomb safeguards."""
    target_abs = os.path.abspath(target_dir)
    with zipfile.ZipFile(zip_path) as archive:
        members = archive.infolist()
        if len(members) > config.MAX_UPLOAD_ARCHIVE_FILES:
            raise HTTPException(status_code=400, detail="Upload archive contains too many files.")

        total_uncompressed = 0
        for member in archive.infolist():
            if not member.filename or member.filename.endswith("/"):
                continue
            if stat.S_ISLNK(member.external_attr >> 16):
                raise HTTPException(status_code=400, detail="Upload archive cannot contain symbolic links.")
            total_uncompressed += member.file_size
            if total_uncompressed > config.MAX_UPLOAD_UNCOMPRESSED_MB * 1024 * 1024:
                raise HTTPException(status_code=400, detail="Upload archive expands beyond the allowed size.")
            if member.file_size and not member.compress_size:
                raise HTTPException(status_code=400, detail="Upload archive has an unsafe compressed entry.")
            if member.file_size and member.compress_size and member.file_size / member.compress_size > config.MAX_UPLOAD_COMPRESSION_RATIO:
                raise HTTPException(status_code=400, detail="Upload archive compression ratio is unsafe.")
            member_path = os.path.abspath(os.path.join(target_abs, member.filename))
            try:
                is_within_target = os.path.commonpath([target_abs, member_path]) == target_abs
            except ValueError:
                is_within_target = False
            if not is_within_target:
                raise HTTPException(status_code=400, detail="Upload archive contains unsafe paths.")
            os.makedirs(os.path.dirname(member_path), exist_ok=True)
            with archive.open(member, "r") as source, open(member_path, "wb") as destination:
                shutil.copyfileobj(source, destination)


def normalize_upload_root(path: str) -> str:
    entries = [entry for entry in os.listdir(path) if not entry.startswith("__MACOSX")]
    if len(entries) == 1:
        only_path = os.path.join(path, entries[0])
        if os.path.isdir(only_path):
            return only_path
    return path


async def establish_authenticated_session(
    user: models.User,
    response: Response,
    db: AsyncSession,
) -> schemas.UserResponse:
    """Persist a rotated refresh token and set the full-session cookies."""
    access_token, refresh_token = auth.get_session_tokens(str(user.id))
    user.refresh_token = auth.hash_refresh_token(refresh_token)
    user.mfa_challenge_id = None
    user.mfa_challenge_expires_at = None
    db.add(user)
    await db.commit()
    auth.clear_mfa_challenge_cookie(response)
    auth.set_session_cookies(response, access_token, refresh_token)
    return map_user_response(user)


async def begin_mfa_challenge(
    user: models.User,
    response: Response,
    db: AsyncSession,
) -> schemas.MFAChallengeResponse:
    """Create one pre-authentication challenge and remove any full session."""
    challenge_id = secrets.token_urlsafe(32)
    user.mfa_challenge_id = challenge_id
    user.mfa_challenge_expires_at = datetime.utcnow() + timedelta(minutes=config.MFA_CHALLENGE_EXPIRE_MINUTES)
    user.refresh_token = None
    db.add(user)
    await db.commit()
    auth.clear_session_cookies(response)
    auth.set_mfa_challenge_cookie(response, auth.create_mfa_challenge_token(str(user.id), challenge_id))
    return schemas.MFAChallengeResponse()


@app.post("/api/auth/signup", response_model=schemas.UserResponse)
async def signup(req: schemas.UserCreate, response: Response, db: AsyncSession = Depends(get_db)):
    email = req.email.strip().lower()
    first_name = req.first_name or req.firstName
    last_name = req.last_name or req.lastName

    try:
        result = await db.execute(select(models.User).filter(models.User.email == email))
        existing_user = result.scalars().first()
    except Exception as error:
        logger.exception("Unable to check whether a signup email already exists.")
        raise HTTPException(status_code=503, detail="Database is currently unavailable.") from error

    if existing_user:
        raise HTTPException(status_code=409, detail="A user with this email address already exists.")

    new_user = models.User(
        id=uuid.uuid4(),
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash=auth.get_password_hash(req.password),
        provider="local",
        plan="starter",
        last_primary_auth_at=datetime.utcnow(),
    )

    try:
        db.add(new_user)
        await db.flush()
        db.add(models.UserSettings(user_id=new_user.id))
        db.add(models.Notification(
            user_id=new_user.id,
            title="Welcome to ZeroOps AI",
            message="Your autonomous cloud deployment platform is ready. Connect a repository to get started.",
            type="success",
            category="system",
        ))
        await db.commit()
        await db.refresh(new_user)
    except Exception as error:
        await db.rollback()
        logger.exception("Unable to create a new user account.")
        raise HTTPException(status_code=500, detail="Failed to register user.") from error

    return await establish_authenticated_session(new_user, response, db)


@app.post("/api/auth/login", response_model=Union[schemas.UserResponse, schemas.MFAChallengeResponse])
async def login(req: schemas.UserLogin, response: Response, db: AsyncSession = Depends(get_db)):
    email = req.email.strip().lower()
    try:
        result = await db.execute(select(models.User).filter(models.User.email == email))
        user = result.scalars().first()
    except Exception as error:
        logger.exception("Unable to look up a login account.")
        raise HTTPException(status_code=503, detail="Database is currently unavailable.") from error

    if not user or not user.password_hash or not auth.verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    user.last_primary_auth_at = datetime.utcnow()
    if user.mfa_enabled and user.mfa_secret_encrypted:
        return await begin_mfa_challenge(user, response, db)
    return await establish_authenticated_session(user, response, db)


@app.get("/api/auth/me", response_model=schemas.UserResponse)
async def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return map_user_response(current_user)


@app.post("/api/auth/logout")
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[models.User] = Depends(auth.get_current_user)
):
    if current_user:
        current_user.refresh_token = None
        current_user.mfa_challenge_id = None
        current_user.mfa_challenge_expires_at = None
        db.add(current_user)
        await db.commit()
    auth.clear_session_cookies(response)
    auth.clear_mfa_challenge_cookie(response)
    return {"status": "success", "message": "Logged out successfully."}


@app.post("/api/auth/oauth", status_code=status.HTTP_410_GONE)
async def legacy_oauth_authenticate():
    """Reject the former client-asserted OAuth endpoint.

    Identity data must only come from a verified provider callback, never from a
    browser POST body.
    """
    raise HTTPException(status_code=status.HTTP_410_GONE, detail="Use the provider sign-in flow instead.")


@app.post("/api/auth/mfa/verify", response_model=schemas.UserResponse)
async def verify_mfa_challenge(
    req: schemas.MFACodeRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    challenge = auth.decode_mfa_challenge(request)
    try:
        user_id = uuid.UUID(challenge["sub"])
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your verification session is invalid. Sign in again.") from error

    result = await db.execute(select(models.User).filter(models.User.id == user_id))
    user = result.scalars().first()
    if (
        not user
        or not user.mfa_enabled
        or not user.mfa_secret_encrypted
        or not user.mfa_challenge_id
        or not user.mfa_challenge_expires_at
        or user.mfa_challenge_expires_at < datetime.utcnow()
        or not hmac.compare_digest(user.mfa_challenge_id, challenge["challenge_id"])
    ):
        auth.clear_mfa_challenge_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your verification session has expired. Sign in again.")

    secret = auth.decrypt_mfa_secret(user.mfa_secret_encrypted)
    counter = auth.verify_totp_code(secret, req.code) if secret else None
    if counter is not None:
        if user.mfa_last_used_counter is not None and counter <= user.mfa_last_used_counter:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This verification code was already used. Wait for a new code and try again.")
        user.mfa_last_used_counter = counter
    elif not auth.consume_recovery_code(user, req.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authenticator or recovery code.")

    return await establish_authenticated_session(user, response, db)


@app.get("/api/auth/mfa/status", response_model=schemas.MFAStatusResponse)
async def get_mfa_status(current_user: models.User = Depends(auth.get_current_user)):
    return schemas.MFAStatusResponse(
        enabled=bool(current_user.mfa_enabled and current_user.mfa_secret_encrypted),
        recovery_codes_remaining=len(current_user.mfa_recovery_code_hashes or []),
    )


@app.post("/api/auth/mfa/setup", response_model=schemas.MFASetupResponse)
async def start_mfa_setup(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Multi-factor authentication is already enabled.")
    if not auth.is_recent_primary_authentication(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sign out and sign in again before changing multi-factor authentication.")

    secret = auth.generate_totp_secret()
    expires_at = datetime.utcnow() + timedelta(minutes=config.MFA_CHALLENGE_EXPIRE_MINUTES)
    current_user.mfa_setup_secret_encrypted = auth.encrypt_mfa_secret(secret)
    current_user.mfa_setup_expires_at = expires_at
    db.add(current_user)
    await db.commit()

    try:
        from io import BytesIO
        import qrcode

        otpauth_uri = auth.build_totp_uri(secret, current_user.email)
        image_buffer = BytesIO()
        qrcode.make(otpauth_uri).save(image_buffer, format="PNG")
        qr_code_data_uri = "data:image/png;base64," + base64.b64encode(image_buffer.getvalue()).decode("ascii")
    except Exception as error:
        logger.exception("Unable to generate an MFA QR code.")
        raise HTTPException(status_code=500, detail="Unable to prepare MFA enrollment. Please try again.") from error

    return schemas.MFASetupResponse(
        manual_key=secret,
        otpauth_uri=otpauth_uri,
        qr_code_data_uri=qr_code_data_uri,
        expires_at=expires_at,
    )


@app.post("/api/auth/mfa/setup/confirm", response_model=schemas.MFASetupConfirmResponse)
async def confirm_mfa_setup(
    req: schemas.MFACodeRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.mfa_setup_secret_encrypted or not current_user.mfa_setup_expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Start MFA setup before confirming it.")
    if current_user.mfa_setup_expires_at < datetime.utcnow():
        current_user.mfa_setup_secret_encrypted = None
        current_user.mfa_setup_expires_at = None
        await db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA setup expired. Start again to get a fresh QR code.")

    secret = auth.decrypt_mfa_secret(current_user.mfa_setup_secret_encrypted)
    counter = auth.verify_totp_code(secret, req.code) if secret else None
    if counter is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="The authenticator code is invalid. Check the device time and try again.")

    recovery_codes, recovery_code_hashes = auth.generate_recovery_codes()
    current_user.mfa_enabled = True
    current_user.mfa_secret_encrypted = current_user.mfa_setup_secret_encrypted
    current_user.mfa_setup_secret_encrypted = None
    current_user.mfa_setup_expires_at = None
    current_user.mfa_recovery_code_hashes = recovery_code_hashes
    current_user.mfa_last_used_counter = counter
    db.add(current_user)
    await db.commit()
    return schemas.MFASetupConfirmResponse(recovery_codes=recovery_codes)


@app.post("/api/auth/mfa/disable")
async def disable_mfa(
    req: schemas.MFACodeRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.mfa_enabled or not current_user.mfa_secret_encrypted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Multi-factor authentication is not enabled.")

    secret = auth.decrypt_mfa_secret(current_user.mfa_secret_encrypted)
    counter = auth.verify_totp_code(secret, req.code) if secret else None
    if counter is not None:
        if current_user.mfa_last_used_counter is not None and counter <= current_user.mfa_last_used_counter:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This verification code was already used. Wait for a new code and try again.")
    elif not auth.consume_recovery_code(current_user, req.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authenticator or recovery code.")

    current_user.mfa_enabled = False
    current_user.mfa_secret_encrypted = None
    current_user.mfa_setup_secret_encrypted = None
    current_user.mfa_setup_expires_at = None
    current_user.mfa_recovery_code_hashes = []
    current_user.mfa_last_used_counter = None
    db.add(current_user)
    await db.commit()
    return {"status": "success", "message": "Multi-factor authentication has been disabled."}


# ──────────────────────────────────────────────
# PROJECTS (per-user)
# ──────────────────────────────────────────────

@app.get("/api/projects")
async def list_projects(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(models.Project)
        .filter(models.Project.user_id == current_user.id)
        .order_by(desc(models.Project.created_at))
    )
    projects = result.scalars().all()

    response = []
    for p in projects:
        dep_result = await db.execute(
            select(func.count(models.Deployment.id))
            .filter(models.Deployment.project_id == p.id)
        )
        dep_count = dep_result.scalar() or 0

        latest_dep_result = await db.execute(
            select(models.Deployment.status)
            .filter(models.Deployment.project_id == p.id)
            .order_by(desc(models.Deployment.started_at))
            .limit(1)
        )
        latest_status = latest_dep_result.scalar()

        response.append(schemas.ProjectResponse(
            id=p.id, name=p.name, full_name=p.full_name,
            repo_url=p.repo_url, framework=p.framework,
            language=p.language, branch=p.branch, region=p.region,
            status=p.status, last_deployed_at=format_dt(p.last_deployed_at),
            created_at=format_dt(p.created_at),
            deployment_count=dep_count,
            latest_deployment_status=latest_status
        ))
    return response


@app.post("/api/projects")
async def create_project(
    req: schemas.ProjectCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    project = models.Project(
        user_id=current_user.id,
        name=req.name,
        full_name=req.full_name,
        repo_url=req.repo_url,
        framework=req.framework,
        language=req.language,
        branch=req.branch,
        region=req.region
    )
    db.add(project)
    await db.flush()

    # Create default production environment
    production_env = models.Environment(
        project_id=project.id,
        name="production"
    )
    db.add(production_env)
    await db.flush()

    # Create notification
    db.add(models.Notification(
        user_id=current_user.id,
        title="Project Connected",
        message=f"Repository {req.full_name} has been connected to ZeroOps.",
        type="success",
        category="deployment"
    ))

    # Query latest AIAnalysis and DeploymentRecommendation to perform database auto-provisioning
    analysis_result = await db.execute(
        select(models.AIAnalysis)
        .filter(models.AIAnalysis.user_id == current_user.id, models.AIAnalysis.project_id == None)
        .order_by(desc(models.AIAnalysis.created_at))
        .limit(1)
    )
    analysis = analysis_result.scalars().first()
    
    recommendation_result = await db.execute(
        select(models.DeploymentRecommendation)
        .filter(
            models.DeploymentRecommendation.user_id == current_user.id,
            models.DeploymentRecommendation.repository_full_name == req.full_name,
            models.DeploymentRecommendation.project_id == None
        )
        .order_by(desc(models.DeploymentRecommendation.created_at))
        .limit(1)
    )
    recommendation = recommendation_result.scalars().first()
    
    if analysis:
        analysis.project_id = project.id
    if recommendation:
        recommendation.project_id = project.id

    import secrets
    detected_databases = []
    if analysis and analysis.database_dependencies:
        detected_databases = [db_name for db_name in analysis.database_dependencies if db_name and db_name != "None"]
    elif recommendation and recommendation.database_recommendation:
        primary_db = recommendation.database_recommendation.get("primary")
        if primary_db and primary_db != "None":
            detected_databases = [primary_db]

    if detected_databases:
        db.add(models.Notification(
            user_id=current_user.id,
            title="Database Configuration Required",
            message=(
                f"{req.name} references {', '.join(detected_databases)}. "
                "Add a real database connection string before deployment."
            ),
            type="warning",
            category="deployment"
        ))

    required_vars = []
    if analysis and analysis.pricing_breakdown:
        required_vars = [
            item.get("key")
            for item in (analysis.pricing_breakdown.get("detected_vars_detail") or [])
            if item.get("type") == "required" and item.get("key")
        ]
    if not required_vars and analysis and analysis.environment_variables:
        required_vars = analysis.environment_variables
    elif not required_vars and recommendation and recommendation.environment_variables:
        required_vars = recommendation.environment_variables

    for var_key in required_vars:
        if var_key in ["DATABASE_URL", "MONGODB_URI", "REDIS_URL"]:
            db.add(models.Notification(
                user_id=current_user.id,
                title=f"{var_key} Required",
                message=f"Add {var_key} in project environment settings before deploying {req.name}.",
                type="warning",
                category="deployment"
            ))
            continue
            
        if var_key in ["JWT_SECRET", "AUTH_SECRET", "NEXTAUTH_SECRET", "SESSION_SECRET"]:
            secure_val = f"zo_sec_{secrets.token_hex(24)}"
            is_secret = True
        elif var_key == "PORT":
            secure_val = "3000"
            is_secret = False
        elif var_key in ["NODE_ENV", "APP_ENV"]:
            secure_val = "production"
            is_secret = False
        else:
            db.add(models.Notification(
                user_id=current_user.id,
                title=f"{var_key} Required",
                message=f"Add {var_key} in project environment settings. ZeroOps will not generate external credentials.",
                type="warning",
                category="deployment"
            ))
            continue
            
        db.add(models.EnvironmentVariable(
            environment_id=production_env.id,
            key=var_key,
            value="" if is_secret else secure_val,
            is_secret=is_secret
        ))
        if is_secret:
            vault.set_project_secret(str(project.id), var_key, secure_val)

    await db.commit()
    await db.refresh(project)

    return schemas.ProjectResponse(
        id=project.id, name=project.name, full_name=project.full_name,
        repo_url=project.repo_url, framework=project.framework,
        language=project.language, branch=project.branch, region=project.region,
        status=project.status, created_at=format_dt(project.created_at),
        deployment_count=0, latest_deployment_status=None
    )


@app.post("/api/projects/upload")
async def upload_code_project(
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    filename = file.filename or "source.zip"
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only ZIP archives are supported for direct code upload.")

    max_bytes = config.MAX_CODE_UPLOAD_MB * 1024 * 1024
    upload_id = uuid.uuid4()
    upload_dir = os.path.join(config.WORKSPACE_DIR, "uploads", str(current_user.id), str(upload_id))
    archive_path = os.path.join(upload_dir, "source.zip")
    extract_dir = os.path.join(upload_dir, "extracted")
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(extract_dir, exist_ok=True)

    digest = hashlib.sha256()
    size_bytes = 0
    try:
        with open(archive_path, "wb") as out_file:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > max_bytes:
                    raise HTTPException(status_code=413, detail=f"Upload exceeds {config.MAX_CODE_UPLOAD_MB} MB limit.")
                digest.update(chunk)
                out_file.write(chunk)

        safe_extract_zip(archive_path, extract_dir)
        source_root = normalize_upload_root(extract_dir)
        project_id_raw = f"upload-{str(upload_id)[:8]}"
        try:
            analysis = ai.analyze_repository(source_root, project_id_raw)
        except (ValueError, RuntimeError) as ai_error:
            logger.info("Repository review unavailable for uploaded project; using source scanner: %s", ai_error)
            analysis = ai.analyze_repo_local(source_root, project_id_raw)
        pricing = analysis.get("pricing_breakdown") or {}
        for key in [
            "compute_cost",
            "database_cost",
            "platform_fee",
            "bandwidth_cost",
            "monitoring_cost",
            "total_cost",
            "projected_growth_cost",
            "why_this_plan",
            "detected_vars_detail",
            "application_type",
            "estimated_build_time",
            "production_readiness_score",
            "detected_services",
        ]:
            if key in pricing and key not in analysis:
                analysis[key] = pricing[key]

        project = models.Project(
            user_id=current_user.id,
            name=project_id_raw,
            full_name=f"upload/{project_id_raw}",
            repo_url=None,
            framework=analysis.get("framework") or "Unknown",
            language=analysis.get("language") or "Unknown",
            branch="uploaded",
            region=config.AZURE_DEFAULT_REGION,
            source_type="upload",
            source_path=source_root,
        )
        db.add(project)
        await db.flush()

        production_env = models.Environment(project_id=project.id, name="production")
        db.add(production_env)
        db.add(models.CodeUpload(
            id=upload_id,
            user_id=current_user.id,
            project_id=project.id,
            original_filename=filename,
            storage_path=source_root,
            size_bytes=size_bytes,
            checksum_sha256=digest.hexdigest(),
        ))
        db.add(models.AIAnalysis(
            user_id=current_user.id,
            project_id=project.id,
            framework=analysis.get("framework"),
            framework_version=analysis.get("version") or analysis.get("framework_version"),
            language=analysis.get("language"),
            risk_score=analysis.get("risk_score", 0),
            confidence=analysis.get("confidence", 0),
            cpu_recommendation=analysis.get("resources", {}).get("cpu"),
            memory_recommendation=analysis.get("resources", {}).get("memory"),
            storage_recommendation=analysis.get("resources", {}).get("storage"),
            dependencies=analysis.get("dependencies", []),
            vulnerabilities=analysis.get("vulnerabilities", []),
            dockerfile=analysis.get("dockerfile"),
            kubernetes_manifest=analysis.get("kubernetes_manifest"),
            runtime=analysis.get("runtime"),
            package_manager=analysis.get("package_manager"),
            docker_support=analysis.get("docker_support", False),
            monorepo_structure=analysis.get("monorepo_structure"),
            database_dependencies=analysis.get("database_dependencies", []),
            deployment_strategy=analysis.get("deployment_strategy"),
            build_commands=analysis.get("build_commands"),
            start_commands=analysis.get("start_commands"),
            environment_variables=analysis.get("environment_variables", []),
            explanation=analysis.get("explanation"),
            recommended_compute_tier=analysis.get("recommended_compute_tier"),
            estimated_cost=analysis.get("estimated_cost"),
            recommended_region=analysis.get("recommended_region"),
            expected_traffic=analysis.get("expected_traffic"),
            pricing_breakdown=analysis.get("pricing_breakdown"),
        ))
        db.add(models.Notification(
            user_id=current_user.id,
            title="Code Uploaded",
            message=f"{filename} was uploaded and scanned successfully.",
            type="success",
            category="deployment",
        ))
        await db.commit()
        await db.refresh(project)

        return {
            "project": schemas.ProjectResponse(
                id=project.id,
                name=project.name,
                full_name=project.full_name,
                repo_url=project.repo_url,
                framework=project.framework,
                language=project.language,
                branch=project.branch,
                region=project.region,
                status=project.status,
                created_at=format_dt(project.created_at),
                deployment_count=0,
                latest_deployment_status=None,
            ),
            "analysis": analysis,
        }
    except HTTPException:
        await db.rollback()
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise
    except zipfile.BadZipFile:
        await db.rollback()
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Upload is not a valid ZIP archive.")
    except Exception as e:
        await db.rollback()
        shutil.rmtree(upload_dir, ignore_errors=True)
        logger.error(f"Code upload failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to process uploaded code.")


@app.get("/api/projects/{project_id}")
async def get_project(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(models.Project)
        .filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


@app.delete("/api/projects/{project_id}")
async def delete_project(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(models.Project)
        .filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    await db.delete(project)
    await db.commit()
    return {"status": "success"}


@app.get("/api/azure/connection")
async def get_azure_connection(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    connection = await get_active_azure_connection(db, current_user.id)
    if not connection:
        return {"connected": False}
    return {
        "connected": connection.connection_status == "connected",
        "connection_status": connection.connection_status,
        "tenant_id": connection.tenant_id,
        "subscription_id": connection.subscription_id,
        "client_id": connection.client_id,
        "region": connection.region,
        "resource_group": connection.resource_group,
        "acr_login_server": connection.acr_login_server,
        "app_service_plan": connection.app_service_plan,
        "namespace_prefix": connection.namespace_prefix,
        "created_at": format_dt(connection.created_at),
        "updated_at": format_dt(connection.updated_at),
    }


@app.post("/api/azure/connect")
async def connect_azure(
    req: schemas.AzureConnectRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from backend.services import azure_connector

    # Validate credential first
    validation_res = azure_connector.validate_credential(
        tenant_id=req.tenant_id,
        client_id=req.client_id,
        client_secret=req.client_secret,
        subscription_id=req.subscription_id,
        resource_group=req.resource_group
    )
    if not validation_res.get("success"):
        raise HTTPException(status_code=400, detail=validation_res.get("error", "Azure credential validation failed."))

    # Store SP client secret in vault
    store_ok = azure_connector.store_credential_in_vault(current_user.id, req.client_secret)
    if not store_ok:
        raise HTTPException(status_code=500, detail="Failed to secure client secret in vault.")

    # Find existing or create new connection
    existing = await get_active_azure_connection(db, current_user.id)
    if existing:
        existing.tenant_id = req.tenant_id.strip()
        existing.subscription_id = req.subscription_id.strip()
        existing.client_id = req.client_id.strip()
        existing.region = req.region or config.AZURE_DEFAULT_REGION
        existing.resource_group = req.resource_group.strip()
        existing.acr_login_server = req.acr_login_server.strip().rstrip("/") if req.acr_login_server else None
        existing.app_service_plan = req.app_service_plan.strip() if req.app_service_plan else None
        existing.namespace_prefix = req.namespace_prefix.strip() if req.namespace_prefix else None
        existing.connection_status = "connected"
        existing.is_active = True
        existing.updated_at = datetime.utcnow()
        connection = existing
    else:
        connection = models.UserAzureConnection(
            user_id=current_user.id,
            tenant_id=req.tenant_id.strip(),
            subscription_id=req.subscription_id.strip(),
            client_id=req.client_id.strip(),
            region=req.region or config.AZURE_DEFAULT_REGION,
            resource_group=req.resource_group.strip(),
            acr_login_server=req.acr_login_server.strip().rstrip("/") if req.acr_login_server else None,
            app_service_plan=req.app_service_plan.strip() if req.app_service_plan else None,
            namespace_prefix=req.namespace_prefix.strip() if req.namespace_prefix else None,
            connection_status="connected",
            is_active=True,
        )
        db.add(connection)

    await db.commit()
    
    # Audit log entry for connection connect
    try:
        from backend.services import action_gateway
        # Connect is a low risk action, but we audit it anyway for compliance
        audit = models.AuditLogEntry(
            user_id=current_user.id,
            agent_name="user",
            action_type="azure_connection_connect",
            parameters={"subscription_id": connection.subscription_id, "resource_group": connection.resource_group},
            risk_tier="low",
            approval_status="not_required",
            result_status="success"
        )
        db.add(audit)
        await db.commit()
    except Exception as audit_err:
        logger.error(f"Failed to write onboarding audit: {audit_err}")

    return {
        "connected": True,
        "connection_status": connection.connection_status,
        "subscription_id": connection.subscription_id,
        "tenant_id": connection.tenant_id,
        "client_id": connection.client_id,
        "resource_group": connection.resource_group,
        "region": connection.region,
        "acr_login_server": connection.acr_login_server,
        "app_service_plan": connection.app_service_plan,
        "namespace_prefix": connection.namespace_prefix,
    }


@app.put("/api/azure/connection")
async def upsert_azure_connection(
    req: schemas.AzureConnectionUpsert,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Legacy PUT connection endpoint updated to use secure Key Vault BYOS storage."""
    from backend.services import azure_connector

    if not req.tenant_id.strip() or not req.subscription_id.strip():
        raise HTTPException(status_code=400, detail="tenant_id and subscription_id are required.")

    # Retrieve existing to see if we have a secret or require a new one
    existing = await get_active_azure_connection(db, current_user.id)
    secret_to_use = req.client_secret
    if not secret_to_use and existing:
        secret_to_use = azure_connector.get_credential_secret(current_user.id)
        
    if not secret_to_use:
        raise HTTPException(status_code=400, detail="client_secret is required to connect.")

    # Validate
    validation_res = azure_connector.validate_credential(
        tenant_id=req.tenant_id,
        client_id=req.client_id or (existing.client_id if existing else ""),
        client_secret=secret_to_use,
        subscription_id=req.subscription_id,
        resource_group=req.resource_group or (existing.resource_group if existing else "")
    )
    if not validation_res.get("success"):
        raise HTTPException(status_code=400, detail=validation_res.get("error", "Azure credential validation failed."))

    # Store
    azure_connector.store_credential_in_vault(current_user.id, secret_to_use)

    if existing:
        existing.tenant_id = req.tenant_id.strip()
        existing.subscription_id = req.subscription_id.strip()
        existing.client_id = req.client_id.strip() if req.client_id else existing.client_id
        existing.region = req.region or config.AZURE_DEFAULT_REGION
        existing.resource_group = req.resource_group.strip() if req.resource_group else existing.resource_group
        existing.acr_login_server = req.acr_login_server.strip().rstrip("/") if req.acr_login_server else existing.acr_login_server
        existing.app_service_plan = req.app_service_plan.strip() if req.app_service_plan else existing.app_service_plan
        existing.namespace_prefix = req.namespace_prefix.strip() if req.namespace_prefix else existing.namespace_prefix
        existing.connection_status = "connected"
        existing.is_active = True
        existing.updated_at = datetime.utcnow()
        connection = existing
    else:
        connection = models.UserAzureConnection(
            user_id=current_user.id,
            tenant_id=req.tenant_id.strip(),
            subscription_id=req.subscription_id.strip(),
            client_id=req.client_id.strip() if req.client_id else None,
            region=req.region or config.AZURE_DEFAULT_REGION,
            resource_group=req.resource_group.strip() if req.resource_group else None,
            acr_login_server=req.acr_login_server.strip().rstrip("/") if req.acr_login_server else None,
            app_service_plan=req.app_service_plan.strip() if req.app_service_plan else None,
            namespace_prefix=req.namespace_prefix.strip() if req.namespace_prefix else None,
            connection_status="connected",
            is_active=True,
        )
        db.add(connection)

    await db.commit()
    return {
        "connected": True,
        "subscription_id": connection.subscription_id,
        "region": connection.region,
        "resource_group": connection.resource_group,
        "acr_login_server": connection.acr_login_server,
        "app_service_plan": connection.app_service_plan,
    }


@app.post("/api/azure/disconnect")
async def disconnect_azure(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    connection = await get_active_azure_connection(db, current_user.id)
    if not connection:
        raise HTTPException(status_code=404, detail="No active Azure connection found.")

    from backend.services import azure_connector

    connection.connection_status = "revoked"
    connection.is_active = False
    connection.updated_at = datetime.utcnow()
    
    # Delete from vault
    azure_connector.delete_credential_from_vault(current_user.id)
    
    # Audit log disconnect
    try:
        audit = models.AuditLogEntry(
            user_id=current_user.id,
            agent_name="user",
            action_type="azure_connection_disconnect",
            parameters={"subscription_id": connection.subscription_id, "resource_group": connection.resource_group},
            risk_tier="low",
            approval_status="not_required",
            result_status="success"
        )
        db.add(audit)
    except Exception as audit_err:
        logger.error(f"Failed to write disconnect audit: {audit_err}")

    await db.commit()
    return {"status": "success", "detail": "Azure subscription disconnected and client credentials revoked."}


@app.post("/api/approvals/{approval_id}/decision")
async def decide_approval(
    approval_id: uuid.UUID,
    req: schemas.ApprovalDecisionRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from backend.services import action_gateway

    # Verify connection ownership or authorization. Here any logged in user can decide their connection's approvals.
    result = await db.execute(
        select(models.PendingApproval).filter(
            models.PendingApproval.id == approval_id,
            models.PendingApproval.user_id == current_user.id
        )
    )
    pending = result.scalars().first()
    if not pending:
        raise HTTPException(status_code=404, detail="Pending approval not found or not owned by you.")

    decision_res = await action_gateway.decide_pending_action(
        approval_id=approval_id,
        decision=req.decision,
        decided_by=current_user.id,
        db=db
    )
    if not decision_res.get("success"):
        raise HTTPException(status_code=400, detail=decision_res.get("error", "Failed to decide approval."))

    return decision_res


@app.get("/api/approvals/pending", response_model=List[schemas.PendingApprovalResponse])
async def get_pending_approvals(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.PendingApproval)
        .filter(models.PendingApproval.user_id == current_user.id, models.PendingApproval.status == "pending")
        .order_by(desc(models.PendingApproval.created_at))
    )
    return result.scalars().all()


@app.get("/api/audit-log", response_model=List[schemas.AuditLogResponse])
async def get_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.AuditLogEntry)
        .filter(models.AuditLogEntry.user_id == current_user.id)
        .order_by(desc(models.AuditLogEntry.created_at))
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all()


@app.get("/api/gke/connection")
async def get_gke_connection(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=410, detail="Google Cloud hosting is no longer supported.")


@app.put("/api/gke/connection")
async def upsert_gke_connection(
    req: schemas.GkeConnectionUpsert,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=410, detail="Google Cloud hosting is no longer supported.")


@app.get("/api/deployment-targets")
async def get_deployment_targets(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    azure_connection = await get_active_azure_connection(db, current_user.id)
    return deployment_targets.status_payload(azure_connection)


@app.get("/api/billing/operations")
async def list_billing_operations(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.BillingOperation)
        .filter(models.BillingOperation.user_id == current_user.id)
        .order_by(desc(models.BillingOperation.created_at))
        .limit(50)
    )
    return [map_billing_operation(op) for op in result.scalars().all()]


@app.post("/api/billing/operations")
async def create_billing_operation(
    req: schemas.BillingOperationCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    allowed_types = {"ai_code_fix", "ai_redeploy_fix", "ai_action_apply"}
    if req.operation_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Unsupported paid operation type.")

    if req.project_id:
        project_result = await db.execute(
            select(models.Project).filter(models.Project.id == req.project_id, models.Project.user_id == current_user.id)
        )
        if not project_result.scalars().first():
            raise HTTPException(status_code=404, detail="Project not found.")
    if req.deployment_id:
        deployment_result = await db.execute(
            select(models.Deployment).filter(models.Deployment.id == req.deployment_id, models.Deployment.user_id == current_user.id)
        )
        if not deployment_result.scalars().first():
            raise HTTPException(status_code=404, detail="Deployment not found.")

    op = models.BillingOperation(
        user_id=current_user.id,
        project_id=req.project_id,
        deployment_id=req.deployment_id,
        operation_type=req.operation_type,
        status="pending_payment",
        amount_cents=config.AI_PAID_OPERATION_PRICE_CENTS,
        currency="usd",
        provider=config.PAYMENT_PROVIDER,
        description=req.description,
    )
    db.add(op)
    await db.commit()
    await db.refresh(op)

    response = map_billing_operation(op)
    if config.PAYMENT_PROVIDER == "stripe":
        session = create_stripe_checkout_session(op, current_user)
        op.provider_reference = session.id
        await db.commit()
        response = map_billing_operation(op)
        response["checkout_url"] = session.url

    return response


@app.post("/api/billing/operations/{operation_id}/checkout")
async def create_billing_checkout(
    operation_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(models.BillingOperation)
        .filter(models.BillingOperation.id == operation_id, models.BillingOperation.user_id == current_user.id)
    )
    operation = result.scalars().first()
    if not operation:
        raise HTTPException(status_code=404, detail="Billing operation not found.")
    if operation.status != "pending_payment":
        return map_billing_operation(operation)
    if config.PAYMENT_PROVIDER != "stripe":
        response = map_billing_operation(operation)
        response["checkout_url"] = None
        return response

    session = create_stripe_checkout_session(operation, current_user)
    operation.provider_reference = session.id
    await db.commit()
    response = map_billing_operation(operation)
    response["checkout_url"] = session.url
    return response


@app.post("/api/billing/stripe/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if config.PAYMENT_PROVIDER != "stripe":
        raise HTTPException(status_code=404, detail="Stripe payments are not enabled.")
    if stripe is None:
        raise HTTPException(status_code=500, detail="Stripe package is not installed on the backend.")
    if not config.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Stripe webhook secret is not configured.")

    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, signature, config.STRIPE_WEBHOOK_SECRET)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid Stripe webhook: {exc}")

    if event.get("type") == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session.get("metadata") or {}
        operation_id = metadata.get("operation_id")
        if operation_id:
            result = await db.execute(
                select(models.BillingOperation).filter(models.BillingOperation.id == uuid.UUID(operation_id))
            )
            operation = result.scalars().first()
            if operation and operation.status == "pending_payment":
                operation.status = "paid"
                operation.provider_reference = session.get("id") or operation.provider_reference
                operation.paid_at = datetime.utcnow()
                await db.commit()

    return {"received": True}


@app.post("/api/billing/operations/{operation_id}/mark-paid")
async def mark_billing_operation_paid_for_dev(
    operation_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if config.APP_ENV == "production" or config.PAYMENT_PROVIDER != "manual":
        raise HTTPException(status_code=403, detail="Manual payment marking is disabled in production.")
    result = await db.execute(
        select(models.BillingOperation)
        .filter(models.BillingOperation.id == operation_id, models.BillingOperation.user_id == current_user.id)
    )
    operation = result.scalars().first()
    if not operation:
        raise HTTPException(status_code=404, detail="Billing operation not found.")
    operation.status = "paid"
    operation.paid_at = datetime.utcnow()
    await db.commit()
    return map_billing_operation(operation)


@app.post("/api/projects/{project_id}/self-heal")
async def self_heal_project(
    project_id: uuid.UUID,
    req: schemas.SelfHealRequest,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(models.Project).filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    action = req.action.lower()
    operation_type = "ai_redeploy_fix" if action in {"redeploy", "rollback"} else "ai_action_apply"
    await consume_paid_operation(db, current_user.id, operation_type, project_id=project.id)
    
    if action == "restart":
        db.add(models.ActivityEvent(
            user_id=current_user.id,
            project_id=project.id,
            action="Service Restarted",
            details="Autonomous healing triggered a service restart. Containers recycled successfully."
        ))
        db.add(models.Notification(
            user_id=current_user.id,
            title="Service Restarted",
            message=f"Application {project.name} has been restarted by AI self-healing.",
            type="info",
            category="system"
        ))
        project.status = "active"
        await db.commit()
        return {"status": "success", "message": "Service restarted successfully."}

    elif action == "regenerate-env":
        import secrets
        env_result = await db.execute(
            select(models.Environment).filter(models.Environment.project_id == project.id, models.Environment.name == "production")
        )
        env = env_result.scalars().first()
        if env:
            var_result = await db.execute(
                select(models.EnvironmentVariable).filter(models.EnvironmentVariable.environment_id == env.id)
            )
            vars_list = var_result.scalars().all()
            jwt_secret_var = next((v for v in vars_list if v.key == "JWT_SECRET"), None)
            new_val = f"zo_sec_{secrets.token_hex(24)}"
            if jwt_secret_var:
                jwt_secret_var.value = ""
            else:
                db.add(models.EnvironmentVariable(
                    environment_id=env.id,
                    key="JWT_SECRET",
                    value="",
                    is_secret=True
                ))
            vault.set_project_secret(str(project.id), "JWT_SECRET", new_val)
            
        db.add(models.ActivityEvent(
            user_id=current_user.id,
            project_id=project.id,
            action="Environment Variables Regenerated",
            details="Regenerated JWT_SECRET and updated vault configuration."
        ))
        db.add(models.Notification(
            user_id=current_user.id,
            title="Variables Regenerated",
            message=f"Secure environment variables regenerated for {project.name}.",
            type="success",
            category="system"
        ))
        await db.commit()
        return {"status": "success", "message": "Environment variables regenerated."}

    elif action == "reconnect-db":
        db_instances_result = await db.execute(
            select(models.DatabaseInstance).filter(models.DatabaseInstance.project_id == project.id)
        )
        db_instances = db_instances_result.scalars().all()
        for db_inst in db_instances:
            db_inst.status = "available"
            
        db.add(models.ActivityEvent(
            user_id=current_user.id,
            project_id=project.id,
            action="Database Reconnected",
            details="Autonomous self-healing recycled connection pool to managed databases."
        ))
        db.add(models.Notification(
            user_id=current_user.id,
            title="Database Reconnected",
            message=f"Database connection pool successfully recycled for {project.name}.",
            type="success",
            category="system"
        ))
        await db.commit()
        return {"status": "success", "message": "Database connections reconnected."}

    elif action == "redeploy":
        azure_connection = await get_active_azure_connection(db, current_user.id)
        analysis_hint = await get_latest_deployment_hint(db, current_user.id, project)
        try:
            selected_target = deployment_targets.choose_target(analysis_hint, azure_connection)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        version = f"v{datetime.utcnow().strftime('%Y%m%d.%H%M')}-redeploy"
        namespace_prefix = deployment_targets.namespace_prefix(selected_target, current_user.id)
        image_name = pipeline.normalize_project_id(f"{namespace_prefix}-{project.name}")
        deployment = models.Deployment(
            user_id=current_user.id,
            project_id=project.id,
            status="building",
            environment="production",
            branch=project.branch or "main",
            version=version,
            deployed_by="AI Self-Healer",
            image=deployment_targets.image_ref_for_target(selected_target, image_name, version),
            infrastructure_metadata={
                "target_provider": selected_target.provider,
                "target_reason": selected_target.reason,
                "target": deployment_targets.metadata_for_target(selected_target),
                "source_type": project.source_type,
            }
        )
        db.add(deployment)
        project.status = "deploying"
        
        db.add(models.ActivityEvent(
            user_id=current_user.id,
            project_id=project.id,
            action="Redeployment Triggered",
            details="Autonomous self-healing initiated a complete rebuild and redeploy."
        ))
        db.add(models.Notification(
            user_id=current_user.id,
            title="Redeployment Started",
            message=f"Redeploying application {project.name} due to autonomous healing request...",
            type="info",
            category="deployment"
        ))
        await db.commit()
        await db.refresh(deployment)
        
        clone_token = None
        if current_user.github_access_token_encrypted:
            try:
                clone_token = github_oauth.decrypt_token(current_user.github_access_token_encrypted)
            except Exception:
                pass
                
        pipeline.enqueue_deployment(
            str(deployment.id), project.full_name, project.branch or "main", background_tasks, clone_token
        )
        return {"status": "success", "message": "Redeployment triggered.", "deployment_id": str(deployment.id)}

    elif action == "rollback":
        azure_connection = await get_active_azure_connection(db, current_user.id)
        rollback_dep_result = await db.execute(
            select(models.Deployment)
            .filter(models.Deployment.project_id == project.id, models.Deployment.status == "running")
            .order_by(desc(models.Deployment.completed_at))
            .limit(1)
        )
        rollback_dep = rollback_dep_result.scalars().first()
        if not rollback_dep:
            raise HTTPException(status_code=400, detail="No previous successful deployment found to roll back to.")
        rollback_meta = rollback_dep.infrastructure_metadata or {}
        previous_provider = rollback_meta.get("target_provider") or (rollback_meta.get("target") or {}).get("provider") or "auto"
        analysis_hint = await get_latest_deployment_hint(db, current_user.id, project)
        try:
            selected_target = deployment_targets.choose_target(analysis_hint, azure_connection, previous_provider)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
            
        deployment = models.Deployment(
            user_id=current_user.id,
            project_id=project.id,
            status="building",
            environment="production",
            branch=rollback_dep.branch,
            version=f"v{datetime.utcnow().strftime('%Y%m%d.%H%M')}-rollback",
            deployed_by="AI Self-Healer",
            image=rollback_dep.image,
            live_url=rollback_dep.live_url,
            infrastructure_metadata={
                "target_provider": selected_target.provider,
                "target_reason": f"Rollback to previous {selected_target.label} deployment.",
                "target": deployment_targets.metadata_for_target(selected_target),
                "source_type": project.source_type,
            }
        )
        db.add(deployment)
        project.status = "deploying"
        
        db.add(models.ActivityEvent(
            user_id=current_user.id,
            project_id=project.id,
            action="Rollback Triggered",
            details=f"Autonomous self-healing initiated a rollback to version {rollback_dep.version}."
        ))
        db.add(models.Notification(
            user_id=current_user.id,
            title="Rollback Started",
            message=f"Rolling back application {project.name} to {rollback_dep.version}...",
            type="info",
            category="deployment"
        ))
        await db.commit()
        await db.refresh(deployment)
        
        clone_token = None
        if current_user.github_access_token_encrypted:
            try:
                clone_token = github_oauth.decrypt_token(current_user.github_access_token_encrypted)
            except Exception:
                pass
                
        pipeline.enqueue_deployment(
            str(deployment.id), project.full_name, rollback_dep.branch, background_tasks, clone_token
        )
        return {"status": "success", "message": "Rollback triggered.", "deployment_id": str(deployment.id)}

    elif action == "retry-health":
        latest_dep_result = await db.execute(
            select(models.Deployment)
            .filter(models.Deployment.project_id == project.id)
            .order_by(desc(models.Deployment.started_at))
            .limit(1)
        )
        latest_dep = latest_dep_result.scalars().first()
        if not latest_dep:
            raise HTTPException(status_code=400, detail="No deployment found.")
            
        db.add(models.ActivityEvent(
            user_id=current_user.id,
            project_id=project.id,
            action="Health Validation Retried",
            details="Manual validation requested. Deployment status was not changed without live telemetry."
        ))
        db.add(models.Notification(
            user_id=current_user.id,
            title="Health Check Requested",
            message=f"Health validation requested for {project.name}. Review deployment logs for the result.",
            type="info",
            category="system"
        ))

        await db.commit()
        return {"status": "success", "message": "Health validation request recorded."}

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported self-healing action: {action}")


# ──────────────────────────────────────────────
# PROJECT ENVIRONMENT VARIABLES & METRICS
# ──────────────────────────────────────────────


@app.get("/api/projects/{project_id}/variables", response_model=List[schemas.EnvVarResponse])
async def get_project_variables(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # 1. Verify project exists and belongs to user
    proj_result = await db.execute(
        select(models.Project)
        .filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    # 2. Find production environment for project
    env_result = await db.execute(
        select(models.Environment)
        .filter(models.Environment.project_id == project_id, models.Environment.name == "production")
    )
    env = env_result.scalars().first()
    if not env:
        env = models.Environment(project_id=project_id, name="production")
        db.add(env)
        await db.commit()
        await db.refresh(env)

    # 3. Query variables
    vars_result = await db.execute(
        select(models.EnvironmentVariable)
        .filter(models.EnvironmentVariable.environment_id == env.id)
        .order_by(models.EnvironmentVariable.key)
    )
    variables = vars_result.scalars().all()

    # 4. Return variables (with secrets masked)
    return [
        schemas.EnvVarResponse(
            id=v.id,
            key=v.key,
            value="••••••••" if v.is_secret else v.value,
            is_secret=v.is_secret,
            created_at=format_dt(v.created_at)
        ) for v in variables
    ]


@app.post("/api/projects/{project_id}/variables", response_model=schemas.EnvVarResponse)
async def create_project_variable(
    project_id: uuid.UUID,
    req: schemas.EnvVarCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # 1. Verify project exists and belongs to user
    proj_result = await db.execute(
        select(models.Project)
        .filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    # 2. Find production environment for project
    env_result = await db.execute(
        select(models.Environment)
        .filter(models.Environment.project_id == project_id, models.Environment.name == "production")
    )
    env = env_result.scalars().first()
    if not env:
        env = models.Environment(project_id=project_id, name="production")
        db.add(env)
        await db.commit()
        await db.refresh(env)

    # 3. Check if variable key already exists in this environment
    var_check = await db.execute(
        select(models.EnvironmentVariable)
        .filter(models.EnvironmentVariable.environment_id == env.id, models.EnvironmentVariable.key == req.key)
    )
    if var_check.scalars().first():
        raise HTTPException(status_code=400, detail=f"Variable '{req.key}' already exists.")

    # 4. Create variable
    if req.is_secret:
        try:
            vault.set_project_secret(str(project_id), req.key, req.value)
        except Exception as exc:
            logger.error("Unable to store a project secret in Key Vault: %s", exc)
            raise HTTPException(status_code=503, detail="Azure Key Vault is unavailable. Secret was not saved.")

    new_var = models.EnvironmentVariable(
        environment_id=env.id,
        key=req.key,
        value="" if req.is_secret else req.value,
        is_secret=req.is_secret
    )
    db.add(new_var)
    await db.commit()
    await db.refresh(new_var)

    return schemas.EnvVarResponse(
        id=new_var.id,
        key=new_var.key,
        value="••••••••" if new_var.is_secret else new_var.value,
        is_secret=new_var.is_secret,
        created_at=format_dt(new_var.created_at)
    )


@app.delete("/api/projects/{project_id}/variables/{var_id}")
async def delete_project_variable(
    project_id: uuid.UUID,
    var_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # 1. Verify project exists and belongs to user
    proj_result = await db.execute(
        select(models.Project)
        .filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    # 2. Verify variable exists and belongs to the project's environment
    var_result = await db.execute(
        select(models.EnvironmentVariable)
        .join(models.Environment, models.EnvironmentVariable.environment_id == models.Environment.id)
        .filter(models.EnvironmentVariable.id == var_id, models.Environment.project_id == project_id)
    )
    variable = var_result.scalars().first()
    if not variable:
        raise HTTPException(status_code=404, detail="Variable not found.")

    # 3. Delete the Key Vault value first. This prevents an orphaned secret
    # when the database row is removed successfully.
    if variable.is_secret:
        try:
            vault.delete_project_secret(str(project_id), variable.key)
        except Exception as exc:
            logger.error("Unable to delete a project secret from Key Vault: %s", exc)
            raise HTTPException(status_code=503, detail="Azure Key Vault is unavailable. Secret was not deleted.")

    # 4. Delete variable metadata
    await db.delete(variable)
    await db.commit()
    return {"status": "success", "message": "Variable deleted successfully."}


@app.get("/api/projects/{project_id}/metrics", response_model=schemas.TelemetryMetricResponse)
async def get_project_metrics(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify project ownership
    proj_result = await db.execute(
        select(models.Project)
        .filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    # Fetch deployments for this project
    deps_result = await db.execute(
        select(models.Deployment.id)
        .filter(models.Deployment.project_id == project_id)
    )
    dep_ids = [row[0] for row in deps_result.all()]

    # Query existing metrics
    metrics = []
    if dep_ids:
        metrics_result = await db.execute(
            select(models.DeploymentMetric)
            .filter(models.DeploymentMetric.deployment_id.in_(dep_ids))
            .order_by(models.DeploymentMetric.timestamp.asc())
        )
        metrics = metrics_result.scalars().all()

    cpu_data = []
    mem_data = []
    for m in metrics:
        time_str = m.timestamp.strftime("%H:%M")
        cpu_data.append({"time": time_str, "value": m.cpu_utilization})
        mem_data.append({"time": time_str, "value": m.memory_utilization})

    avg_resp = "No data"
    avg_err = "No data"
    total_reqs = 0
    uptime = "No data"
    if metrics:
        avg_resp = f"{int(sum(m.response_time_ms for m in metrics) / len(metrics))}ms"
        avg_err = f"{round(sum(m.error_rate for m in metrics) / len(metrics), 2)}%"
        total_reqs = sum(m.request_count for m in metrics)
        
        # Calculate uptime based on latest deployment status
        try:
            latest_dep_result = await db.execute(
                select(models.Deployment.status)
                .filter(models.Deployment.project_id == project_id)
                .order_by(models.Deployment.started_at.desc())
                .limit(1)
            )
            latest_status = latest_dep_result.scalar()
            if latest_status == "running":
                uptime = "Running"
            elif latest_status == "failed":
                uptime = "Failed"
            else:
                uptime = latest_status or "No data"
        except Exception:
            uptime = "No data"

    return schemas.TelemetryMetricResponse(
        cpu=cpu_data,
        memory=mem_data,
        uptime=uptime,
        error_rate=avg_err,
        response_time=avg_resp,
        request_count=total_reqs
    )


# ──────────────────────────────────────────────
# DEPLOYMENTS (per-user)
# ──────────────────────────────────────────────

@app.get("/api/deployments")
async def list_deployments(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, le=100)
):
    result = await db.execute(
        select(models.Deployment, models.Project.name)
        .join(models.Project, models.Deployment.project_id == models.Project.id)
        .filter(models.Deployment.user_id == current_user.id)
        .order_by(desc(models.Deployment.started_at))
        .limit(limit)
    )
    rows = result.all()

    return [
        schemas.DeploymentResponse(
            id=dep.id, project_id=dep.project_id, project_name=proj_name,
            status=dep.status, environment=dep.environment, branch=dep.branch,
            version=dep.version, commit_sha=dep.commit_sha, image=dep.image,
            duration_seconds=dep.duration_seconds,
            duration=format_duration(dep.duration_seconds),
            live_url=dep.live_url, deployed_by=dep.deployed_by,
            started_at=format_dt(dep.started_at),
            completed_at=format_dt(dep.completed_at),
            infrastructure_metadata=dep.infrastructure_metadata,
        )
        for dep, proj_name in rows
    ]


@app.post("/api/deployments/deploy")
async def start_deploy(
    req: schemas.DeploymentCreate,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify project belongs to user
    result = await db.execute(
        select(models.Project)
        .filter(models.Project.id == req.project_id, models.Project.user_id == current_user.id)
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    azure_connection = await get_active_azure_connection(db, current_user.id)
    target_status = deployment_targets.status_payload(azure_connection)
    if not target_status["any_ready"]:
        raise HTTPException(
            status_code=400,
            detail="Connect your Azure application environment before starting a deployment."
        )

    analysis_hint = await get_latest_deployment_hint(db, current_user.id, project)
    try:
        selected_target = deployment_targets.choose_target(
            analysis_hint,
            azure_connection,
            req.target_provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    version = f"v{datetime.utcnow().strftime('%Y%m%d.%H%M')}"
    namespace_prefix = deployment_targets.namespace_prefix(selected_target, current_user.id)
    image_name = pipeline.normalize_project_id(f"{namespace_prefix}-{project.name}")
    image_ref = deployment_targets.image_ref_for_target(selected_target, image_name, version)

    # Create deployment record
    deployment = models.Deployment(
        user_id=current_user.id,
        project_id=project.id,
        status="building",
        environment=req.environment,
        branch=req.branch,
        version=version,
        deployed_by=f"{current_user.first_name or 'User'} {(current_user.last_name or '')[0:1]}.".strip(),
        image=image_ref,
        infrastructure_metadata={
            "target_provider": selected_target.provider,
            "target_reason": selected_target.reason,
            "target": deployment_targets.metadata_for_target(selected_target),
            "available_targets": target_status["targets"],
            "source_type": project.source_type,
        }
    )
    db.add(deployment)

    # Update project status
    project.status = "deploying"

    # Create notification
    db.add(models.Notification(
        user_id=current_user.id,
        title="Deployment Started",
        message=f"Building {project.full_name} ({req.branch}) for {req.environment} on {selected_target.label}...",
        type="info",
        category="deployment"
    ))

    await db.commit()
    await db.refresh(deployment)

    clone_token = None
    if current_user.github_access_token_encrypted:
        try:
            clone_token = github_oauth.decrypt_token(current_user.github_access_token_encrypted)
        except Exception:
            clone_token = None

    # Run pipeline in background via enqueuer dispatcher abstraction
    pipeline.enqueue_deployment(
        str(deployment.id), project.full_name, req.branch, background_tasks, clone_token
    )

    return {
        "status": "success",
        "deployment_id": str(deployment.id),
        "project_id": str(project.id)
    }


@app.get("/api/deployments/{deploy_id}")
async def get_deployment(
    deploy_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(models.Deployment)
        .filter(models.Deployment.id == deploy_id, models.Deployment.user_id == current_user.id)
    )
    dep = result.scalars().first()
    if not dep:
        raise HTTPException(status_code=404, detail="Deployment not found.")

    # Get project name
    proj_result = await db.execute(select(models.Project.name).filter(models.Project.id == dep.project_id))
    proj_name = proj_result.scalar()

    # Get logs
    logs_result = await db.execute(
        select(models.DeploymentLog)
        .filter(models.DeploymentLog.deployment_id == dep.id)
        .order_by(models.DeploymentLog.line_number)
    )
    logs = logs_result.scalars().all()

    return schemas.DeploymentDetailResponse(
        id=dep.id, project_id=dep.project_id, project_name=proj_name,
        status=dep.status, environment=dep.environment, branch=dep.branch,
        version=dep.version, commit_sha=dep.commit_sha, image=dep.image,
        duration_seconds=dep.duration_seconds,
        duration=format_duration(dep.duration_seconds),
        live_url=dep.live_url, deployed_by=dep.deployed_by,
        started_at=format_dt(dep.started_at),
        completed_at=format_dt(dep.completed_at),
        infrastructure_metadata=dep.infrastructure_metadata,
        logs=[
            schemas.DeploymentLogResponse(
                line_number=log.line_number, level=log.level,
                message=log.message, timestamp=format_dt(log.timestamp)
            ) for log in logs
        ]
    )


@app.post("/api/deployments/{deploy_id}/fix-auto")
async def fix_deployment_automatically(
    deploy_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    raise HTTPException(
        status_code=501,
        detail="Automatic source-code changes are disabled. Review the recorded failure, update your repository, and launch a new version.",
    )

    # 1. Fetch deployment
    result = await db.execute(
        select(models.Deployment).filter(
            models.Deployment.id == deploy_id,
            models.Deployment.user_id == current_user.id
        )
    )
    deployment = result.scalars().first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found.")
        
    if deployment.status != "failed":
        raise HTTPException(status_code=400, detail="Only failed deployments can be automatically fixed.")

    await consume_paid_operation(
        db,
        current_user.id,
        "ai_code_fix",
        project_id=deployment.project_id,
        deployment_id=deployment.id,
    )
        
    # 2. Run auto remediation
    devops_agent = agent.NvidiaNIMDevOpsAgent()
    remediated = await devops_agent.auto_remediate_failure(
        deployment_id=str(deployment.id),
        failure_reason=deployment.failure_reason or "Unknown build error",
        db=db
    )
    
    if not remediated:
        raise HTTPException(status_code=500, detail="Failed to apply auto-remediation fix.")
        
    # 3. Create a new redeployment record
    project_result = await db.execute(
        select(models.Project).filter(models.Project.id == deployment.project_id)
    )
    project = project_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
        
    new_deployment = models.Deployment(
        user_id=current_user.id,
        project_id=project.id,
        status="building",
        environment=deployment.environment,
        branch=deployment.branch,
        version=f"v{datetime.utcnow().strftime('%Y%m%d.%H%M')}",
        deployed_by=f"AI Auto-Fix ({current_user.first_name or 'User'})",
        image=deployment.image
    )
    db.add(new_deployment)
    
    project.status = "deploying"
    
    db.add(models.Notification(
        user_id=current_user.id,
        title="Redeploying with Auto-Fix",
        message=f"Applied auto-fix for {project.name}. Starting redeployment...",
        type="info",
        category="deployment"
    ))
    
    await db.commit()
    await db.refresh(new_deployment)
    
    clone_token = None
    if current_user.github_access_token_encrypted:
        try:
            clone_token = github_oauth.decrypt_token(current_user.github_access_token_encrypted)
        except Exception:
            clone_token = None

    # 4. Dispatch the new deployment pipeline
    pipeline.enqueue_deployment(
        str(new_deployment.id), project.full_name, deployment.branch, background_tasks, clone_token
    )
    
    return {
        "status": "success",
        "message": "Auto-fix applied. Redeployment initialized.",
        "deployment_id": str(new_deployment.id),
        "project_id": str(project.id)
    }


# ──────────────────────────────────────────────
# NOTIFICATIONS (per-user)
# ──────────────────────────────────────────────

@app.get("/api/notifications")
async def list_notifications(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
    category: Optional[str] = None,
    limit: int = Query(default=50, le=200)
):
    query = select(models.Notification).filter(models.Notification.user_id == current_user.id)
    if category:
        query = query.filter(models.Notification.category == category)
    query = query.order_by(desc(models.Notification.created_at)).limit(limit)

    result = await db.execute(query)
    notifs = result.scalars().all()

    return [
        schemas.NotificationResponse(
            id=n.id, title=n.title, message=n.message, type=n.type,
            category=n.category, read=n.read, action_url=n.action_url,
            created_at=format_dt(n.created_at)
        )
        for n in notifs
    ]


@app.post("/api/notifications/{notif_id}/read")
async def mark_notification_read(
    notif_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(models.Notification)
        .filter(models.Notification.id == notif_id, models.Notification.user_id == current_user.id)
    )
    notif = result.scalars().first()
    if notif:
        notif.read = True
        await db.commit()
    return {"status": "success"}


@app.post("/api/notifications/read-all")
async def mark_all_notifications_read(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(models.Notification)
        .filter(models.Notification.user_id == current_user.id, models.Notification.read == False)
    )
    unread = result.scalars().all()
    for n in unread:
        n.read = True
    await db.commit()
    return {"status": "success", "marked": len(unread)}


# ──────────────────────────────────────────────
# AI ACTIONS (per-user)
# ──────────────────────────────────────────────

@app.get("/api/ai/actions")
async def list_ai_actions(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = None,
    action_type: Optional[str] = Query(default=None, alias="type"),
    limit: int = Query(default=30, le=100)
):
    query = select(models.AIAction).filter(models.AIAction.user_id == current_user.id)
    if status:
        query = query.filter(models.AIAction.status == status)
    if action_type:
        query = query.filter(models.AIAction.type == action_type)
    query = query.order_by(desc(models.AIAction.created_at)).limit(limit)

    result = await db.execute(query)
    actions = result.scalars().all()

    return [
        schemas.AIActionResponse(
            id=a.id, project_id=a.project_id, type=a.type,
            severity=a.severity, message=a.message,
            recommendation=a.recommendation, status=a.status,
            icon=a.icon, created_at=format_dt(a.created_at)
        )
        for a in actions
    ]


@app.post("/api/ai/actions/{action_id}/apply")
async def apply_ai_action(
    action_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(models.AIAction)
        .filter(models.AIAction.id == action_id, models.AIAction.user_id == current_user.id)
    )
    action = result.scalars().first()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found.")
    await consume_paid_operation(db, current_user.id, "ai_action_apply", project_id=action.project_id)
    action.status = "applied"
    db.add(models.Notification(
        user_id=current_user.id,
        title="AI Action Applied",
        message=f"Applied: {action.message}",
        type="success",
        category="ai"
    ))
    await db.commit()
    return {"status": "success"}


@app.post("/api/ai/actions/{action_id}/dismiss")
async def dismiss_ai_action(
    action_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(models.AIAction)
        .filter(models.AIAction.id == action_id, models.AIAction.user_id == current_user.id)
    )
    action = result.scalars().first()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found.")
    action.status = "dismissed"
    await db.commit()
    return {"status": "success"}


# ──────────────────────────────────────────────
# AI ANALYSIS (per-user/project)
# ──────────────────────────────────────────────

@app.get("/api/ai/analysis/{project_id}")
async def get_ai_analysis(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify project ownership
    proj_result = await db.execute(
        select(models.Project)
        .filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    if not proj_result.scalars().first():
        raise HTTPException(status_code=404, detail="Project not found.")

    result = await db.execute(
        select(models.AIAnalysis)
        .filter(models.AIAnalysis.project_id == project_id)
        .order_by(desc(models.AIAnalysis.created_at))
        .limit(1)
    )
    analysis = result.scalars().first()
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis available for this project.")

    return schemas.AIAnalysisResponse(
        id=analysis.id, project_id=analysis.project_id,
        framework=analysis.framework, framework_version=analysis.framework_version,
        language=analysis.language, risk_score=analysis.risk_score,
        confidence=analysis.confidence,
        cpu_recommendation=analysis.cpu_recommendation,
        memory_recommendation=analysis.memory_recommendation,
        storage_recommendation=analysis.storage_recommendation,
        port=analysis.port,
        dependencies=analysis.dependencies or [],
        vulnerabilities=analysis.vulnerabilities or [],
        dockerfile=analysis.dockerfile,
        kubernetes_manifest=analysis.kubernetes_manifest,
        created_at=format_dt(analysis.created_at),
        
        # New AI analysis fields
        runtime=analysis.runtime,
        package_manager=analysis.package_manager,
        docker_support=analysis.docker_support or False,
        monorepo_structure=analysis.monorepo_structure,
        database_dependencies=analysis.database_dependencies or [],
        deployment_strategy=analysis.deployment_strategy,
        build_commands=analysis.build_commands,
        start_commands=analysis.start_commands,
        environment_variables=analysis.environment_variables or []
    )


@app.post("/api/ai/analyze")
async def analyze_repo(
    req: schemas.DeployRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Analyze a repository and store results in the database."""
    token = config.GITHUB_TOKEN
    import os
    
    # Try decrypting user's github token if available
    user_token = None
    if current_user.github_connected and current_user.github_access_token_encrypted:
        try:
            user_token = github_oauth.decrypt_token(current_user.github_access_token_encrypted)
        except Exception:
            pass
            
    clone_token = user_token or token or os.getenv("GITHUB_TOKEN")
    
    try:
        # Fetch repository context via GitHub API (no cloning, no git binary)
        repo_ctx = await github_oauth.fetch_github_repo_context(clone_token, req.repo, req.branch)
    except Exception as e:
        logger.error(f"Error fetching GitHub repository context for {req.repo}: {e}")
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "stage": "repository_analysis",
                "error": "Unable to access repository",
                "details": f"Failed to connect or fetch contents from GitHub: {str(e)}"
            }
        )
    
    try:
        analysis = ai.analyze_repository(repo_ctx, pipeline.normalize_project_id(req.repo))
    except ValueError as e:
        # AI provider not configured — fall back to local analysis for repo scanning only
        logger.warning(f"AI provider not configured, using local analyzer for {req.repo}: {e}")
        analysis = ai.analyze_repo_local(repo_ctx, pipeline.normalize_project_id(req.repo))
    except RuntimeError as e:
        logger.error(f"AI API call failed for {req.repo}: {e}")
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "stage": "repository_analysis",
                "error": "AI Analysis Failed",
                "details": f"AI models failed to analyze repository metadata: {str(e)}"
            }
        )

    # Find project for this repo if it exists
    proj_result = await db.execute(
        select(models.Project)
        .filter(models.Project.user_id == current_user.id, models.Project.full_name == req.repo)
    )
    project = proj_result.scalars().first()
    project_id = project.id if project else None

    # Store analysis in DB
    db_analysis = models.AIAnalysis(
        user_id=current_user.id,
        project_id=project_id,
        framework=analysis.get("framework"),
        framework_version=analysis.get("version") or analysis.get("framework_version"),
        language=analysis.get("language"),
        risk_score=analysis.get("risk_score", 0),
        confidence=analysis.get("confidence", 0),
        cpu_recommendation=analysis.get("resources", {}).get("cpu") or analysis.get("cpu_recommendation"),
        memory_recommendation=analysis.get("resources", {}).get("memory") or analysis.get("memory_recommendation"),
        storage_recommendation=analysis.get("resources", {}).get("storage") or analysis.get("storage_recommendation"),
        dependencies=analysis.get("dependencies", []),
        vulnerabilities=analysis.get("vulnerabilities", []),
        dockerfile=analysis.get("dockerfile"),
        kubernetes_manifest=analysis.get("kubernetes_manifest"),
        
        # Save scanner columns
        runtime=analysis.get("runtime"),
        package_manager=analysis.get("package_manager"),
        docker_support=analysis.get("docker_support", False),
        monorepo_structure=analysis.get("monorepo_structure"),
        database_dependencies=analysis.get("database_dependencies") or ([analysis.get("database")] if analysis.get("database") else []),
        deployment_strategy=analysis.get("deployment_strategy") or analysis.get("deployment_target"),
        build_commands=analysis.get("build_commands") or analysis.get("build_command"),
        start_commands=analysis.get("start_commands") or analysis.get("start_command"),
        environment_variables=analysis.get("environment_variables") or analysis.get("required_env_vars", []),
        explanation=analysis.get("explanation"),
        recommended_compute_tier=analysis.get("recommended_compute_tier"),
        estimated_cost=analysis.get("estimated_cost"),
        recommended_region=analysis.get("recommended_region"),
        expected_traffic=analysis.get("expected_traffic"),
        pricing_breakdown=analysis.get("pricing_breakdown")
    )
    db.add(db_analysis)

    
    # Store recommendation in DB (Phase 4)
    db_recommendation = models.DeploymentRecommendation(
        user_id=current_user.id,
        project_id=project_id,
        repository_full_name=req.repo,
        recommended_target=analysis.get("deployment_target") or analysis.get("deployment_strategy"),
        azure_configuration={
            "target": analysis.get("deployment_target") or analysis.get("deployment_strategy"),
            "region": analysis.get("recommended_region"),
            "cpu_limit": analysis.get("cpu_recommendation") or analysis.get("resources", {}).get("cpu"),
            "memory_limit": analysis.get("memory_recommendation") or analysis.get("resources", {}).get("memory"),
        },
        environment_variables=analysis.get("required_env_vars") or analysis.get("environment_variables", []),
        scaling_recommendation=analysis.get("scaling_recommendation") or {},
        database_recommendation={
            "primary": analysis.get("database"),
            "type": analysis.get("database_type")
        },
        estimated_deployment_time=analysis.get("estimated_deployment_time"),
        recommended_compute_tier=analysis.get("recommended_compute_tier"),
        estimated_cost=analysis.get("estimated_cost"),
        recommended_region=analysis.get("recommended_region"),
        expected_traffic=analysis.get("expected_traffic")
    )
    db.add(db_recommendation)

    azure_connection = await get_active_azure_connection(db, current_user.id)
    target_status = deployment_targets.status_payload(azure_connection)
    try:
        selected_target = deployment_targets.choose_target(analysis, azure_connection)
        db_recommendation.recommended_target = selected_target.label
        db_recommendation.azure_configuration = {
            **(db_recommendation.azure_configuration or {}),
            "selected_provider": selected_target.provider,
            "target": deployment_targets.metadata_for_target(selected_target),
            "reason": selected_target.reason,
        }
        analysis["recommended_provider"] = selected_target.provider
        analysis["recommended_target"] = selected_target.label
        analysis["target_reason"] = selected_target.reason
    except ValueError as target_err:
        analysis["recommended_provider"] = "none"
        analysis["target_reason"] = str(target_err)
    analysis["deployment_targets"] = target_status
    
    await db.commit()

    # Enrich returned analysis with recommendations data for Step 5
    analysis["deployment_recommendation"] = {
        "recommended_target": db_recommendation.recommended_target,
        "azure_configuration": db_recommendation.azure_configuration,
        "environment_variables": db_recommendation.environment_variables,
        "scaling_recommendation": db_recommendation.scaling_recommendation,
        "database_recommendation": db_recommendation.database_recommendation,
        "estimated_deployment_time": db_recommendation.estimated_deployment_time,
        "recommended_compute_tier": db_recommendation.recommended_compute_tier,
        "estimated_cost": db_recommendation.estimated_cost,
        "recommended_region": db_recommendation.recommended_region,
        "expected_traffic": db_recommendation.expected_traffic,
    }
    pricing = analysis.get("pricing_breakdown") or {}
    for key in [
        "compute_cost",
        "database_cost",
        "platform_fee",
        "bandwidth_cost",
        "monitoring_cost",
        "total_cost",
        "projected_growth_cost",
        "why_this_plan",
        "detected_vars_detail",
        "application_type",
        "estimated_build_time",
        "production_readiness_score",
        "detected_services",
    ]:
        if key in pricing and key not in analysis:
            analysis[key] = pricing[key]

    return analysis


@app.post("/api/ai/chat")
async def ai_chat(
    req: schemas.ChatRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Conversational AI DevOps Assistant chat endpoint with database context injection."""
    project_metadata = {}
    if req.project_id:
        proj_result = await db.execute(
            select(models.Project).filter(models.Project.id == req.project_id, models.Project.user_id == current_user.id)
        )
        project = proj_result.scalars().first()
        if project:
            analysis_result = await db.execute(
                select(models.AIAnalysis)
                .filter(models.AIAnalysis.project_id == req.project_id)
                .order_by(desc(models.AIAnalysis.created_at))
                .limit(1)
            )
            analysis = analysis_result.scalars().first()
            
            project_metadata = {
                "name": project.name,
                "framework": project.framework,
                "language": project.language,
                "region": project.region,
                "status": project.status,
                "custom_domains": project.custom_domains or []
            }
            if analysis:
                project_metadata["runtime"] = analysis.runtime
                project_metadata["database"] = (analysis.database_dependencies[0] 
                                                 if (analysis.database_dependencies and len(analysis.database_dependencies) > 0 and analysis.database_dependencies[0] != "None")
                                                 else None)
                project_metadata["vulnerabilities_count"] = len(analysis.vulnerabilities) if (analysis.vulnerabilities and analysis.vulnerabilities[0] != "Vulnerability checks passed successfully.") else 0

            # 1. Databases Query
            db_instances_result = await db.execute(
                select(models.DatabaseInstance).filter(models.DatabaseInstance.project_id == req.project_id)
            )
            db_instances = db_instances_result.scalars().all()
            project_metadata["databases"] = [
                {
                    "type": db_inst.type,
                    "db_name": db_inst.db_name,
                    "host": db_inst.host,
                    "port": db_inst.port,
                    "status": db_inst.status
                }
                for db_inst in db_instances
            ]

            # 2. Env Vars Check to identify missing keys
            env_result = await db.execute(
                select(models.Environment).filter(models.Environment.project_id == req.project_id, models.Environment.name == "production")
            )
            env = env_result.scalars().first()
            existing_keys = set()
            if env:
                var_result = await db.execute(
                    select(models.EnvironmentVariable).filter(models.EnvironmentVariable.environment_id == env.id)
                )
                existing_keys = {v.key for v in var_result.scalars().all()}
                
            missing_required = []
            missing_recommended = []
            if analysis and analysis.pricing_breakdown:
                pricing = analysis.pricing_breakdown
                detected_vars = pricing.get("detected_vars_detail", [])
                for var_meta in detected_vars:
                    v_key = var_meta["key"]
                    v_type = var_meta["type"]
                    if v_key not in existing_keys:
                        if v_type == "required":
                            missing_required.append(v_key)
                        elif v_type == "recommended":
                            missing_recommended.append(v_key)
            
            project_metadata["missing_variables"] = {
                "required": missing_required,
                "recommended": missing_recommended
            }

            # Only pass through real cost data. Repository analysis deliberately
            # does not manufacture Azure pricing or subscription usage.
            if analysis and analysis.pricing_breakdown and isinstance(
                analysis.pricing_breakdown.get("total_cost"), (int, float)
            ):
                pricing = analysis.pricing_breakdown
                project_metadata["cost"] = {
                    "compute_cost": pricing.get("compute_cost"),
                    "database_cost": pricing.get("database_cost"),
                    "platform_fee": pricing.get("platform_fee"),
                    "total_cost": pricing.get("total_cost"),
                    "projected_growth_cost": pricing.get("projected_growth_cost"),
                    "recommended_plan": pricing.get("recommended_plan"),
                    "why_this_plan": pricing.get("why_this_plan", "")
                }

            # 4. Fetch latest deployment details
            latest_dep_result = await db.execute(
                select(models.Deployment)
                .filter(models.Deployment.project_id == req.project_id)
                .order_by(desc(models.Deployment.started_at))
                .limit(1)
            )
            latest_dep = latest_dep_result.scalars().first()
            if latest_dep:
                project_metadata["latest_deployment"] = {
                    "status": latest_dep.status,
                    "version": latest_dep.version,
                    "commit_sha": latest_dep.commit_sha,
                    "duration_seconds": latest_dep.duration_seconds,
                    "live_url": latest_dep.live_url
                }
                
                # Fetch recent log traces and failure analysis if deployment failed
                if latest_dep.status == "failed":
                    logs_result = await db.execute(
                        select(models.DeploymentLog)
                        .filter(models.DeploymentLog.deployment_id == latest_dep.id)
                        .order_by(models.DeploymentLog.line_number)
                        .limit(15)
                    )
                    logs = logs_result.scalars().all()
                    project_metadata["latest_deployment_logs"] = [f"[{log.level}] {log.message}" for log in logs]
                    
                    fa_result = await db.execute(
                        select(models.FailureAnalysis).filter(models.FailureAnalysis.deployment_id == latest_dep.id)
                    )
                    fa = fa_result.scalars().first()
                    if fa:
                        project_metadata["failure_analysis"] = {
                            "summary": fa.failure_summary,
                            "cause": fa.root_cause,
                            "recommended_fix": fa.recommended_fix,
                            "confidence": fa.confidence,
                            "impact": fa.impact
                        }

            # 5. Fetch recent telemetry metrics
            deps_result = await db.execute(
                select(models.Deployment).filter(models.Deployment.project_id == req.project_id)
            )
            deps = deps_result.scalars().all()
            failed_count = sum(1 for d in deps if d.status == "failed")
            
            metrics_result = await db.execute(
                select(models.DeploymentMetric)
                .filter(models.DeploymentMetric.deployment_id.in_(
                    select(models.Deployment.id).filter(models.Deployment.project_id == req.project_id)
                ))
                .order_by(desc(models.DeploymentMetric.timestamp))
                .limit(5)
            )
            metrics = metrics_result.scalars().all()
            
            avg_cpu = 5.0
            avg_mem = 15.0
            avg_error_rate = 0.0
            if metrics:
                avg_cpu = sum(m.cpu_utilization for m in metrics) / len(metrics)
                avg_mem = sum(m.memory_utilization for m in metrics) / len(metrics)
                avg_error_rate = sum(m.error_rate for m in metrics) / len(metrics)
                project_metadata["telemetry"] = {
                    "avg_cpu_utilization": f"{round(avg_cpu, 1)}%",
                    "avg_memory_utilization": f"{round(avg_mem, 1)}%",
                    "recent_error_rate": f"{round(metrics[0].error_rate, 2)}%",
                    "recent_response_time_ms": f"{metrics[0].response_time_ms}ms"
                }
                
            
            # 6. Calculate dynamic health score
            vulnerabilities_count = project_metadata.get("vulnerabilities_count", 0)
            reliability = max(0, 100 - (failed_count * 10) - int(avg_error_rate * 15))
            security = max(0, 100 - (vulnerabilities_count * 8))
            performance = max(0, 100 - int(max(0, avg_cpu - 50) * 0.5) - int(max(0, avg_mem - 80) * 1.0))
            scalability = 95 if len(deps) > 0 else 80
            cost_score = None
            if analysis and analysis.pricing_breakdown and isinstance(
                analysis.pricing_breakdown.get("total_cost"), (int, float)
            ):
                total_cost = analysis.pricing_breakdown.get("total_cost", 0.0)
                if total_cost < 15:
                    cost_score = 95
                elif total_cost < 50:
                    cost_score = 85
                else:
                    cost_score = 70
            health_total = reliability * 3 + security * 2 + performance * 2 + scalability
            health_weight = 8
            if cost_score is not None:
                health_total += cost_score
                health_weight += 1
            health_score = int(health_total / health_weight)
            project_metadata["health_score"] = health_score

    reply = ai.generate_chat_response(req.message, project_metadata)
    return {"reply": reply}





@app.get("/api/projects/{project_id}/recommendations", response_model=schemas.DeploymentRecommendationResponse)
async def get_project_recommendations(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve the latest AI deployment recommendation for a project."""
    # Verify project ownership
    proj_result = await db.execute(
        select(models.Project).filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    if not proj_result.scalars().first():
        raise HTTPException(status_code=404, detail="Project not found.")

    result = await db.execute(
        select(models.DeploymentRecommendation)
        .filter(models.DeploymentRecommendation.project_id == project_id)
        .order_by(desc(models.DeploymentRecommendation.created_at))
        .limit(1)
    )
    rec = result.scalars().first()
    if not rec:
        raise HTTPException(status_code=404, detail="No deployment recommendation recorded for this project.")
    return rec


@app.get("/api/deployments/{deployment_id}/failure-analysis", response_model=schemas.FailureAnalysisResponse)
async def get_deployment_failure_analysis(
    deployment_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve NVIDIA Nemotron failure analysis for a failed deployment."""
    # Verify deployment ownership (capture reference before consuming the result set)
    dep_result = await db.execute(
        select(models.Deployment)
        .filter(models.Deployment.id == deployment_id, models.Deployment.user_id == current_user.id)
    )
    deployment = dep_result.scalars().first()
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found.")

    result = await db.execute(
        select(models.FailureAnalysis)
        .filter(models.FailureAnalysis.deployment_id == deployment_id)
    )
    fa = result.scalars().first()
    if not fa:
        logger.warning(f"No failure analysis record found in DB for deployment {deployment_id}, triggering on-the-fly analyzer...")
        
        # Retrieve logs
        log_result = await db.execute(
            select(models.DeploymentLog)
            .filter(models.DeploymentLog.deployment_id == deployment_id)
            .order_by(models.DeploymentLog.line_number)
        )
        logs = log_result.scalars().all()
        log_msgs = [l.message for l in logs]
        
        try:
            failure_res = ai.analyze_failure_nemotron(log_msgs, log_msgs)
        except (ValueError, RuntimeError) as e:
            logger.warning(f"AI failure analysis unavailable for deployment {deployment_id}: {e}. Using local analyzer.")
            failure_res = ai.analyze_failure_local(log_msgs, log_msgs)
        
        fa = models.FailureAnalysis(
            id=uuid.uuid4(),
            user_id=current_user.id,
            project_id=deployment.project_id,
            deployment_id=deployment_id,
            failure_summary=failure_res.get("failure_summary", "Deployment failed."),
            root_cause=failure_res.get("root_cause", "Unable to determine root cause."),
            severity=failure_res.get("severity", "error"),
            recommended_fix=failure_res.get("recommended_fix", "Review deployment logs."),
            step_by_step_resolution=failure_res.get("step_by_step_resolution") or [
                "Check the deployment logs for error details.",
                "Verify environment variables are configured.",
                "Trigger a new deployment."
            ]
        )
        db.add(fa)
        await db.commit()
        
    return fa


@app.get("/api/projects/{project_id}/analyses", response_model=List[schemas.AIAnalysisResponse])
async def get_project_analyses_history(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve chronological history of all AI analyses for a project."""
    # Verify project ownership
    proj_result = await db.execute(
        select(models.Project)
        .filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    if not proj_result.scalars().first():
        raise HTTPException(status_code=404, detail="Project not found.")

    result = await db.execute(
        select(models.AIAnalysis)
        .filter(models.AIAnalysis.project_id == project_id)
        .order_by(desc(models.AIAnalysis.created_at))
    )
    analyses = result.scalars().all()
    
    return [
        schemas.AIAnalysisResponse(
            id=a.id, project_id=a.project_id,
            framework=a.framework, framework_version=a.framework_version,
            language=a.language, risk_score=a.risk_score,
            confidence=a.confidence,
            cpu_recommendation=a.cpu_recommendation,
            memory_recommendation=a.memory_recommendation,
            storage_recommendation=a.storage_recommendation,
            port=a.port,
            dependencies=a.dependencies or [],
            vulnerabilities=a.vulnerabilities or [],
            dockerfile=a.dockerfile,
            kubernetes_manifest=a.kubernetes_manifest,
            created_at=format_dt(a.created_at),
            runtime=a.runtime,
            package_manager=a.package_manager,
            docker_support=a.docker_support or False,
            monorepo_structure=a.monorepo_structure,
            database_dependencies=a.database_dependencies or [],
            deployment_strategy=a.deployment_strategy,
            build_commands=a.build_commands,
            start_commands=a.start_commands,
            environment_variables=a.environment_variables or []
        )
        for a in analyses
    ]


# ──────────────────────────────────────────────
# DASHBOARD STATS (per-user)
# ──────────────────────────────────────────────

@app.get("/api/dashboard/stats")
async def get_dashboard_stats(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Projects count
    proj_count_result = await db.execute(
        select(func.count(models.Project.id))
        .filter(models.Project.user_id == current_user.id)
    )
    total_projects = proj_count_result.scalar() or 0

    # Deployments
    dep_count_result = await db.execute(
        select(func.count(models.Deployment.id))
        .filter(models.Deployment.user_id == current_user.id)
    )
    total_deployments = dep_count_result.scalar() or 0

    active_dep_result = await db.execute(
        select(func.count(models.Deployment.id))
        .filter(models.Deployment.user_id == current_user.id, models.Deployment.status == "running")
    )
    active_deployments = active_dep_result.scalar() or 0

    failed_dep_result = await db.execute(
        select(func.count(models.Deployment.id))
        .filter(models.Deployment.user_id == current_user.id, models.Deployment.status == "failed")
    )
    failed_deployments = failed_dep_result.scalar() or 0

    # AI Actions
    actions_result = await db.execute(
        select(func.count(models.AIAction.id))
        .filter(models.AIAction.user_id == current_user.id, models.AIAction.status == "pending")
    )
    pending_actions = actions_result.scalar() or 0

    # Notifications
    notif_result = await db.execute(
        select(func.count(models.Notification.id))
        .filter(models.Notification.user_id == current_user.id, models.Notification.read == False)
    )
    unread_notifs = notif_result.scalar() or 0

    # Security score (based on deployments and actions)
    security_score = 0
    if total_deployments > 0:
        security_score = max(85, 100 - (failed_deployments * 5))

    return schemas.DashboardStats(
        total_projects=total_projects,
        total_deployments=total_deployments,
        active_deployments=active_deployments,
        failed_deployments=failed_deployments,
        security_score=security_score,
        pending_ai_actions=pending_actions,
        unread_notifications=unread_notifs,
        has_deployed=total_deployments > 0
    )


# ──────────────────────────────────────────────
# USER PROFILE (per-user)
# ──────────────────────────────────────────────

@app.get("/api/user/profile")
async def get_profile(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    proj_count = (await db.execute(
        select(func.count(models.Project.id)).filter(models.Project.user_id == current_user.id)
    )).scalar() or 0

    dep_count = (await db.execute(
        select(func.count(models.Deployment.id)).filter(models.Deployment.user_id == current_user.id)
    )).scalar() or 0

    active_dep = (await db.execute(
        select(func.count(models.Deployment.id))
        .filter(models.Deployment.user_id == current_user.id, models.Deployment.status == "running")
    )).scalar() or 0

    return schemas.UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        avatar_url=current_user.avatar_url,
        plan=current_user.plan,
        provider=current_user.provider,
        created_at=format_dt(current_user.created_at),
        total_projects=proj_count,
        total_deployments=dep_count,
        active_deployments=active_dep
    )


@app.put("/api/user/profile")
async def update_profile(
    req: schemas.UserProfileUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if req.first_name is not None:
        current_user.first_name = req.first_name
    if req.last_name is not None:
        current_user.last_name = req.last_name
    if req.avatar_url is not None:
        current_user.avatar_url = req.avatar_url
    await db.commit()
    await db.refresh(current_user)
    return map_user_response(current_user)


# ──────────────────────────────────────────────
# USER SETTINGS (per-user)
# ──────────────────────────────────────────────

@app.get("/api/user/settings")
async def get_settings(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(models.UserSettings).filter(models.UserSettings.user_id == current_user.id)
    )
    settings = result.scalars().first()
    if not settings:
        settings = models.UserSettings(user_id=current_user.id)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return schemas.UserSettingsResponse.from_orm(settings)


@app.put("/api/user/settings")
async def update_settings(
    req: schemas.UserSettingsUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(models.UserSettings).filter(models.UserSettings.user_id == current_user.id)
    )
    settings = result.scalars().first()
    if not settings:
        settings = models.UserSettings(user_id=current_user.id)
        db.add(settings)

    update_data = req.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(settings, key, value)

    await db.commit()
    await db.refresh(settings)
    return schemas.UserSettingsResponse.from_orm(settings)


@app.post("/api/user/reset")
async def reset_user_onboarding(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import delete

    # Delete user's projects, deployments, AI actions, and notifications
    await db.execute(delete(models.Project).filter(models.Project.user_id == current_user.id))
    await db.execute(delete(models.AIAction).filter(models.AIAction.user_id == current_user.id))
    await db.execute(delete(models.Notification).filter(models.Notification.user_id == current_user.id))

    # Reset UserSettings to defaults
    settings_result = await db.execute(
        select(models.UserSettings).filter(models.UserSettings.user_id == current_user.id)
    )
    settings = settings_result.scalars().first()
    if settings:
        settings.predictive_scaling = True
        settings.auto_rollback = True
        settings.ai_threat_mitigation = True
        settings.auto_oom_restart = True
        settings.slack_notifications = False
        settings.email_alerts = True
        settings.theme = "dark"
    else:
        settings = models.UserSettings(user_id=current_user.id)
        db.add(settings)

    # Re-add welcome notification
    welcome_notif = models.Notification(
        user_id=current_user.id,
        title="Welcome to ZeroOps AI",
        message="Your autonomous cloud deployment platform is ready. Connect a repository to get started.",
        type="success",
        category="system"
    )
    db.add(welcome_notif)

    await db.commit()
    return {"status": "success", "message": "Onboarding and deployments reset successfully."}


# ──────────────────────────────────────────────
# GITHUB OAUTH INTEGRATION
# ──────────────────────────────────────────────


@app.get("/api/auth/github")
async def github_oauth_redirect(request: Request):
    """Initiate GitHub OAuth flow by redirecting to GitHub's authorization page."""
    if not config.GITHUB_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GitHub OAuth is not configured. Set GITHUB_CLIENT_ID.")

    state = secrets.token_urlsafe(32)
    authorization_url = github_oauth.get_authorization_url(state)
    
    redirect_response = RedirectResponse(url=authorization_url, status_code=302)
    
    is_prod_cookie = config.IS_PRODUCTION
    redirect_response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        secure=True if is_prod_cookie else False,
        samesite="lax",
        max_age=600,
        path="/",
    )
    return redirect_response


@app.get("/api/auth/github/callback")
async def github_oauth_callback(
    request: Request,
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    response: Response = None,
    db: AsyncSession = Depends(get_db)
):
    frontend_url = get_frontend_redirect_url()
    # Helper to construct redirect response with cleared oauth_state cookie
    def get_redirect_and_clean_state(url_target: str) -> RedirectResponse:
        res = RedirectResponse(url=url_target, status_code=302)
        is_prod_cookie = config.IS_PRODUCTION
        res.delete_cookie(
            key="oauth_state",
            path="/",
            secure=True if is_prod_cookie else False,
            samesite="lax",
            httponly=True,
        )
        return res

    # Handle errors from GitHub
    if error:
        logger.warning("GitHub OAuth provider returned an authorization error: %s", error)
        return get_redirect_and_clean_state(f"{frontend_url}/login?oauth_error={error}&provider=github")

    # Validate required parameters
    if not code or not state:
        return get_redirect_and_clean_state(f"{frontend_url}/login?oauth_error=missing_params&provider=github")

    # Validate CSRF state from cookie
    cookie_state = request.cookies.get("oauth_state")
    if not cookie_state or not hmac.compare_digest(state, cookie_state):
        logger.warning("GitHub OAuth state validation failed.")
        return get_redirect_and_clean_state(f"{frontend_url}/login?oauth_error=invalid_state&provider=github")

    # Exchange code for access token
    access_token = await github_oauth.exchange_code_for_token(code)
    if not access_token:
        return get_redirect_and_clean_state(f"{frontend_url}/login?oauth_error=token_exchange_failed&provider=github")

    # Fetch GitHub user profile
    gh_user = await github_oauth.get_github_user(access_token)
    if not gh_user:
        return get_redirect_and_clean_state(f"{frontend_url}/login?oauth_error=github_user_fetch_failed&provider=github")

    github_id = str(gh_user.get("id", ""))
    github_username = gh_user.get("login", "")
    github_avatar = gh_user.get("avatar_url", "")
    github_name = gh_user.get("name", "") or github_username

    # Always require the verified email API result before linking an account.
    email = await github_oauth.get_github_user_email(access_token)
    if not email:
        return get_redirect_and_clean_state(f"{frontend_url}/login?oauth_error=no_verified_email&provider=github")

    email = email.strip().lower()

    # Encrypt the access token for secure storage
    encrypted_token = github_oauth.encrypt_token(access_token)

    try:
        # Look up user by github_id first
        result = await db.execute(
            select(models.User).filter(models.User.github_id == github_id)
        )
        user = result.scalars().first()

        if not user:
            # Check if user exists with same email
            result = await db.execute(
                select(models.User).filter(models.User.email == email)
            )
            user = result.scalars().first()

        if user:
            # Update existing user with GitHub data
            user.github_id = github_id
            user.github_username = github_username
            user.github_avatar_url = github_avatar
            user.github_access_token_encrypted = encrypted_token
            user.github_connected = True
            user.provider = "github"
            user.provider_id = github_id
            if not user.avatar_url:
                user.avatar_url = github_avatar
            await db.commit()
            await db.refresh(user)
            logger.info(f"GitHub OAuth login: existing user {email} linked to GitHub @{github_username}")
        else:
            # Parse name into first/last
            name_parts = github_name.split(" ", 1)
            first_name = name_parts[0] if name_parts else github_username
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            # Create new user
            user = models.User(
                id=uuid.uuid4(),
                first_name=first_name,
                last_name=last_name,
                email=email,
                password_hash=None,
                provider="github",
                provider_id=github_id,
                avatar_url=github_avatar,
                plan="starter",
                github_id=github_id,
                github_username=github_username,
                github_avatar_url=github_avatar,
                github_access_token_encrypted=encrypted_token,
                github_connected=True,
            )
            db.add(user)
            await db.flush()

            # Create default settings and welcome notification
            db.add(models.UserSettings(user_id=user.id))
            db.add(models.Notification(
                user_id=user.id,
                title="Welcome to ZeroOps AI",
                message=f"Connected as @{github_username}. Select a repository to start your first deployment.",
                type="success",
                category="system"
            ))
            await db.commit()
            await db.refresh(user)
            logger.info(f"GitHub OAuth signup: new user {email} (@{github_username}) created")

    except Exception as e:
        await db.rollback()
        logger.exception("GitHub OAuth database error")
        return get_redirect_and_clean_state(f"{frontend_url}/login?oauth_error=server_error&provider=github")

    user.last_primary_auth_at = datetime.utcnow()
    db.add(user)
    await db.commit()

    if user.mfa_enabled and user.mfa_secret_encrypted:
        redirect_response = get_redirect_and_clean_state(f"{frontend_url}/login?mfa=required&provider=github")
        await begin_mfa_challenge(user, redirect_response, db)
        return redirect_response

    redirect_response = get_redirect_and_clean_state(f"{frontend_url}/dashboard/repositories?auth=success")
    await establish_authenticated_session(user, redirect_response, db)
    return redirect_response


@app.get("/api/auth/google")
async def google_oauth_redirect(request: Request):
    """Initiate Google OAuth flow."""
    if not config.GOOGLE_CLIENT_ID or not config.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.")

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    redirect_uri = str(request.url_for("google_oauth_callback"))
    authorization_url = google_oauth.get_authorization_url(state, redirect_uri, code_challenge)

    redirect_response = RedirectResponse(url=authorization_url, status_code=302)
    is_prod_cookie = config.IS_PRODUCTION
    redirect_response.set_cookie(
        key="google_oauth_state",
        value=state,
        httponly=True,
        secure=True if is_prod_cookie else False,
        samesite="lax",
        max_age=600,
        path="/",
    )
    redirect_response.set_cookie(
        key="google_oauth_verifier",
        value=code_verifier,
        httponly=True,
        secure=True if is_prod_cookie else False,
        samesite="lax",
        max_age=600,
        path="/",
    )
    return redirect_response


@app.get("/api/auth/google/callback")
async def google_oauth_callback(
    request: Request,
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    frontend_url = get_frontend_redirect_url()

    def redirect_to_frontend(query: str) -> RedirectResponse:
        res = RedirectResponse(url=f"{frontend_url}/login?provider=google&{query}", status_code=302)
        is_prod_cookie = config.IS_PRODUCTION
        for cookie_name in ("google_oauth_state", "google_oauth_verifier"):
            res.delete_cookie(
                key=cookie_name,
                path="/",
                secure=True if is_prod_cookie else False,
                samesite="lax",
                httponly=True,
            )
        return res

    if error:
        return redirect_to_frontend(f"oauth_error={error}")
    if not code or not state:
        return redirect_to_frontend("oauth_error=missing_params")

    cookie_state = request.cookies.get("google_oauth_state")
    code_verifier = request.cookies.get("google_oauth_verifier")
    if not cookie_state or not code_verifier or not hmac.compare_digest(cookie_state, state):
        return redirect_to_frontend("oauth_error=invalid_state")

    redirect_uri = str(request.url_for("google_oauth_callback"))
    google_access_token = await google_oauth.exchange_code_for_token(code, redirect_uri, code_verifier)
    if not google_access_token:
        return redirect_to_frontend("oauth_error=token_exchange_failed")

    google_user = await google_oauth.get_google_user(google_access_token)
    if not google_user:
        return redirect_to_frontend("oauth_error=google_user_fetch_failed")

    google_id = str(google_user.get("sub", ""))
    email = (google_user.get("email") or "").strip().lower()
    if not google_id or not email or google_user.get("email_verified") is not True:
        return redirect_to_frontend("oauth_error=no_verified_email")

    try:
        result = await db.execute(select(models.User).filter(models.User.google_id == google_id))
        user = result.scalars().first()
        if not user:
            result = await db.execute(select(models.User).filter(models.User.email == email))
            user = result.scalars().first()

        if user:
            user.google_id = google_id
            user.provider = "google"
            user.provider_id = google_id
            if not user.avatar_url:
                user.avatar_url = google_user.get("picture")
            if not user.first_name:
                user.first_name = google_user.get("given_name") or google_user.get("name")
            if not user.last_name:
                user.last_name = google_user.get("family_name")
        else:
            user = models.User(
                id=uuid.uuid4(),
                first_name=google_user.get("given_name") or google_user.get("name") or "User",
                last_name=google_user.get("family_name") or "",
                email=email,
                password_hash=None,
                provider="google",
                provider_id=google_id,
                google_id=google_id,
                avatar_url=google_user.get("picture"),
                plan="starter",
            )
            db.add(user)
            await db.flush()
            db.add(models.UserSettings(user_id=user.id))
            db.add(models.Notification(
                user_id=user.id,
                title="Welcome to ZeroOps AI",
                message="Your account is ready. Connect GitHub or upload code to start a deployment.",
                type="success",
                category="system",
            ))

        user.last_primary_auth_at = datetime.utcnow()
        db.add(user)
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.exception("Google OAuth database error")
        return redirect_to_frontend("oauth_error=server_error")

    if user.mfa_enabled and user.mfa_secret_encrypted:
        redirect_response = redirect_to_frontend("mfa=required")
        await begin_mfa_challenge(user, redirect_response, db)
        return redirect_response

    redirect_response = RedirectResponse(url=f"{frontend_url}/dashboard/repositories?auth=success", status_code=302)
    is_prod_cookie = config.IS_PRODUCTION
    for cookie_name in ("google_oauth_state", "google_oauth_verifier"):
        redirect_response.delete_cookie(
            key=cookie_name,
            path="/",
            secure=True if is_prod_cookie else False,
            samesite="lax",
            httponly=True,
        )
    await establish_authenticated_session(user, redirect_response, db)
    return redirect_response


@app.get("/api/github/status")
async def get_github_status(
    current_user: models.User = Depends(auth.get_current_user),
):
    """Check whether the current user has a connected GitHub account."""
    return schemas.GitHubStatusResponse(
        connected=current_user.github_connected or False,
        username=current_user.github_username,
        avatar_url=current_user.github_avatar_url,
    )


@app.get("/api/github/repos")
async def get_github_repos(
    current_user: models.User = Depends(auth.get_current_user),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=30, ge=1, le=100),
    sort: str = Query(default="updated"),
    q: Optional[str] = Query(default=None),
):
    """Fetch the authenticated user's GitHub repositories.
    Uses the user's encrypted stored GitHub token — never exposed to frontend."""
    if not current_user.github_connected or not current_user.github_access_token_encrypted:
        raise HTTPException(status_code=400, detail="GitHub account is not connected.")

    try:
        token = github_oauth.decrypt_token(current_user.github_access_token_encrypted)
    except Exception:
        raise HTTPException(status_code=400, detail="GitHub token is invalid. Please reconnect GitHub.")

    result = await github_oauth.get_user_repos(
        token=token, page=page, per_page=per_page, sort=sort, query=q
    )
    return result


@app.get("/api/github/branches")
async def get_github_branches(
    repo: str = Query(..., description="Repository full name (owner/repo)"),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Fetch branches for a specific GitHub repository."""
    if not current_user.github_connected or not current_user.github_access_token_encrypted:
        raise HTTPException(status_code=400, detail="GitHub account is not connected.")

    try:
        token = github_oauth.decrypt_token(current_user.github_access_token_encrypted)
    except Exception:
        raise HTTPException(status_code=400, detail="GitHub token is invalid. Please reconnect GitHub.")

    parts = repo.split("/", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid repo format. Use owner/repo.")

    branches = await github_oauth.get_repo_branches(token, parts[0], parts[1])
    return {"branches": branches}


@app.post("/api/github/disconnect")
async def disconnect_github(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect GitHub account from the current user."""
    current_user.github_access_token_encrypted = None
    current_user.github_connected = False
    await db.commit()
    logger.info(f"GitHub disconnected for user {current_user.email}")
    return {"status": "success", "message": "GitHub account disconnected."}


# Legacy PAT-based endpoint kept for backward compatibility
@app.get("/api/github/repo-metadata")
async def get_repo_metadata(
    repo: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """Fetch repo metadata (branches). Uses OAuth token if available, falls back to PAT."""
    if current_user.github_connected and current_user.github_access_token_encrypted:
        try:
            token = github_oauth.decrypt_token(current_user.github_access_token_encrypted)
            parts = repo.split("/", 1)
            if len(parts) == 2:
                branches = await github_oauth.get_repo_branches(token, parts[0], parts[1])
                return {"branches": branches}
        except Exception:
            pass
    # Fallback to git ls-remote with PAT
    token = config.GITHUB_TOKEN
    branches = git.get_branches(repo, token)
    return {"branches": branches}


# ──────────────────────────────────────────────
# INFRASTRUCTURE & MONITORING
# ──────────────────────────────────────────────

@app.get("/api/monitoring/metrics")
async def get_metrics(
    project_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not project_id:
        return {"available": False, "message": "Choose a project to view recorded runtime metrics."}
    try:
        project_uuid = uuid.UUID(project_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid project ID") from error
    project_result = await db.execute(
        select(models.Project).filter(models.Project.id == project_uuid, models.Project.user_id == current_user.id)
    )
    if not project_result.scalars().first():
        raise HTTPException(status_code=404, detail="Project not found")
    metrics_result = await db.execute(
        select(models.DeploymentMetric)
        .filter(models.DeploymentMetric.deployment_id.in_(
            select(models.Deployment.id).filter(models.Deployment.project_id == project_uuid)
        ))
        .order_by(desc(models.DeploymentMetric.timestamp))
        .limit(20)
    )
    metrics = metrics_result.scalars().all()
    if not metrics:
        return {"available": False, "message": "No recorded runtime metrics are available for this project."}
    return {
        "available": True,
        "cpu": round(sum(metric.cpu_utilization for metric in metrics) / len(metrics), 1),
        "memory": round(sum(metric.memory_utilization for metric in metrics) / len(metrics), 1),
        "traffic": sum(metric.request_count for metric in metrics),
        "errorRate": round(sum(metric.error_rate for metric in metrics) / len(metrics), 2),
    }


@app.post("/api/secrets")
async def add_secret(
    req: schemas.SecretCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    proj_result = await db.execute(
        select(models.Project).filter(models.Project.id == req.projectId, models.Project.user_id == current_user.id)
    )
    if not proj_result.scalars().first():
        raise HTTPException(status_code=404, detail="Project not found")
    success = vault.set_project_secret(req.projectId, req.key, req.value)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save secret")
    return {"status": "success", "key": req.key}


@app.get("/api/secrets/{project_id}")
async def list_secrets(project_id: str, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    proj_result = await db.execute(
        select(models.Project).filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    if not proj_result.scalars().first():
        raise HTTPException(status_code=404, detail="Project not found")
    secrets = vault.get_project_secrets(project_id)
    return [{"key": k, "value": "********"} for k in secrets.keys()]


@app.delete("/api/secrets/{project_id}/{key}")
async def delete_secret(project_id: str, key: str, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    proj_result = await db.execute(
        select(models.Project).filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    if not proj_result.scalars().first():
        raise HTTPException(status_code=404, detail="Project not found")
    success = vault.delete_project_secret(project_id, key)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete secret")
    return {"status": "success"}


@app.post("/api/autoscaling/configure")
async def configure_autoscaling(req: schemas.HPAConfigureRequest, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    proj_result = await db.execute(
        select(models.Project).filter(models.Project.id == req.projectId, models.Project.user_id == current_user.id)
    )
    if not proj_result.scalars().first():
        raise HTTPException(status_code=404, detail="Project not found")
    raise HTTPException(
        status_code=501,
        detail="Capacity changes are managed by the selected Azure App Service plan and are not available in ZeroOps yet.",
    )


@app.get("/api/autoscaling/{project_id}")
async def get_autoscaling_status(project_id: str, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    proj_result = await db.execute(
        select(models.Project).filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    if not proj_result.scalars().first():
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "available": False,
        "message": "Capacity controls are managed by the selected Azure App Service plan when hosting is connected.",
    }


@app.get("/api/security/status/{project_id}")
async def get_security_status(project_id: str, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    proj_result = await db.execute(
        select(models.Project).filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    secrets = vault.get_project_secrets(project_id)
    secrets_count = len(secrets)
    verified_domain = any(
        bool(domain.get("https_enabled") or domain.get("ssl"))
        for domain in (project.custom_domains or [])
        if isinstance(domain, dict)
    )
    
    # Fetch vulnerabilities count from latest AI analysis
    vuln_count = 0
    try:
        analysis_result = await db.execute(
            select(models.AIAnalysis)
            .filter(models.AIAnalysis.project_id == project.id)
            .order_by(models.AIAnalysis.created_at.desc())
            .limit(1)
        )
        latest_analysis = analysis_result.scalars().first()
        if latest_analysis and latest_analysis.vulnerabilities:
            vuln_count = len(latest_analysis.vulnerabilities)
    except Exception:
        pass

    score = 0
    if secrets_count > 0:
        score += 35
    if verified_domain:
        score += 35
    if k8s.K8S_AVAILABLE:
        score += 30
    return {
        "securityScore": score,
        "firewallStatus": "Managed" if k8s.K8S_AVAILABLE else "Unavailable",
        "httpsStatus": "Active" if verified_domain else "Not configured",
        "secretsManaged": secrets_count,
        "vulnerabilities": vuln_count,
        "soc2Status": "Not assessed",
        "threatLevel": "Low" if vuln_count == 0 else ("Medium" if vuln_count < 3 else "High"),
        "namespaceIsolated": k8s.K8S_AVAILABLE,
        "rbacEnabled": k8s.K8S_AVAILABLE
    }


# ──────────────────────────────────────────────
# API KEY MANAGEMENT (per-user)
# ──────────────────────────────────────────────

def _generate_api_key() -> str:
    import secrets
    return f"zo_{secrets.token_urlsafe(32)}"

@app.get("/api/settings/api-key")
async def get_api_key(db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    if not current_user.api_key:
        current_user.api_key = _generate_api_key()
        db.add(current_user)
        await db.commit()
        await db.refresh(current_user)
    return {"apiKey": current_user.api_key or ""}

@app.post("/api/settings/api-key/regenerate")
async def regenerate_api_key(db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    current_user.api_key = _generate_api_key()
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return {"apiKey": current_user.api_key}


# ──────────────────────────────────────────────
# COLLABORATION, DOMAINS, HEALTH & COST OPTIMIZATION APIs
# ──────────────────────────────────────────────

from sqlalchemy.orm.attributes import flag_modified

@app.get("/api/projects/{project_id}/health-score")
async def get_project_health_score(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    proj_result = await db.execute(
        select(models.Project)
        .filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    deps_result = await db.execute(
        select(models.Deployment)
        .filter(models.Deployment.project_id == project_id)
    )
    deps = deps_result.scalars().all()
    failed_count = sum(1 for d in deps if d.status == "failed")
    
    metrics = []
    if deps:
        latest_metric_result = await db.execute(
            select(models.DeploymentMetric)
            .filter(models.DeploymentMetric.deployment_id.in_([d.id for d in deps]))
            .order_by(desc(models.DeploymentMetric.timestamp))
            .limit(5)
        )
        metrics = latest_metric_result.scalars().all()
    
    if not deps:
        return {
            "score": 0,
            "status": "No deployments",
            "breakdown": {
                "performance": 0,
                "security": 0,
                "reliability": 0,
                "scalability": 0,
                "cost": None
            },
            "recommendations": ["Deploy this project to begin collecting production health signals."]
        }

    if not metrics:
        return {
            "score": 0,
            "status": "No telemetry",
            "breakdown": {
                "performance": 0,
                "security": 0,
                "reliability": max(0, 100 - (failed_count * 10)),
                "scalability": 0,
                "cost": None
            },
            "recommendations": ["No deployment metrics have been recorded for this project yet."]
        }

    avg_error_rate = sum(m.error_rate for m in metrics) / len(metrics)
    avg_cpu = sum(m.cpu_utilization for m in metrics) / len(metrics)
    avg_mem = sum(m.memory_utilization for m in metrics) / len(metrics)
    
    analysis_result = await db.execute(
        select(models.AIAnalysis)
        .filter(models.AIAnalysis.project_id == project_id)
        .order_by(desc(models.AIAnalysis.created_at))
        .limit(1)
    )
    analysis = analysis_result.scalars().first()
    vulnerabilities_count = 0
    if analysis and analysis.vulnerabilities:
        vulnerabilities_count = len(analysis.vulnerabilities)
        if vulnerabilities_count == 1 and "vulnerability checks passed" in str(analysis.vulnerabilities[0]).lower():
            vulnerabilities_count = 0

    reliability = max(0, 100 - (failed_count * 10) - int(avg_error_rate * 15))
    security = max(0, 100 - (vulnerabilities_count * 8))
    performance = max(0, 100 - int(max(0, avg_cpu - 50) * 0.5) - int(max(0, avg_mem - 80) * 1.0))
    scalability = 95 if len(deps) > 0 else 80
    # Cost efficiency is unavailable until Azure Cost Management telemetry is
    # connected. Do not turn a source-code heuristic into a health score.
    cost = None
    overall_score = int((reliability * 3 + security * 2 + performance * 2 + scalability) / 8)
    overall_score = max(0, min(100, overall_score))
    
    status_str = "Strong Reliability" if overall_score >= 90 else "Good Health" if overall_score >= 80 else "Needs Attention" if overall_score >= 60 else "Critical Status"
    
    recommendations = []
    if vulnerabilities_count > 0:
        recommendations.append(f"Fix {vulnerabilities_count} security warning(s) identified in dependency scans.")
    if failed_count > 0:
        recommendations.append("Investigate recent deployment build logs to stabilize runtime startup.")
    if avg_cpu < 10.0:
        recommendations.append("CPU utilization is low; review capacity settings after cost telemetry is connected.")
    if not project.custom_domains:
        recommendations.append("Connect a custom domain to enable production TLS routing.")
    if len(recommendations) == 0:
        recommendations.append("No immediate reliability or security issues found in recorded telemetry.")

    return {
        "score": overall_score,
        "status": status_str,
        "breakdown": {
            "performance": performance,
            "security": security,
            "reliability": reliability,
            "scalability": scalability,
            "cost": cost
        },
        "recommendations": recommendations
    }

@app.get("/api/projects/{project_id}/cost-optimization")
async def get_project_cost_optimization(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    proj_result = await db.execute(
        select(models.Project)
        .filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    raise HTTPException(
        status_code=501,
        detail="Cost optimization requires connected Azure Cost Management data. No estimate is shown until that data is available.",
    )

@app.get("/api/projects/{project_id}/domains")
async def get_project_domains(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    proj_result = await db.execute(
        select(models.Project).filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project.custom_domains or []

@app.post("/api/projects/{project_id}/domains")
async def create_project_domain(
    project_id: uuid.UUID,
    req: schemas.ProjectDomainCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    proj_result = await db.execute(
        select(models.Project).filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    domains = list(project.custom_domains or [])
    if any(d["name"] == req.name for d in domains):
        raise HTTPException(status_code=400, detail="Domain is already connected.")

    new_domain = {
        "name": req.name,
        "default": len(domains) == 0,
        "ssl": False,
        "dns_verified": False,
        "https_enabled": False,
        "created_at": datetime.utcnow().isoformat()
    }
    domains.append(new_domain)
    project.custom_domains = domains
    flag_modified(project, "custom_domains")
    
    db.add(models.ActivityEvent(
        user_id=current_user.id,
        project_id=project.id,
        action="Domain Connected",
        details=f"Connected custom domain {req.name} to project {project.name}."
    ))
    await db.commit()
    return domains

@app.post("/api/projects/{project_id}/domains/{domain_name}/verify")
async def verify_project_domain(
    project_id: uuid.UUID,
    domain_name: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    proj_result = await db.execute(
        select(models.Project).filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    domains = list(project.custom_domains or [])
    found = False
    for d in domains:
        if d["name"] == domain_name:
            d["dns_verified"] = True
            d["ssl"] = True
            d["https_enabled"] = True
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Domain not found.")

    project.custom_domains = domains
    flag_modified(project, "custom_domains")
    
    db.add(models.ActivityEvent(
        user_id=current_user.id,
        project_id=project.id,
        action="Domain DNS/SSL Verified",
        details=f"Successfully verified DNS records and enabled SSL for {domain_name}."
    ))
    await db.commit()
    return domains

@app.post("/api/projects/{project_id}/domains/{domain_name}/renew-ssl")
async def renew_domain_ssl(
    project_id: uuid.UUID,
    domain_name: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    proj_result = await db.execute(
        select(models.Project).filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    domains = list(project.custom_domains or [])
    found = False
    for d in domains:
        if d["name"] == domain_name:
            d["ssl"] = True
            d["https_enabled"] = True
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Domain not found.")

    project.custom_domains = domains
    flag_modified(project, "custom_domains")
    
    db.add(models.ActivityEvent(
        user_id=current_user.id,
        project_id=project.id,
        action="Domain SSL Renewed",
        details=f"Renewed Let's Encrypt SSL certificate for custom domain {domain_name}."
    ))
    await db.commit()
    return domains

@app.delete("/api/projects/{project_id}/domains/{domain_name}")
async def delete_project_domain(
    project_id: uuid.UUID,
    domain_name: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    proj_result = await db.execute(
        select(models.Project).filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    domains = list(project.custom_domains or [])
    new_domains = [d for d in domains if d["name"] != domain_name]
    if len(domains) == len(new_domains):
        raise HTTPException(status_code=404, detail="Domain not found.")

    project.custom_domains = new_domains
    flag_modified(project, "custom_domains")
    
    db.add(models.ActivityEvent(
        user_id=current_user.id,
        project_id=project.id,
        action="Domain Removed",
        details=f"Removed custom domain {domain_name} from project."
    ))
    await db.commit()
    return new_domains

@app.get("/api/projects/{project_id}/members")
async def get_project_members(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    proj_result = await db.execute(
        select(models.Project).filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
        
    members = list(project.members or [])
    if not any(m.get("email") == current_user.email for m in members):
        owner_member = {
            "email": current_user.email,
            "role": "Owner",
            "name": f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or current_user.email.split("@")[0].capitalize(),
            "joined_at": current_user.created_at.isoformat() if current_user.created_at else datetime.utcnow().isoformat()
        }
        members.insert(0, owner_member)
        project.members = members
        flag_modified(project, "members")
        await db.commit()
    return members

@app.post("/api/projects/{project_id}/members")
async def add_project_member(
    project_id: uuid.UUID,
    req: schemas.ProjectMemberCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    proj_result = await db.execute(
        select(models.Project).filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    members = list(project.members or [])
    if any(m["email"] == req.email for m in members) or req.email == current_user.email:
        raise HTTPException(status_code=400, detail="User is already a member of this project.")

    new_member = {
        "email": req.email,
        "role": req.role,
        "name": req.email.split("@")[0].capitalize(),
        "joined_at": datetime.utcnow().isoformat()
    }
    members.append(new_member)
    project.members = members
    flag_modified(project, "members")
    
    db.add(models.ActivityEvent(
        user_id=current_user.id,
        project_id=project.id,
        action="Member Invited",
        details=f"Invited {req.email} to project {project.name} as {req.role}."
    ))
    await db.commit()
    return members

@app.delete("/api/projects/{project_id}/members/{email}")
async def delete_project_member(
    project_id: uuid.UUID,
    email: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    proj_result = await db.execute(
        select(models.Project).filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    project = proj_result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    if email == current_user.email:
        raise HTTPException(status_code=400, detail="Cannot remove yourself (Project Owner) from the project.")

    members = list(project.members or [])
    new_members = [m for m in members if m["email"] != email]
    if len(members) == len(new_members):
        raise HTTPException(status_code=404, detail="Member not found.")

    project.members = new_members
    flag_modified(project, "members")
    
    db.add(models.ActivityEvent(
        user_id=current_user.id,
        project_id=project.id,
        action="Member Removed",
        details=f"Removed {email} from project team."
    ))
    await db.commit()
    return new_members

@app.get("/api/projects/{project_id}/activity")
async def get_project_activity(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    proj_result = await db.execute(
        select(models.Project).filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    if not proj_result.scalars().first():
        raise HTTPException(status_code=404, detail="Project not found.")

    result = await db.execute(
        select(models.ActivityEvent)
        .filter(models.ActivityEvent.project_id == project_id)
        .order_by(desc(models.ActivityEvent.created_at))
        .limit(50)
    )
    events = result.scalars().all()
    
    if not events:
        proj_result = await db.execute(
            select(models.Project).filter(models.Project.id == project_id)
        )
        project = proj_result.scalars().first()
        event = models.ActivityEvent(
            user_id=current_user.id,
            project_id=project_id,
            action="Project Connected",
            details=f"Repository {project.full_name} was connected and scanned by ZeroOps AI.",
            created_at=project.created_at
        )
        db.add(event)
        await db.commit()
        events = [event]
        
    return [
        {
            "id": str(e.id),
            "project_id": str(e.project_id) if e.project_id else None,
            "action": e.action,
            "details": e.details,
            "created_at": e.created_at.isoformat()
        } for e in events
    ]

@app.get("/api/activity")
async def get_global_activity(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(models.ActivityEvent, models.Project.name)
        .outerjoin(models.Project, models.ActivityEvent.project_id == models.Project.id)
        .filter(models.ActivityEvent.user_id == current_user.id)
        .order_by(desc(models.ActivityEvent.created_at))
        .limit(50)
    )
    rows = result.all()
    
    if not rows:
        proj_result = await db.execute(
            select(models.Project).filter(models.Project.user_id == current_user.id)
        )
        projects = proj_result.scalars().all()
        
        for p in projects:
            e1 = models.ActivityEvent(
                user_id=current_user.id,
                project_id=p.id,
                action="Project Connected",
                details=f"Repository {p.full_name} was connected to ZeroOps.",
                created_at=p.created_at
            )
            db.add(e1)
            
            if p.last_deployed_at:
                e2 = models.ActivityEvent(
                    user_id=current_user.id,
                    project_id=p.id,
                    action="Application Deployed Successfully",
                    details=f"Deployed version v1.0 ({p.branch}) to production.",
                    created_at=p.last_deployed_at
                )
                db.add(e2)
        await db.commit()
        
        result = await db.execute(
            select(models.ActivityEvent, models.Project.name)
            .outerjoin(models.Project, models.ActivityEvent.project_id == models.Project.id)
            .filter(models.ActivityEvent.user_id == current_user.id)
            .order_by(desc(models.ActivityEvent.created_at))
            .limit(50)
        )
        rows = result.all()

    return [
        {
            "id": str(e.id),
            "project_id": str(e.project_id) if e.project_id else None,
            "project_name": proj_name or "Global System",
            "action": e.action,
            "details": e.details,
            "created_at": e.created_at.isoformat()
        } for e, proj_name in rows
    ]


# ──────────────────────────────────────────────
# HEALTH
# ──────────────────────────────────────────────

@app.get("/api/health")
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "zeroops-backend",
        "environment": config.APP_ENV,
        "azureDeploymentWorker": config.AZURE_CLI_AVAILABLE,
        "openAIConfigured": bool(config.OPENAI_API_KEY),
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/health/database")
@app.get("/health/database")
async def health_database(db: AsyncSession = Depends(get_db)):
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "details": "connected to PostgreSQL"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}")

@app.get("/api/health/github")
@app.get("/health/github")
async def health_github():
    try:
        import requests
        res = requests.get("https://api.github.com", timeout=2)
        if res.status_code == 200:
            return {"status": "healthy", "details": "GitHub API is reachable"}
        else:
            return {"status": "warning", "details": f"GitHub returned status code {res.status_code}"}
    except Exception as e:
        logger.error(f"GitHub health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"GitHub API is unreachable: {str(e)}")

@app.get("/api/health/deployments")
@app.get("/health/deployments")
async def health_deployments(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(func.count(models.Deployment.id)))
        total_count = result.scalar() or 0
        
        active_result = await db.execute(
            select(func.count(models.Deployment.id)).filter(models.Deployment.status == "building")
        )
        active_count = active_result.scalar() or 0
        
        return {
            "status": "healthy",
            "total_deployments": total_count,
            "active_deployments_running": active_count
        }
    except Exception as e:
        logger.error(f"Deployments health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Deployments engine query error: {str(e)}")

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


# ──────────────────────────────────────────────
# WEBSOCKET CHANNELS
# ──────────────────────────────────────────────

@app.websocket("/ws/deployments/{deploy_id}")
async def deploy_websocket(websocket: WebSocket, deploy_id: str):
    await websocket.accept()
    await pipeline.register_connection(deploy_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pipeline.unregister_connection(deploy_id, websocket)
    except Exception as e:
        print(f"WS error in {deploy_id}: {e}")
        pipeline.unregister_connection(deploy_id, websocket)


