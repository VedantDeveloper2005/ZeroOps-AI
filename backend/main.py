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
import secrets
import shutil
import zipfile
import hashlib
import stat
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, List, Union
from urllib.parse import urlencode
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Response, Query, Request, UploadFile, File, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func, desc, or_

logger = logging.getLogger("zeroops.main")

try:
    import stripe
except ImportError:
    stripe = None

try:
    from backend import config
    from backend.services import git, ai, pipeline, pipeline_records, vault, email_service, sms_service, planner, decision_intelligence, tenancy, analysis as zeroops_analysis
    from backend.services import deployment_targets
    from backend.services import github_oauth, google_oauth
    from backend.database import get_db, init_db, database_available, AsyncSessionLocal
    from backend import models, schemas, auth
except ImportError:
    import config
    from services import git, ai, pipeline, pipeline_records, vault, email_service, sms_service, planner, decision_intelligence, tenancy, analysis as zeroops_analysis
    from services import deployment_targets
    from services import github_oauth, google_oauth
    from database import get_db, init_db, database_available, AsyncSessionLocal
    import models, schemas, auth

@asynccontextmanager
async def lifespan(_: FastAPI):
    initialized = await init_db()
    if initialized:
        await migrate_legacy_environment_secrets()
        await remove_unverified_plan_estimates()
        await recover_interrupted_deployments()
        await reconcile_stale_ai_investigations()
    daemon_task = asyncio.create_task(maintenance_daemon())
    try:
        yield
    finally:
        daemon_task.cancel()
        with suppress(asyncio.CancelledError):
            await daemon_task


app = FastAPI(
    title="ZeroOps AI Backend",
    docs_url=None if config.IS_PRODUCTION else "/docs",
    redoc_url=None if config.IS_PRODUCTION else "/redoc",
    openapi_url=None if config.IS_PRODUCTION else "/openapi.json",
    lifespan=lifespan,
)

try:
    from backend.routes.history import router as history_router
    from backend.routes.devsecops import router as devsecops_router
except ImportError:
    from routes.history import router as history_router
    from routes.devsecops import router as devsecops_router

app.include_router(history_router)
app.include_router(devsecops_router)

@app.get("/health")
@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "ZeroOps AI Control Plane",
        "environment": config.APP_ENV,
        "database": database_available,
    }

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=config.ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "Stripe-Signature", "X-ZeroOps-Worker-Token"],
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
        path.startswith("/api/auth/oauth") or
        path.startswith("/api/auth/verify-email") or
        path.startswith("/api/auth/resend-verification") or
        path.startswith("/api/auth/verify-phone") or
        path.startswith("/api/auth/resend-phone-verification")
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
    elif path.startswith("/api/auth/verify-email"):
        category = "verify_email"
        limit = 10
    elif path.startswith("/api/auth/resend-verification"):
        category = "resend_verification"
        limit = 5
    elif path.startswith("/api/auth/verify-phone"):
        category = "verify_phone"
        limit = 10
    elif path.startswith("/api/auth/resend-phone-verification"):
        category = "resend_phone_verification"
        limit = 5
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

async def reconcile_stale_ai_investigations() -> int:
    """Finalize model attempts that cannot still have a live worker call."""

    if AsyncSessionLocal is None:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    completed_at = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(models.AIInvestigation).filter(
                models.AIInvestigation.status == "running",
                models.AIInvestigation.started_at.is_not(None),
                models.AIInvestigation.started_at < cutoff,
            )
        )
        stale = list(result.scalars().all())
        for investigation in stale:
            investigation.status = "unavailable"
            investigation.model_provider = "unavailable"
            investigation.model_name = "none"
            investigation.error_code = "AI_INVESTIGATION_INTERRUPTED"
            investigation.redacted_error = (
                "The investigation worker did not record a terminal result within the execution window."
            )
            investigation.completed_at = completed_at
        if stale:
            await db.commit()
            logger.warning("Finalized %s stale AI investigation(s) as unavailable.", len(stale))
        return len(stale)


async def maintenance_daemon():
    """Run bounded record reconciliation; telemetry rules execute on ingestion."""

    logger.info("ZeroOps maintenance daemon started.")
    while True:
        await asyncio.sleep(60)
        try:
            await reconcile_stale_ai_investigations()
        except Exception as error:
            logger.error(
                "Stale investigation reconciliation failed: %s",
                type(error).__name__,
            )


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
        mfa_method=user.mfa_method or "totp",
        email_verified=user.email_verified or False,
        phone_verified=user.phone_verified or False,
    )


def oauth_mfa_method(user: models.User) -> str:
    """Return the only MFA method values the login redirect may expose."""
    return "email" if user.mfa_method == "email" else "totp"

def format_duration(seconds: Optional[int]) -> str:
    if seconds is None:
        return "—"
    m, s = divmod(seconds, 60)
    return f"{m}m {s}s" if m > 0 else f"{s}s"

def format_dt(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def deployment_branch_for_queue(project: models.Project, requested_branch: str) -> str:
    """Bind a release request to the project's reviewed source selection."""

    if (project.source_type or "github") == "upload":
        raise HTTPException(
            status_code=409,
            detail=(
                "Uploaded ZIP projects can be reviewed, but deployment is unavailable until "
                "durable shared source storage is configured for the isolated worker."
            ),
        )
    if (project.source_type or "github") != "github":
        raise HTTPException(status_code=409, detail="This project source type is not deployable.")

    saved_branch = str(project.branch or "").strip()
    if not saved_branch:
        raise HTTPException(
            status_code=409,
            detail="Select and save a GitHub branch before starting a deployment.",
        )
    if requested_branch != saved_branch:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This project is configured for branch '{saved_branch}'. "
                "Review and save a different branch before deploying it."
            ),
        )
    return saved_branch


async def migrate_legacy_environment_secrets() -> None:
    """Move legacy database secret values to Key Vault before clearing them."""
    if not vault.HAS_AZURE_KV or AsyncSessionLocal is None:
        if config.IS_PRODUCTION:
            raise RuntimeError(
                "Azure Key Vault is unavailable; production cannot verify or migrate legacy environment secrets."
            )
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(models.EnvironmentVariable, models.Environment.project_id)
            .join(models.Environment, models.EnvironmentVariable.environment_id == models.Environment.id)
            .filter(models.EnvironmentVariable.is_secret == True, models.EnvironmentVariable.value != "")
        )
        migrated = 0
        failed = 0
        for variable, project_id in result.all():
            try:
                vault.set_project_secret(str(project_id), variable.key, variable.value)
                variable.value = ""
                migrated += 1
            except Exception:
                failed += 1
                logger.error("Unable to migrate one legacy environment secret to Key Vault.")
        if migrated:
            await db.commit()
            logger.info("Migrated %s legacy environment secrets to Key Vault.", migrated)
        if failed and config.IS_PRODUCTION:
            raise RuntimeError(
                "One or more legacy environment secrets could not be migrated to Azure Key Vault."
            )


async def remove_unverified_plan_estimates() -> None:
    """Clear historical placeholder costs, scores, and durations from plans."""
    if AsyncSessionLocal is None:
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(models.InfrastructurePlan))
        sanitized_count = 0
        for plan in result.scalars().all():
            sanitized = planner.clear_unverified_estimates(plan.plan_data or {})
            if sanitized == (plan.plan_data or {}):
                continue
            plan.plan_data = sanitized
            plan.cost_estimate = sanitized.get("cost")
            plan.security_score = sanitized.get("assessment", {}).get("security", {}).get("value")
            plan.performance_score = sanitized.get("assessment", {}).get("performance", {}).get("value")
            plan.reliability_score = sanitized.get("assessment", {}).get("reliability", {}).get("value")
            plan.estimated_deploy_time = sanitized.get("deployment_time", {}).get("estimate")
            sanitized_count += 1
        if sanitized_count:
            await db.commit()
            logger.info("Cleared unverified cost and readiness estimates from %s infrastructure plan(s).", sanitized_count)


async def recover_interrupted_deployments() -> None:
    """Reconcile only expired worker claims; API restarts do not own the queue."""
    if AsyncSessionLocal is None:
        return

    try:
        from worker.queue import stale_job_disposition
    except ImportError:
        def stale_job_disposition(
            deployment_status: str | None,
            attempt_count: int | None,
            max_attempts: int,
        ) -> str:
            if (deployment_status or "queued").lower() == "queued" and (attempt_count or 0) < max_attempts:
                return "requeue"
            if (deployment_status or "").lower() == "running":
                return "complete"
            if (deployment_status or "").lower() == "rolled_back":
                return "cancel"
            return "fail"

    async with AsyncSessionLocal() as db:
        now = datetime.utcnow()
        legacy_cutoff = now - timedelta(seconds=config.WORKER_LEASE_SECONDS)
        result = await db.execute(
            select(models.DeploymentJob, models.Deployment)
            .outerjoin(
                models.Deployment,
                models.Deployment.id == models.DeploymentJob.deployment_id,
            )
            .filter(
                models.DeploymentJob.status == "running",
                or_(
                    models.DeploymentJob.lease_expires_at < now,
                    and_(
                        models.DeploymentJob.lease_expires_at.is_(None),
                        or_(
                            models.DeploymentJob.updated_at.is_(None),
                            models.DeploymentJob.updated_at < legacy_cutoff,
                        ),
                    ),
                ),
            )
            .order_by(models.DeploymentJob.updated_at.asc())
            .limit(config.WORKER_RECOVERY_BATCH_SIZE)
            .with_for_update(skip_locked=True, of=models.DeploymentJob)
        )
        rows = result.all()
        if not rows:
            return

        counts = {"requeued": 0, "completed": 0, "cancelled": 0, "failed": 0}
        for job, deployment in rows:
            disposition = stale_job_disposition(
                deployment.status if deployment else None,
                job.attempt_count,
                config.WORKER_MAX_ATTEMPTS,
            )

            job.worker_id = None
            job.lease_token = None
            job.lease_expires_at = None
            job.heartbeat_at = None

            if disposition == "requeue":
                job.status = "queued"
                job.started_at = None
                job.completed_at = None
                job.failure_reason = None
                counts["requeued"] += 1
                continue

            if disposition == "complete":
                job.status = "completed"
                job.deployment_status = "completed"
                job.live_url = deployment.live_url if deployment else None
                job.failure_reason = None
                job.completed_at = job.completed_at or now
                counts["completed"] += 1
                continue

            if disposition == "cancel":
                job.status = "cancelled"
                job.failure_reason = "The deployment became inactive while its worker lease was stale."
                job.completed_at = job.completed_at or now
                counts["cancelled"] += 1
                continue

            failure_reason = (
                deployment.failure_reason
                if deployment and deployment.failure_reason
                else (
                    "The deployment worker lease expired after release processing started. "
                    "Automatic replay was withheld to avoid duplicate Azure changes."
                )
            )
            job.status = "failed"
            job.deployment_status = "failed"
            job.failure_reason = failure_reason
            job.completed_at = job.completed_at or now
            counts["failed"] += 1

            if not deployment:
                continue
            if deployment.status in {"queued", "building", "deploying"}:
                deployment.status = "failed"
                deployment.failure_reason = deployment.failure_reason or failure_reason
                deployment.completed_at = deployment.completed_at or now
            project_result = await db.execute(
                select(models.Project).filter(models.Project.id == deployment.project_id)
            )
            project = project_result.scalars().first()
            if project and project.status == "deploying":
                project.status = "failed"
            evaluation_result = await db.execute(
                select(models.DecisionEvaluation).filter(
                    models.DecisionEvaluation.deployment_id == deployment.id
                )
            )
            evaluation = evaluation_result.scalars().first()
            if evaluation and evaluation.status == "pending":
                evaluation.status = "failed"
                evaluation.outcome_metadata = {
                    "outcome": "Worker lease expired; automatic replay was withheld.",
                    "completed_at": now.isoformat(),
                }
        await db.commit()
        logger.warning(
            "Reconciled expired deployment leases: %s requeued, %s completed, %s cancelled, %s failed.",
            counts["requeued"],
            counts["completed"],
            counts["cancelled"],
            counts["failed"],
        )


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


SUPPORTED_PAID_OPERATION_TYPES: frozenset[str] = frozenset()
_PAID_OPERATION_UNAVAILABLE_DETAIL = (
    "Paid remediation is not available because ZeroOps AI does not currently "
    "have an implemented execution path for this operation. No checkout was created."
)


def create_stripe_checkout_session(op: models.BillingOperation, user: models.User):
    if op.operation_type not in SUPPORTED_PAID_OPERATION_TYPES:
        raise HTTPException(status_code=501, detail=_PAID_OPERATION_UNAVAILABLE_DETAIL)
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

    if user.mfa_method == "email":
        otp_code = auth.generate_email_otp(config.EMAIL_OTP_LENGTH)
        user.email_otp_hash = auth.hash_otp(otp_code)
        user.email_otp_expires_at = datetime.utcnow() + timedelta(minutes=config.EMAIL_OTP_EXPIRE_MINUTES)
        if not email_service.send_otp_email(user.email, otp_code):
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="We could not deliver the verification code. Please try again shortly.")

    db.add(user)
    await db.commit()
    auth.clear_session_cookies(response)
    auth.set_mfa_challenge_cookie(response, auth.create_mfa_challenge_token(str(user.id), challenge_id))
    return schemas.MFAChallengeResponse(mfa_method=user.mfa_method)


def requires_phone_verification(user: models.User) -> bool:
    """Require phone proof for newly enrolled local accounts without locking out legacy users."""
    return bool(config.PHONE_VERIFICATION_REQUIRED and user.provider == "local" and user.phone_number)


def require_local_enrollment_delivery() -> None:
    if not email_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account verification email delivery is not configured. Please try again later.",
        )
    if config.PHONE_VERIFICATION_REQUIRED and not sms_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Phone verification delivery is not configured. Please try again later.",
        )


async def prepare_and_send_verification_email(user: models.User) -> None:
    """Stage a fresh, single-use verification link without persisting its raw token."""
    raw_token = auth.create_verification_token()
    user.email_verification_token = auth.hash_verification_token(raw_token)
    user.email_verification_expires_at = datetime.utcnow() + timedelta(hours=config.EMAIL_VERIFICATION_EXPIRE_HOURS)
    verification_query = urlencode({"token": raw_token, "email": user.email})
    verification_url = f"{config.FRONTEND_URL}/verify-email?{verification_query}"
    if not email_service.send_verification_email(user.email, verification_url):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="We could not deliver the verification email. Please try again shortly.",
        )


async def begin_phone_verification(
    user: models.User,
    response: Response,
    db: AsyncSession,
    context: str,
) -> schemas.PhoneVerificationPending:
    """Send one phone OTP and bind it to a short-lived, HttpOnly challenge cookie."""
    if not user.phone_number:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Add and verify a phone number before signing in.")
    if not sms_service.is_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Phone verification delivery is unavailable. Please try again later.")

    challenge_id = secrets.token_urlsafe(32)
    otp_code = auth.generate_email_otp(config.PHONE_OTP_LENGTH)
    user.phone_verification_challenge_id = challenge_id
    user.phone_verification_context = context
    user.phone_otp_hash = auth.hash_otp(otp_code)
    user.phone_otp_expires_at = datetime.utcnow() + timedelta(minutes=config.PHONE_OTP_EXPIRE_MINUTES)
    user.phone_otp_attempts = 0
    user.phone_otp_last_sent_at = datetime.utcnow()
    db.add(user)

    if not sms_service.send_phone_verification_otp(user.phone_number, otp_code):
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="We could not deliver the phone verification code. Please try again shortly.")

    await db.commit()
    auth.set_phone_verification_challenge_cookie(
        response,
        auth.create_phone_verification_challenge_token(str(user.id), challenge_id, context),
    )
    return schemas.PhoneVerificationPending(phone_hint=auth.mask_phone_number(user.phone_number))


@app.post("/api/auth/signup", response_model=schemas.EmailVerificationPending)
async def signup(req: schemas.UserCreate, response: Response, db: AsyncSession = Depends(get_db)):
    email = req.email.strip().lower()
    first_name = req.first_name or req.firstName
    last_name = req.last_name or req.lastName
    phone_number = req.phone_number or req.phoneNumber

    require_local_enrollment_delivery()
    if config.PHONE_VERIFICATION_REQUIRED and not phone_number:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A phone number is required to protect this account.")

    try:
        result = await db.execute(select(models.User).filter(models.User.email == email))
        existing_user = result.scalars().first()
    except Exception as error:
        logger.exception("Unable to check whether a signup email already exists.")
        raise HTTPException(status_code=503, detail="Database is currently unavailable.") from error

    if existing_user:
        # Do not reveal whether the address is registered. For an unfinished
        # local enrollment, safely replace the old one-time link and resend it.
        if existing_user.provider == "local" and not existing_user.email_verified:
            try:
                await prepare_and_send_verification_email(existing_user)
                db.add(existing_user)
                await db.commit()
            except HTTPException:
                await db.rollback()
                raise
            except Exception as error:
                await db.rollback()
                logger.exception("Unable to resend an enrollment verification email.")
                raise HTTPException(status_code=503, detail="Unable to continue account verification. Please try again later.") from error
        return schemas.EmailVerificationPending(email=email)

    new_user = models.User(
        id=uuid.uuid4(),
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash=auth.get_password_hash(req.password),
        provider="local",
        plan="starter",
        phone_number=phone_number,
        email_verified=False,
        phone_verified=False,
    )

    try:
        db.add(new_user)
        await db.flush()
        await tenancy.ensure_personal_tenant(db, new_user)
        db.add(models.UserSettings(user_id=new_user.id))
        db.add(models.Notification(
            user_id=new_user.id,
            title="Welcome to ZeroOps AI",
            message="Your ZeroOps workspace is ready. Connect a repository or upload a ZIP to get started.",
            type="success",
            category="system",
        ))
        await prepare_and_send_verification_email(new_user)
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception as error:
        await db.rollback()
        logger.exception("Unable to create a new user account.")
        raise HTTPException(status_code=500, detail="Failed to register user.") from error

    return schemas.EmailVerificationPending(email=email)


@app.post("/api/auth/login", response_model=Union[schemas.UserResponse, schemas.MFAChallengeResponse, schemas.PhoneVerificationPending, schemas.EmailVerificationPending])
async def login(req: schemas.UserLogin, response: Response, db: AsyncSession = Depends(get_db)):
    email = req.email.strip().lower()
    try:
        result = await db.execute(select(models.User).filter(models.User.email == email))
        user = result.scalars().first()
    except Exception as error:
        logger.exception("Unable to look up a login account.")
        raise HTTPException(status_code=503, detail="Database is currently unavailable.") from error

    if user and user.login_locked_until and user.login_locked_until > datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many sign-in attempts. Please try again later.")

    if not user or not user.password_hash or not auth.verify_password(req.password, user.password_hash):
        if user:
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if user.failed_login_count >= config.LOGIN_MAX_FAILURES:
                user.login_locked_until = datetime.utcnow() + timedelta(minutes=config.LOGIN_LOCKOUT_MINUTES)
                user.failed_login_count = 0
            db.add(user)
            await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    if not user.email_verified:
        await prepare_and_send_verification_email(user)
        db.add(user)
        await db.commit()
        return schemas.EmailVerificationPending(email=email)

    if requires_phone_verification(user) and not user.phone_verified:
        return await begin_phone_verification(user, response, db, "login")

    user.failed_login_count = 0
    user.login_locked_until = None
    user.last_primary_auth_at = datetime.utcnow()
    db.add(user)
    await db.commit()

    if user.mfa_enabled and (user.mfa_secret_encrypted or user.mfa_method == "email"):
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
        or (user.mfa_method == "totp" and not user.mfa_secret_encrypted)
        or not user.mfa_challenge_id
        or not user.mfa_challenge_expires_at
        or user.mfa_challenge_expires_at < datetime.utcnow()
        or not hmac.compare_digest(user.mfa_challenge_id, challenge["challenge_id"])
    ):
        auth.clear_mfa_challenge_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your verification session has expired. Sign in again.")

    verified = False

    if user.mfa_method == "email":
        if (
            user.email_otp_hash
            and user.email_otp_expires_at
            and user.email_otp_expires_at >= datetime.utcnow()
            and auth.verify_otp(req.code, user.email_otp_hash)
        ):
            verified = True
            user.email_otp_hash = None
            user.email_otp_expires_at = None
            db.add(user)
    else:  # totp
        secret = auth.decrypt_mfa_secret(user.mfa_secret_encrypted) if user.mfa_secret_encrypted else None
        counter = auth.verify_totp_code(secret, req.code) if secret else None
        if counter is not None:
            if user.mfa_last_used_counter is not None and counter <= user.mfa_last_used_counter:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This verification code was already used. Wait for a new code and try again.")
            user.mfa_last_used_counter = counter
            verified = True
            db.add(user)

    if not verified:
        if auth.consume_recovery_code(user, req.code):
            verified = True
            db.add(user)

    if not verified:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification or recovery code.")

    return await establish_authenticated_session(user, response, db)


@app.get("/api/auth/mfa/status", response_model=schemas.MFAStatusResponse)
async def get_mfa_status(current_user: models.User = Depends(auth.get_current_user)):
    return schemas.MFAStatusResponse(
        enabled=bool(current_user.mfa_enabled and (current_user.mfa_secret_encrypted or current_user.mfa_method == "email")),
        method=current_user.mfa_method or "totp",
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
    if not current_user.mfa_enabled or (current_user.mfa_method == "totp" and not current_user.mfa_secret_encrypted):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Multi-factor authentication is not enabled.")

    verified = False

    if current_user.mfa_method == "email":
        if (
            current_user.email_otp_hash
            and current_user.email_otp_expires_at
            and current_user.email_otp_expires_at >= datetime.utcnow()
            and auth.verify_otp(req.code, current_user.email_otp_hash)
        ):
            verified = True
            current_user.email_otp_hash = None
            current_user.email_otp_expires_at = None
    else:  # totp
        secret = auth.decrypt_mfa_secret(current_user.mfa_secret_encrypted) if current_user.mfa_secret_encrypted else None
        counter = auth.verify_totp_code(secret, req.code) if secret else None
        if counter is not None:
            if current_user.mfa_last_used_counter is not None and counter <= current_user.mfa_last_used_counter:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This verification code was already used. Wait for a new code and try again.")
            current_user.mfa_last_used_counter = counter
            verified = True

    if not verified:
        if auth.consume_recovery_code(current_user, req.code):
            verified = True

    if not verified:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification or recovery code.")

    current_user.mfa_enabled = False
    current_user.mfa_secret_encrypted = None
    current_user.mfa_setup_secret_encrypted = None
    current_user.mfa_setup_expires_at = None
    current_user.mfa_recovery_code_hashes = []
    current_user.mfa_last_used_counter = None
    db.add(current_user)
    await db.commit()
    return {"status": "success", "message": "Multi-factor authentication has been disabled."}


@app.post("/api/auth/verify-email", response_model=Union[schemas.PhoneVerificationPending, schemas.EmailVerificationComplete])
async def verify_email(
    req: schemas.EmailVerificationRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Verify user's email address using the code sent via email."""
    email = req.email.strip().lower()
    result = await db.execute(select(models.User).filter(models.User.email == email))
    user = result.scalars().first()
    if (
        not user
        or not user.email_verification_token
        or not user.email_verification_expires_at
        or user.email_verification_expires_at < datetime.utcnow()
        or not auth.verify_verification_token(req.token, user.email_verification_token)
    ):
        raise HTTPException(
            status_code=400,
            detail="The verification code is invalid or has expired. Please request a new one."
        )
    user.email_verified = True
    user.email_verification_token = None
    user.email_verification_expires_at = None
    db.add(user)

    if requires_phone_verification(user):
        # begin_phone_verification commits both verification steps only after
        # the SMS provider accepts delivery.
        return await begin_phone_verification(user, response, db, "signup")

    await db.commit()
    return schemas.EmailVerificationComplete()


@app.post("/api/auth/resend-verification")
async def resend_verification(req: schemas.ResendVerificationRequest, db: AsyncSession = Depends(get_db)):
    """Resend verification email to unverified user."""
    email = req.email.strip().lower()
    result = await db.execute(select(models.User).filter(models.User.email == email))
    user = result.scalars().first()
    
    # Always return the same acknowledgement so this endpoint cannot be used
    # to discover whether an account exists or has already been verified.
    acknowledgement = {"status": "success", "message": "If this email can be verified, we have sent a verification link."}
    if not user or user.email_verified:
        return acknowledgement
    if not email_service.is_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Verification email delivery is unavailable. Please try again later.")

    try:
        await prepare_and_send_verification_email(user)
        db.add(user)
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception as error:
        await db.rollback()
        logger.exception("Unable to resend verification email.")
        raise HTTPException(status_code=503, detail="Unable to send verification email. Please try again later.") from error
    return acknowledgement


@app.post("/api/auth/verify-phone", response_model=Union[schemas.UserResponse, schemas.PhoneVerificationComplete])
async def verify_phone(
    req: schemas.MFACodeRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    challenge = auth.decode_phone_verification_challenge(request)
    try:
        user_id = uuid.UUID(challenge["sub"])
    except ValueError as error:
        auth.clear_phone_verification_challenge_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your phone verification session is invalid. Start again.") from error

    result = await db.execute(select(models.User).filter(models.User.id == user_id))
    user = result.scalars().first()
    if (
        not user
        or not user.phone_number
        or not user.phone_otp_hash
        or not user.phone_otp_expires_at
        or user.phone_otp_expires_at < datetime.utcnow()
        or not user.phone_verification_challenge_id
        or user.phone_verification_context != challenge["context"]
        or not hmac.compare_digest(user.phone_verification_challenge_id, challenge["challenge_id"])
    ):
        auth.clear_phone_verification_challenge_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your phone verification session has expired. Start again.")

    if user.phone_otp_attempts >= config.PHONE_OTP_MAX_ATTEMPTS:
        user.phone_otp_hash = None
        user.phone_otp_expires_at = None
        user.phone_verification_challenge_id = None
        user.phone_verification_context = None
        db.add(user)
        await db.commit()
        auth.clear_phone_verification_challenge_cookie(response)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many invalid codes. Start phone verification again.")

    if not auth.verify_otp(req.code, user.phone_otp_hash):
        user.phone_otp_attempts = (user.phone_otp_attempts or 0) + 1
        db.add(user)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="That verification code is invalid. Please try again.")

    context = user.phone_verification_context
    user.phone_verified = True
    user.phone_otp_hash = None
    user.phone_otp_expires_at = None
    user.phone_otp_attempts = 0
    user.phone_otp_last_sent_at = None
    user.phone_verification_challenge_id = None
    user.phone_verification_context = None
    user.failed_login_count = 0
    user.login_locked_until = None
    if context == "login":
        user.last_primary_auth_at = datetime.utcnow()
    db.add(user)

    if context == "login":
        authenticated_user = await establish_authenticated_session(user, response, db)
        auth.clear_phone_verification_challenge_cookie(response)
        return authenticated_user

    await db.commit()
    auth.clear_phone_verification_challenge_cookie(response)
    return schemas.PhoneVerificationComplete(authenticated=False)


@app.post("/api/auth/resend-phone-verification", response_model=schemas.PhoneVerificationPending)
async def resend_phone_verification(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    challenge = auth.decode_phone_verification_challenge(request)
    try:
        user_id = uuid.UUID(challenge["sub"])
    except ValueError as error:
        auth.clear_phone_verification_challenge_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your phone verification session is invalid. Start again.") from error

    result = await db.execute(select(models.User).filter(models.User.id == user_id))
    user = result.scalars().first()
    if (
        not user
        or not user.phone_number
        or not user.phone_verification_challenge_id
        or user.phone_verification_context != challenge["context"]
        or not hmac.compare_digest(user.phone_verification_challenge_id, challenge["challenge_id"])
    ):
        auth.clear_phone_verification_challenge_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your phone verification session has expired. Start again.")

    now = datetime.utcnow()
    if user.phone_otp_last_sent_at and (now - user.phone_otp_last_sent_at).total_seconds() < config.PHONE_OTP_RESEND_COOLDOWN_SECONDS:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Please wait before requesting another code.")

    otp_code = auth.generate_email_otp(config.PHONE_OTP_LENGTH)
    user.phone_otp_hash = auth.hash_otp(otp_code)
    user.phone_otp_expires_at = now + timedelta(minutes=config.PHONE_OTP_EXPIRE_MINUTES)
    user.phone_otp_attempts = 0
    user.phone_otp_last_sent_at = now
    db.add(user)
    if not sms_service.send_phone_verification_otp(user.phone_number, otp_code):
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="We could not deliver the phone verification code. Please try again shortly.")
    await db.commit()
    return schemas.PhoneVerificationPending(phone_hint=auth.mask_phone_number(user.phone_number))


@app.post("/api/auth/mfa/method")
async def update_mfa_method(
    req: schemas.MFAMethodRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Switch the preferred MFA method (totp or email)."""
    if req.method == "totp" and not current_user.mfa_secret_encrypted:
        raise HTTPException(status_code=400, detail="Please set up your authenticator app first.")
        
    current_user.mfa_method = req.method
    db.add(current_user)
    await db.commit()
    return {"status": "success", "message": f"MFA method updated to {req.method}."}


@app.post("/api/auth/mfa/setup/email", response_model=schemas.MFASetupConfirmResponse)
async def setup_email_mfa(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Enable email-based MFA directly."""
    if current_user.mfa_enabled and current_user.mfa_method == "email":
        raise HTTPException(status_code=409, detail="Email MFA is already enabled.")
    if not auth.is_recent_primary_authentication(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sign out and sign in again before changing multi-factor authentication.")

    # Generate recovery codes
    recovery_codes, recovery_code_hashes = auth.generate_recovery_codes()
    current_user.mfa_enabled = True
    current_user.mfa_method = "email"
    current_user.mfa_recovery_code_hashes = recovery_code_hashes
    
    # We clear TOTP secrets if switching entirely to email MFA
    current_user.mfa_secret_encrypted = None
    current_user.mfa_setup_secret_encrypted = None
    current_user.mfa_setup_expires_at = None
    current_user.mfa_last_used_counter = None

    db.add(current_user)
    await db.commit()
    return schemas.MFASetupConfirmResponse(recovery_codes=recovery_codes)


@app.post("/api/auth/mfa/resend-otp")
async def resend_mfa_otp(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Resend email MFA OTP if user is in an active challenge."""
    challenge = auth.decode_mfa_challenge(request)
    try:
        user_id = uuid.UUID(challenge["sub"])
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification session.") from error

    result = await db.execute(select(models.User).filter(models.User.id == user_id))
    user = result.scalars().first()
    if (
        not user
        or not user.mfa_enabled
        or user.mfa_method != "email"
        or not user.mfa_challenge_id
        or not hmac.compare_digest(user.mfa_challenge_id, challenge["challenge_id"])
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification session.")

    otp_code = auth.generate_email_otp(config.EMAIL_OTP_LENGTH)
    user.email_otp_hash = auth.hash_otp(otp_code)
    user.email_otp_expires_at = datetime.utcnow() + timedelta(minutes=config.EMAIL_OTP_EXPIRE_MINUTES)
    db.add(user)
    if not email_service.send_otp_email(user.email, otp_code):
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="We could not deliver the verification code. Please try again shortly.")
    await db.commit()

    return {"status": "success", "message": "Verification code resent."}


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
        "aks_cluster_name": connection.aks_cluster_name,
        "namespace_prefix": connection.namespace_prefix,
        "created_at": format_dt(connection.created_at),
        "updated_at": format_dt(connection.updated_at),
    }


async def compensate_failed_azure_connection_write(
    db: AsyncSession,
    azure_connector,
    user_id: uuid.UUID,
    previous_secret: Optional[str],
) -> None:
    """Roll back database state and restore the credential boundary if possible."""
    try:
        await db.rollback()
    except Exception:
        logger.exception("Unable to roll back a failed Azure connection write.")

    if previous_secret is not None:
        restored = azure_connector.store_credential_in_vault(user_id, previous_secret)
        action = "restore the previous"
    else:
        restored = azure_connector.delete_credential_from_vault(user_id)
        action = "remove the newly stored"
    if not restored:
        logger.error("Unable to %s Azure credential after a database failure.", action)


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

    existing = await get_active_azure_connection(db, current_user.id)
    previous_secret = (
        azure_connector.get_credential_secret(current_user.id)
        if existing
        else None
    )

    # Store SP client secret in vault
    store_ok = azure_connector.store_credential_in_vault(current_user.id, req.client_secret)
    if not store_ok:
        raise HTTPException(
            status_code=503,
            detail="Azure Key Vault could not store the client secret. The connection was not saved.",
        )

    # Find existing or create new connection
    if existing:
        existing.tenant_id = req.tenant_id.strip()
        existing.subscription_id = req.subscription_id.strip()
        existing.client_id = req.client_id.strip()
        existing.region = req.region or config.AZURE_DEFAULT_REGION
        existing.resource_group = req.resource_group.strip()
        existing.acr_login_server = req.acr_login_server.strip().rstrip("/") if req.acr_login_server else None
        existing.app_service_plan = req.app_service_plan.strip() if req.app_service_plan else None
        existing.aks_cluster_name = req.aks_cluster_name.strip() if req.aks_cluster_name else None
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
            aks_cluster_name=req.aks_cluster_name.strip() if req.aks_cluster_name else None,
            namespace_prefix=req.namespace_prefix.strip() if req.namespace_prefix else None,
            connection_status="connected",
            is_active=True,
        )
        db.add(connection)

    try:
        await db.commit()
    except Exception as error:
        await compensate_failed_azure_connection_write(
            db,
            azure_connector,
            current_user.id,
            previous_secret,
        )
        raise HTTPException(
            status_code=503,
            detail="The Azure connection record could not be saved. The credential update was reverted where possible.",
        ) from error
    
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
        await db.rollback()
        logger.error("Failed to write the Azure connection audit entry: %s", audit_err)

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
        "aks_cluster_name": connection.aks_cluster_name,
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
    previous_secret = (
        azure_connector.get_credential_secret(current_user.id)
        if existing
        else None
    )
    secret_to_use = req.client_secret or previous_secret
        
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

    # Persist the secret before claiming the connection is active. If the
    # database write fails, restore the prior vault value (or remove the new
    # one for a first-time connection).
    store_ok = azure_connector.store_credential_in_vault(current_user.id, secret_to_use)
    if not store_ok:
        raise HTTPException(
            status_code=503,
            detail="Azure Key Vault could not store the client secret. The connection was not saved.",
        )

    if existing:
        existing.tenant_id = req.tenant_id.strip()
        existing.subscription_id = req.subscription_id.strip()
        existing.client_id = req.client_id.strip() if req.client_id else existing.client_id
        existing.region = req.region or config.AZURE_DEFAULT_REGION
        existing.resource_group = req.resource_group.strip() if req.resource_group else existing.resource_group
        existing.acr_login_server = req.acr_login_server.strip().rstrip("/") if req.acr_login_server else existing.acr_login_server
        existing.app_service_plan = req.app_service_plan.strip() if req.app_service_plan else existing.app_service_plan
        existing.aks_cluster_name = (
            req.aks_cluster_name.strip()
            if req.aks_cluster_name
            else getattr(existing, "aks_cluster_name", None)
        )
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
            aks_cluster_name=req.aks_cluster_name.strip() if req.aks_cluster_name else None,
            namespace_prefix=req.namespace_prefix.strip() if req.namespace_prefix else None,
            connection_status="connected",
            is_active=True,
        )
        db.add(connection)

    try:
        await db.commit()
    except Exception as error:
        await compensate_failed_azure_connection_write(
            db,
            azure_connector,
            current_user.id,
            previous_secret,
        )
        raise HTTPException(
            status_code=503,
            detail="The Azure connection record could not be saved. The credential update was reverted where possible.",
        ) from error
    return {
        "connected": True,
        "subscription_id": connection.subscription_id,
        "region": connection.region,
        "resource_group": connection.resource_group,
        "acr_login_server": connection.acr_login_server,
        "app_service_plan": connection.app_service_plan,
        "aks_cluster_name": connection.aks_cluster_name,
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

    previous_secret = azure_connector.get_credential_secret(current_user.id)
    if not azure_connector.delete_credential_from_vault(current_user.id):
        raise HTTPException(
            status_code=503,
            detail=(
                "Azure Key Vault could not confirm client-secret revocation. "
                "The connection remains recorded as active."
            ),
        )

    connection.connection_status = "revoked"
    connection.is_active = False
    connection.updated_at = datetime.utcnow()

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
        logger.error("Failed to prepare the Azure disconnect audit entry: %s", audit_err)

    try:
        await db.commit()
    except Exception as error:
        await compensate_failed_azure_connection_write(
            db,
            azure_connector,
            current_user.id,
            previous_secret,
        )
        raise HTTPException(
            status_code=503,
            detail="The disconnect record could not be saved. The credential was restored where possible.",
        ) from error
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
    if req.operation_type not in SUPPORTED_PAID_OPERATION_TYPES:
        raise HTTPException(status_code=501, detail=_PAID_OPERATION_UNAVAILABLE_DETAIL)

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
    if operation.operation_type not in SUPPORTED_PAID_OPERATION_TYPES:
        raise HTTPException(status_code=501, detail=_PAID_OPERATION_UNAVAILABLE_DETAIL)
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
            try:
                parsed_operation_id = uuid.UUID(operation_id)
            except (TypeError, ValueError):
                logger.warning("Ignored Stripe completion with an invalid operation identifier.")
                return {"received": True}

            result = await db.execute(
                select(models.BillingOperation).filter(models.BillingOperation.id == parsed_operation_id)
            )
            operation = result.scalars().first()
            checkout_matches_operation = bool(
                operation
                and operation.operation_type in SUPPORTED_PAID_OPERATION_TYPES
                and operation.status == "pending_payment"
                and session.get("payment_status") == "paid"
                and session.get("mode") == "payment"
                and session.get("id") == operation.provider_reference
                and metadata.get("user_id") == str(operation.user_id)
                and metadata.get("operation_type") == operation.operation_type
                and session.get("amount_total") == operation.amount_cents
                and str(session.get("currency") or "").lower() == operation.currency.lower()
            )
            if checkout_matches_operation:
                operation.status = "paid"
                operation.provider_reference = session.get("id") or operation.provider_reference
                operation.paid_at = datetime.utcnow()
                await db.commit()
            elif operation:
                logger.warning(
                    "Ignored Stripe completion that did not match an available billing operation."
                )

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
    if operation.operation_type not in SUPPORTED_PAID_OPERATION_TYPES:
        raise HTTPException(status_code=501, detail=_PAID_OPERATION_UNAVAILABLE_DETAIL)
    operation.status = "paid"
    operation.paid_at = datetime.utcnow()
    await db.commit()
    return map_billing_operation(operation)


@app.post("/api/projects/{project_id}/self-heal")
async def self_heal_project(
    project_id: uuid.UUID,
    req: schemas.SelfHealRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(models.Project.id).filter(
            models.Project.id == project_id,
            models.Project.user_id == current_user.id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    raise HTTPException(
        status_code=501,
        detail=(
            "Automated remediation is not available. Use the reviewed deployment workflow "
            "for a new release and manage live Azure resources through verified provider operations."
        ),
    )


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
        if m.cpu_utilization is not None:
            cpu_data.append({"time": time_str, "value": m.cpu_utilization})
        if m.memory_utilization is not None:
            mem_data.append({"time": time_str, "value": m.memory_utilization})

    avg_resp = "No data"
    avg_err = "No data"
    total_reqs = 0
    uptime = "No data"
    if metrics:
        response_samples = [m.response_time_ms for m in metrics if m.response_time_ms is not None]
        error_samples = [m.error_rate for m in metrics if m.error_rate is not None]
        request_samples = [m.request_count for m in metrics if m.request_count is not None]
        if response_samples:
            avg_resp = f"{int(sum(response_samples) / len(response_samples))}ms"
        if error_samples:
            avg_err = f"{round(sum(error_samples) / len(error_samples), 2)}%"
        total_reqs = sum(request_samples) if request_samples else 0
        
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

    selected_branch = deployment_branch_for_queue(project, req.branch)
    encrypted_github_token = current_user.github_access_token_encrypted
    if not encrypted_github_token:
        raise HTTPException(
            status_code=409,
            detail="Reconnect GitHub before deploying this repository.",
        )
    try:
        github_token = github_oauth.decrypt_token(encrypted_github_token)
    except Exception as error:
        logger.warning("Unable to decrypt GitHub credentials for deployment user %s.", current_user.id)
        raise HTTPException(
            status_code=409,
            detail="Reconnect GitHub before deploying this repository.",
        ) from error

    commit_sha = await github_oauth.resolve_branch_commit(
        github_token,
        project.full_name,
        selected_branch,
    )
    if not commit_sha:
        raise HTTPException(
            status_code=503,
            detail=(
                "The saved GitHub branch could not be resolved to an immutable commit. "
                "No deployment was queued; verify repository access and try again."
            ),
        )

    plan_result = await db.execute(
        select(models.InfrastructurePlan).filter(
            models.InfrastructurePlan.project_id == project.id,
            models.InfrastructurePlan.user_id == current_user.id,
        )
    )
    approved_plan = plan_result.scalars().first()
    if not approved_plan or approved_plan.status != "approved":
        raise HTTPException(
            status_code=409,
            detail="Review and approve the AI infrastructure plan before starting a deployment.",
        )

    azure_connection = await get_active_azure_connection(db, current_user.id)
    target_status = deployment_targets.status_payload(azure_connection)
    preflight = await _run_digital_twin(
        db,
        project=project,
        user_id=current_user.id,
        plan=approved_plan,
    )
    await db.flush()
    if preflight.status == "blocked":
        db.add(models.ActivityEvent(
            user_id=current_user.id,
            project_id=project.id,
            action="Deployment blocked by digital twin preflight",
            details=f"Execution did not start because the deterministic preflight returned risk {preflight.risk_score}/100.",
        ))
        await db.commit()
        raise HTTPException(
            status_code=409,
            detail="Deployment was blocked by the digital-twin preflight. Resolve its blocking architecture, source-evidence, or Azure-target checks before retrying.",
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

    deployment_id = uuid.uuid4()
    version = f"v{datetime.utcnow().strftime('%Y%m%d')}.{deployment_id.hex[:12]}"
    namespace_prefix = deployment_targets.namespace_prefix(selected_target, current_user.id)
    image_name = pipeline.normalize_project_id(
        f"{namespace_prefix}-{project.name}-{str(project.id)[:8]}"
    )
    image_ref = deployment_targets.image_ref_for_target(selected_target, image_name, version)
    tenant = await tenancy.resolve_tenant(db, user=current_user)
    pipeline_config_result = await db.execute(
        select(models.ProjectPipelineConfiguration)
        .filter(
            models.ProjectPipelineConfiguration.tenant_id == tenant.id,
            models.ProjectPipelineConfiguration.project_id == project.id,
        )
        .order_by(desc(models.ProjectPipelineConfiguration.version))
        .limit(1)
    )
    pipeline_configuration = pipeline_config_result.scalars().first()
    pipeline_context = pipeline_records.context_from_configuration(
        pipeline_configuration,
        target_type=selected_target.provider,
        has_dependencies=True,
        has_tests=bool(pipeline_configuration.run_unit_tests) if pipeline_configuration else True,
        # The approved architecture is an input to the existing App Service
        # path, not proof that repository Terraform changed in this commit.
        has_iac=False,
        infrastructure_change=False,
    )
    planned_stages = pipeline.initialize_pipeline_stages(pipeline_context)

    # Create deployment record
    deployment = models.Deployment(
        id=deployment_id,
        user_id=current_user.id,
        project_id=project.id,
        status="queued",
        environment=req.environment,
        branch=selected_branch,
        version=version,
        commit_sha=commit_sha,
        deployed_by=f"{current_user.first_name or 'User'} {(current_user.last_name or '')[0:1]}.".strip(),
        image=image_ref,
        infrastructure_metadata={
            # Preserve the caller's target intent so the isolated worker can
            # re-evaluate an automatic choice against the immutable checkout,
            # rather than trusting a potentially stale pre-clone analysis.
            "requested_target": (
                "auto"
                if (req.target_provider or "auto").strip().lower() == "auto"
                else selected_target.provider
            ),
            "target_provider": selected_target.provider,
            "target_reason": selected_target.reason,
            "target": deployment_targets.metadata_for_target(selected_target),
            "available_targets": target_status["targets"],
            "source_type": project.source_type,
            "source_revision": {
                "provider": "github",
                "branch": selected_branch,
                "commit_sha": commit_sha,
            },
            "architecture_plan": {
                "id": str(approved_plan.id),
                "revision": approved_plan.revision,
                "provider": approved_plan.provider,
                "region": approved_plan.region,
            },
            "pipeline_configuration": (
                {
                    "id": str(pipeline_configuration.id),
                    "version": pipeline_configuration.version,
                    "digest": pipeline_configuration.config_digest or "",
                }
                if pipeline_configuration
                else None
            ),
            "pipeline_approval_decision": {
                "status": (
                    "pending"
                    if pipeline_configuration
                    and pipeline_configuration.deployment_mode == "require_approval"
                    else "not_required"
                ),
                "consumed": False,
            },
            "preflight": {
                "id": str(preflight.id),
                "status": preflight.status,
                "risk_score": preflight.risk_score,
                "risk_level": preflight.risk_level,
                "model": decision_intelligence.RISK_MODEL_VERSION,
            },
            "stages": planned_stages,
        }
    )
    db.add(deployment)
    await db.flush()

    previous_success_result = await db.execute(
        select(models.Deployment.commit_sha)
        .filter(
            models.Deployment.project_id == project.id,
            models.Deployment.id != deployment.id,
            models.Deployment.status == "running",
            models.Deployment.commit_sha.is_not(None),
        )
        .order_by(desc(models.Deployment.completed_at))
        .limit(1)
    )
    await pipeline_records.create_pipeline_run(
        db,
        tenant_id=tenant.id,
        project_id=project.id,
        deployment_id=deployment.id,
        requested_by_user_id=current_user.id,
        configuration=pipeline_configuration,
        trigger_type="manual",
        branch=selected_branch,
        source_revision=commit_sha,
        target_type=selected_target.provider,
        idempotency_key=f"manual:{deployment.id}",
        context=pipeline_context,
        previous_successful_revision=previous_success_result.scalar_one_or_none(),
    )

    db.add(models.DecisionEvaluation(
        user_id=current_user.id,
        project_id=project.id,
        infrastructure_plan_id=approved_plan.id,
        deployment_id=deployment.id,
        plan_revision=approved_plan.revision,
        recommendation={
            "provider": approved_plan.provider,
            "region": approved_plan.region,
            "components": [
                {
                    "id": component.get("id"),
                    "service": component.get("service"),
                    "tier": component.get("tier"),
                }
                for component in (approved_plan.plan_data or {}).get("components", [])
            ],
            "preflight_risk_score": preflight.risk_score,
        },
        status="pending",
    ))

    # Update project status
    project.status = "deploying"

    # Create notification
    db.add(models.Notification(
        user_id=current_user.id,
        title="Deployment Started",
        message=(
            f"Queued {project.full_name} at {commit_sha[:12]} "
            f"for {req.environment} on {selected_target.label}."
        ),
        type="info",
        category="deployment"
    ))

    # Create a deployment job without copying an OAuth token into the queue.
    # The worker decrypts the user's encrypted token only for the active run.
    job = models.DeploymentJob(
        id=uuid.uuid4(),
        user_id=current_user.id,
        project_id=project.id,
        deployment_id=deployment.id,
        status="queued",
        cloud="azure",
        region=approved_plan.region,
        infrastructure_spec=approved_plan.plan_data,
    )
    db.add(job)
    await db.commit()
    await db.refresh(deployment)

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
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(models.Deployment.id).filter(
            models.Deployment.id == deploy_id,
            models.Deployment.user_id == current_user.id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Deployment not found.")
    raise HTTPException(
        status_code=501,
        detail="Automatic source-code changes are disabled. Review the recorded failure, update your repository, and launch a new version.",
    )


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
    raise HTTPException(
        status_code=501,
        detail=(
            "Applying AI recommendations is not available. Review the recommendation "
            "and make the change through the repository or verified deployment workflow."
        ),
    )


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
    # Repository contents must be fetched with the requesting user's GitHub
    # authorization. A service-wide token could expose repositories that the
    # signed-in ZeroOps user is not entitled to inspect.
    user_token = None
    if current_user.github_connected and current_user.github_access_token_encrypted:
        try:
            user_token = github_oauth.decrypt_token(current_user.github_access_token_encrypted)
        except Exception:
            pass
            
    if not user_token:
        raise HTTPException(
            status_code=400,
            detail="Connect GitHub before analyzing a GitHub repository.",
        )
    clone_token = user_token
    
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
        db_recommendation.recommended_target = None
        db_recommendation.azure_configuration = {
            "selected_provider": None,
            "target": None,
            "reason": str(target_err),
        }
        analysis["recommended_provider"] = "none"
        analysis["recommended_target"] = None
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


def _serialize_infrastructure_plan(plan: models.InfrastructurePlan) -> schemas.InfrastructurePlanResponse:
    """Return the architecture decision record without internal IaC details."""
    return schemas.InfrastructurePlanResponse(
        id=plan.id,
        project_id=plan.project_id,
        provider=plan.provider,
        region=plan.region,
        status=plan.status,
        revision=plan.revision,
        plan=plan.plan_data or {},
        cost_estimate=plan.cost_estimate or {},
        security_score=plan.security_score,
        performance_score=plan.performance_score,
        reliability_score=plan.reliability_score,
        estimated_deploy_time=plan.estimated_deploy_time,
        ai_explanations=plan.ai_explanations or {},
        approval_note=plan.approval_note,
        approved_at=format_dt(plan.approved_at),
        created_at=format_dt(plan.created_at),
        updated_at=format_dt(plan.updated_at),
    )


async def _owned_project_or_404(
    project_id: uuid.UUID,
    current_user: models.User,
    db: AsyncSession,
) -> models.Project:
    result = await db.execute(
        select(models.Project).filter(
            models.Project.id == project_id,
            models.Project.user_id == current_user.id,
        )
    )
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _analysis_to_plan_facts(analysis: models.AIAnalysis | None) -> dict[str, Any]:
    if not analysis:
        return {}
    return {
        "framework": analysis.framework,
        "runtime": analysis.runtime,
        "package_manager": analysis.package_manager,
        "docker_support": analysis.docker_support,
        "database_dependencies": analysis.database_dependencies or [],
        "environment_variables": analysis.environment_variables or [],
        "vulnerabilities": analysis.vulnerabilities or [],
        "unresolved_questions": [],
    }


async def _latest_project_analysis(db: AsyncSession, project_id: uuid.UUID) -> models.AIAnalysis | None:
    result = await db.execute(
        select(models.AIAnalysis)
        .filter(models.AIAnalysis.project_id == project_id)
        .order_by(desc(models.AIAnalysis.created_at))
        .limit(1)
    )
    return result.scalars().first()


def _serialize_digital_twin(simulation: models.DigitalTwinSimulation) -> schemas.DigitalTwinSimulationResponse:
    checks = simulation.checks or []
    return schemas.DigitalTwinSimulationResponse(
        id=simulation.id,
        project_id=simulation.project_id,
        plan_revision=simulation.plan_revision,
        model=decision_intelligence.RISK_MODEL_VERSION,
        status=simulation.status,
        risk_score=simulation.risk_score,
        risk_level=simulation.risk_level,
        summary=simulation.summary,
        snapshot=simulation.snapshot or {},
        checks=checks,
        proposed_changes=[
            str(check.get("detail"))
            for check in checks
            if isinstance(check, dict) and check.get("status") in {"blocked", "warning"} and check.get("detail")
        ],
        created_at=format_dt(simulation.created_at),
    )


async def _store_knowledge_graph(
    db: AsyncSession,
    *,
    project: models.Project,
    user_id: uuid.UUID,
    analysis: models.AIAnalysis | None,
    plan: models.InfrastructurePlan,
) -> models.KnowledgeGraphSnapshot:
    """Persist an auditable graph after an architecture decision changes."""
    graph = decision_intelligence.build_knowledge_graph(
        project=project,
        analysis=_analysis_to_plan_facts(analysis),
        plan=plan.plan_data or {},
        plan_revision=plan.revision,
    )
    snapshot = models.KnowledgeGraphSnapshot(
        user_id=user_id,
        project_id=project.id,
        plan_revision=plan.revision,
        graph_data=graph,
    )
    db.add(snapshot)
    return snapshot


async def _run_digital_twin(
    db: AsyncSession,
    *,
    project: models.Project,
    user_id: uuid.UUID,
    plan: models.InfrastructurePlan,
) -> models.DigitalTwinSimulation:
    """Run and persist a non-mutating deployment preflight."""
    analysis = await _latest_project_analysis(db, project.id)
    azure_connection = await get_active_azure_connection(db, user_id)
    result = decision_intelligence.simulate_digital_twin(
        project=project,
        plan=plan.plan_data or {},
        plan_revision=plan.revision,
        analysis=_analysis_to_plan_facts(analysis),
        target_status=deployment_targets.status_payload(azure_connection),
        plan_approved=plan.status == "approved",
    )
    simulation = models.DigitalTwinSimulation(
        user_id=user_id,
        project_id=project.id,
        infrastructure_plan_id=plan.id,
        plan_revision=plan.revision,
        status=result["status"],
        risk_score=result["risk_score"],
        risk_level=result["risk_level"],
        snapshot=result["snapshot"],
        checks=result["checks"],
        summary=result["summary"],
    )
    db.add(simulation)
    return simulation


@app.post(
    "/api/projects/{project_id}/infrastructure-plan/generate",
    response_model=schemas.InfrastructurePlanResponse,
)
async def generate_infrastructure_plan(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or refresh a project architecture plan from recorded source facts."""
    project = await _owned_project_or_404(project_id, current_user, db)
    analysis = await _latest_project_analysis(db, project.id)
    if not analysis:
        raise HTTPException(status_code=409, detail="Analyze this application before creating an infrastructure plan.")

    azure_connection = await get_active_azure_connection(db, current_user.id)
    region = str(
        getattr(azure_connection, "region", None)
        or project.region
        or config.AZURE_DEFAULT_REGION
    )
    plan_data = planner.build_infrastructure_spec(
        _analysis_to_plan_facts(analysis),
        region=region,
        azure_connection=azure_connection,
    )

    existing_result = await db.execute(
        select(models.InfrastructurePlan).filter(
            models.InfrastructurePlan.project_id == project.id,
            models.InfrastructurePlan.user_id == current_user.id,
        )
    )
    record = existing_result.scalars().first()
    if record:
        record.provider = "azure"
        record.region = region
        record.status = "draft"
        record.revision += 1
        record.plan_data = plan_data
        record.cost_estimate = plan_data.get("cost")
        record.security_score = plan_data.get("assessment", {}).get("security", {}).get("value")
        record.performance_score = plan_data.get("assessment", {}).get("performance", {}).get("value")
        record.reliability_score = plan_data.get("assessment", {}).get("reliability", {}).get("value")
        record.estimated_deploy_time = plan_data.get("deployment_time", {}).get("estimate")
        record.ai_explanations = plan_data.get("ai_explanations")
        record.approval_note = None
        record.approved_at = None
    else:
        record = models.InfrastructurePlan(
            user_id=current_user.id,
            project_id=project.id,
            provider="azure",
            region=region,
            plan_data=plan_data,
            cost_estimate=plan_data.get("cost"),
            security_score=plan_data.get("assessment", {}).get("security", {}).get("value"),
            performance_score=plan_data.get("assessment", {}).get("performance", {}).get("value"),
            reliability_score=plan_data.get("assessment", {}).get("reliability", {}).get("value"),
            estimated_deploy_time=plan_data.get("deployment_time", {}).get("estimate"),
            ai_explanations=plan_data.get("ai_explanations"),
        )
        db.add(record)

    db.add(models.ActivityEvent(
        user_id=current_user.id,
        project_id=project.id,
        action="Infrastructure plan generated",
        details="Architecture decisions were generated from the latest repository analysis.",
    ))
    await _store_knowledge_graph(
        db,
        project=project,
        user_id=current_user.id,
        analysis=analysis,
        plan=record,
    )
    await db.commit()
    await db.refresh(record)
    return _serialize_infrastructure_plan(record)


@app.get(
    "/api/projects/{project_id}/infrastructure-plan",
    response_model=schemas.InfrastructurePlanResponse,
)
async def get_infrastructure_plan(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _owned_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(models.InfrastructurePlan).filter(
            models.InfrastructurePlan.project_id == project_id,
            models.InfrastructurePlan.user_id == current_user.id,
        )
    )
    plan = result.scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="No infrastructure plan has been generated for this project yet.")
    return _serialize_infrastructure_plan(plan)


@app.patch(
    "/api/projects/{project_id}/infrastructure-plan",
    response_model=schemas.InfrastructurePlanResponse,
)
async def update_infrastructure_plan(
    project_id: uuid.UUID,
    req: schemas.InfrastructurePlanUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not any([req.region, req.component_id, req.service, req.tier]):
        raise HTTPException(status_code=400, detail="Choose a region or resource setting to update.")
    project = await _owned_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(models.InfrastructurePlan).filter(
            models.InfrastructurePlan.project_id == project_id,
            models.InfrastructurePlan.user_id == current_user.id,
        )
    )
    plan = result.scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Generate an infrastructure plan before modifying it.")

    try:
        updated_plan_data = planner.apply_plan_update(
            plan.plan_data or {},
            region=req.region,
            component_id=req.component_id,
            service=req.service,
            tier=req.tier,
        )
        plan.plan_data = updated_plan_data
        plan.cost_estimate = updated_plan_data.get("cost")
        plan.security_score = updated_plan_data.get("assessment", {}).get("security", {}).get("value")
        plan.performance_score = updated_plan_data.get("assessment", {}).get("performance", {}).get("value")
        plan.reliability_score = updated_plan_data.get("assessment", {}).get("reliability", {}).get("value")
        plan.estimated_deploy_time = updated_plan_data.get("deployment_time", {}).get("estimate")
        if req.region:
            plan.region = planner.normalize_region(req.region)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    plan.status = "draft"
    plan.revision += 1
    plan.approval_note = None
    plan.approved_at = None
    db.add(models.ActivityEvent(
        user_id=current_user.id,
        project_id=project_id,
        action="Infrastructure plan updated",
        details="Architecture settings changed; approval is required again before deployment.",
    ))
    await _store_knowledge_graph(
        db,
        project=project,
        user_id=current_user.id,
        analysis=await _latest_project_analysis(db, project.id),
        plan=plan,
    )
    await db.commit()
    await db.refresh(plan)
    return _serialize_infrastructure_plan(plan)


@app.post(
    "/api/projects/{project_id}/infrastructure-plan/approve",
    response_model=schemas.InfrastructurePlanResponse,
)
async def approve_infrastructure_plan(
    project_id: uuid.UUID,
    req: schemas.InfrastructurePlanApproval,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _owned_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(models.InfrastructurePlan).filter(
            models.InfrastructurePlan.project_id == project_id,
            models.InfrastructurePlan.user_id == current_user.id,
        )
    )
    plan = result.scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Generate an infrastructure plan before approval.")

    application = next(
        (component for component in (plan.plan_data or {}).get("components", []) if component.get("id") == "application"),
        None,
    )
    if not application or application.get("service") != "Azure App Service":
        raise HTTPException(
            status_code=409,
            detail="This workspace can currently deploy approved Azure App Service plans only. Select App Service or configure another deployment engine before approval.",
        )

    plan.status = "approved"
    plan.approval_note = req.note.strip() if req.note else None
    plan.approved_at = datetime.utcnow()
    db.add(models.ActivityEvent(
        user_id=current_user.id,
        project_id=project_id,
        action="Infrastructure plan approved",
        details="The approved architecture is ready for the internal deployment workflow.",
    ))
    await _store_knowledge_graph(
        db,
        project=project,
        user_id=current_user.id,
        analysis=await _latest_project_analysis(db, project.id),
        plan=plan,
    )
    # Approval records the current preflight for review but never treats it as
    # an execution command. The deployment endpoint evaluates it again.
    await _run_digital_twin(db, project=project, user_id=current_user.id, plan=plan)
    await db.commit()
    await db.refresh(plan)
    return _serialize_infrastructure_plan(plan)


@app.get(
    "/api/projects/{project_id}/knowledge-graph",
    response_model=schemas.KnowledgeGraphResponse,
)
async def get_knowledge_graph(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the latest redacted evidence graph for the selected plan revision."""
    project = await _owned_project_or_404(project_id, current_user, db)
    plan_result = await db.execute(
        select(models.InfrastructurePlan).filter(
            models.InfrastructurePlan.project_id == project.id,
            models.InfrastructurePlan.user_id == current_user.id,
        )
    )
    plan = plan_result.scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Generate an infrastructure plan before viewing its evidence graph.")

    snapshot_result = await db.execute(
        select(models.KnowledgeGraphSnapshot)
        .filter(
            models.KnowledgeGraphSnapshot.project_id == project.id,
            models.KnowledgeGraphSnapshot.user_id == current_user.id,
            models.KnowledgeGraphSnapshot.plan_revision == plan.revision,
        )
        .order_by(desc(models.KnowledgeGraphSnapshot.created_at))
        .limit(1)
    )
    snapshot = snapshot_result.scalars().first()
    if not snapshot:
        snapshot = await _store_knowledge_graph(
            db,
            project=project,
            user_id=current_user.id,
            analysis=await _latest_project_analysis(db, project.id),
            plan=plan,
        )
        await db.commit()
        await db.refresh(snapshot)

    return schemas.KnowledgeGraphResponse(
        project_id=project.id,
        plan_revision=snapshot.plan_revision,
        graph=snapshot.graph_data or {},
        generated_at=format_dt(snapshot.created_at),
    )


@app.post(
    "/api/projects/{project_id}/digital-twin/simulate",
    response_model=schemas.DigitalTwinSimulationResponse,
)
async def simulate_project_digital_twin(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run a non-mutating preflight. It does not create or change Azure resources."""
    project = await _owned_project_or_404(project_id, current_user, db)
    plan_result = await db.execute(
        select(models.InfrastructurePlan).filter(
            models.InfrastructurePlan.project_id == project.id,
            models.InfrastructurePlan.user_id == current_user.id,
        )
    )
    plan = plan_result.scalars().first()
    if not plan:
        raise HTTPException(status_code=409, detail="Generate an infrastructure plan before running a preflight.")

    simulation = await _run_digital_twin(db, project=project, user_id=current_user.id, plan=plan)
    db.add(models.ActivityEvent(
        user_id=current_user.id,
        project_id=project.id,
        action="Digital twin preflight completed",
        details=f"Preflight status: {simulation.status}; deterministic risk score: {simulation.risk_score}/100.",
    ))
    await db.commit()
    await db.refresh(simulation)
    return _serialize_digital_twin(simulation)


@app.get(
    "/api/projects/{project_id}/digital-twin/latest",
    response_model=schemas.DigitalTwinSimulationResponse,
)
async def get_latest_digital_twin(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _owned_project_or_404(project_id, current_user, db)
    plan_result = await db.execute(
        select(models.InfrastructurePlan).filter(
            models.InfrastructurePlan.project_id == project.id,
            models.InfrastructurePlan.user_id == current_user.id,
        )
    )
    plan = plan_result.scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="No infrastructure plan exists for this project yet.")
    result = await db.execute(
        select(models.DigitalTwinSimulation)
        .filter(
            models.DigitalTwinSimulation.project_id == project_id,
            models.DigitalTwinSimulation.user_id == current_user.id,
            models.DigitalTwinSimulation.plan_revision == plan.revision,
        )
        .order_by(desc(models.DigitalTwinSimulation.created_at))
        .limit(1)
    )
    simulation = result.scalars().first()
    if not simulation:
        raise HTTPException(status_code=404, detail="No digital-twin preflight has been recorded for this project yet.")
    return _serialize_digital_twin(simulation)


@app.get(
    "/api/projects/{project_id}/decision-accuracy",
    response_model=schemas.DecisionAccuracyResponse,
)
async def get_decision_accuracy(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_project_or_404(project_id, current_user, db)
    result = await db.execute(
        select(models.DecisionEvaluation)
        .filter(
            models.DecisionEvaluation.project_id == project_id,
            models.DecisionEvaluation.user_id == current_user.id,
        )
        .order_by(desc(models.DecisionEvaluation.created_at))
    )
    return schemas.DecisionAccuracyResponse(**decision_intelligence.decision_accuracy_summary(result.scalars().all()))


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
                project_metadata["analysis_warning_count"] = len(analysis.vulnerabilities or [])

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
                            "impact": fa.impact
                        }

            # 5. Fetch recent telemetry metrics
            metrics_result = await db.execute(
                select(models.DeploymentMetric)
                .filter(models.DeploymentMetric.deployment_id.in_(
                    select(models.Deployment.id).filter(models.Deployment.project_id == req.project_id)
                ))
                .order_by(desc(models.DeploymentMetric.timestamp))
                .limit(5)
            )
            metrics = metrics_result.scalars().all()

            if metrics:
                avg_cpu = sum(m.cpu_utilization for m in metrics) / len(metrics)
                avg_mem = sum(m.memory_utilization for m in metrics) / len(metrics)
                project_metadata["telemetry"] = {
                    "avg_cpu_utilization": f"{round(avg_cpu, 1)}%",
                    "avg_memory_utilization": f"{round(avg_mem, 1)}%",
                    "recent_error_rate": f"{round(metrics[0].error_rate, 2)}%",
                    "recent_response_time_ms": f"{metrics[0].response_time_ms}ms"
                }

    plan_payload = None
    plan_updated = False
    plan_update_summary = None
    if req.project_id:
        plan_result = await db.execute(
            select(models.InfrastructurePlan).filter(
                models.InfrastructurePlan.project_id == req.project_id,
                models.InfrastructurePlan.user_id == current_user.id,
            )
        )
        architecture_plan = plan_result.scalars().first()
        if architecture_plan:
            current_plan = architecture_plan.plan_data or {}
            project_metadata["architecture_plan"] = {
                "cloud": current_plan.get("cloud"),
                "region": current_plan.get("region_label"),
                "components": current_plan.get("components", []),
            }
            updated_plan, plan_update_summary = planner.apply_chat_instruction(current_plan, req.message)
            if plan_update_summary:
                architecture_plan.plan_data = updated_plan
                architecture_plan.status = "draft"
                architecture_plan.revision += 1
                architecture_plan.approval_note = None
                architecture_plan.approved_at = None
                db.add(models.ActivityEvent(
                    user_id=current_user.id,
                    project_id=req.project_id,
                    action="Infrastructure plan updated by AI chat",
                    details=plan_update_summary,
                ))
                await db.commit()
                await db.refresh(architecture_plan)
                plan_updated = True
            plan_payload = _serialize_infrastructure_plan(architecture_plan).model_dump(mode="json")

    reply = ai.generate_chat_response(req.message, project_metadata)
    if plan_update_summary:
        reply = f"{reply}\n\nArchitecture plan updated: {plan_update_summary} Review and approve the revised plan before deployment."
    return {
        "reply": reply,
        "plan_updated": plan_updated,
        "infrastructure_plan": plan_payload,
    }





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
    """Retrieve a failure analysis already produced by the durable worker."""
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
        raise HTTPException(
            status_code=404,
            detail=(
                "No durable failure analysis is recorded for this deployment. "
                "A read request does not start an AI workload."
            ),
        )

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
        settings.predictive_scaling = False
        settings.auto_rollback = False
        settings.ai_threat_mitigation = False
        settings.auto_oom_restart = False
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
        message="Your ZeroOps workspace is ready. Connect a repository or upload a ZIP to get started.",
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
    # In production the Next.js frontend proxies /api/* to the backend, so
    # route the callback through the frontend domain so JWT cookies land on
    # the same origin the browser uses for all subsequent API calls.
    github_redirect_uri = (
        f"{config.FRONTEND_URL.rstrip('/')}/api/auth/github/callback"
        if config.IS_PRODUCTION and config.FRONTEND_URL
        else ""
    )
    authorization_url = github_oauth.get_authorization_url(state, github_redirect_uri)

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

    # The immutable provider subject is the account-linking key. Never create
    # or link a user from a partial provider profile with an empty subject.
    if not github_id:
        logger.warning("GitHub OAuth user profile did not contain an account id.")
        return get_redirect_and_clean_state(
            f"{frontend_url}/login?oauth_error=github_user_fetch_failed&provider=github"
        )

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
            user.email_verified = True
            if not user.avatar_url:
                user.avatar_url = github_avatar
            await tenancy.ensure_personal_tenant(db, user)
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
                email_verified=True,
            )
            db.add(user)
            await db.flush()
            await tenancy.ensure_personal_tenant(db, user)

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

    if user.mfa_enabled and (user.mfa_secret_encrypted or user.mfa_method == "email"):
        redirect_response = get_redirect_and_clean_state(
            f"{frontend_url}/login?mfa=required&provider=github"
            f"&mfa_method={oauth_mfa_method(user)}"
        )
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
    # In production the Next.js frontend proxies /api/* to the backend, so
    # the callback must be registered on the frontend domain so that the JWT
    # session cookies are set on the same origin the browser uses for all
    # subsequent API calls.
    if config.IS_PRODUCTION and config.FRONTEND_URL:
        redirect_uri = f"{config.FRONTEND_URL.rstrip('/')}/api/auth/google/callback"
    else:
        redirect_uri = str(request.url_for("google_oauth_callback"))
        if request.headers.get("x-forwarded-proto") == "https":
            redirect_uri = redirect_uri.replace("http://", "https://")
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

    if config.IS_PRODUCTION and config.FRONTEND_URL:
        redirect_uri = f"{config.FRONTEND_URL.rstrip('/')}/api/auth/google/callback"
    else:
        redirect_uri = str(request.url_for("google_oauth_callback"))
        if request.headers.get("x-forwarded-proto") == "https":
            redirect_uri = redirect_uri.replace("http://", "https://")
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
            user.email_verified = True
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
                email_verified=True,
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

        await tenancy.ensure_personal_tenant(db, user)
        user.last_primary_auth_at = datetime.utcnow()
        db.add(user)
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.exception("Google OAuth database error")
        return redirect_to_frontend("oauth_error=server_error")

    if user.mfa_enabled and (user.mfa_secret_encrypted or user.mfa_method == "email"):
        redirect_response = redirect_to_frontend(
            f"mfa=required&mfa_method={oauth_mfa_method(user)}"
        )
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


# Legacy endpoint kept for backward-compatible clients.
@app.get("/api/github/repo-metadata")
async def get_repo_metadata(
    repo: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """Fetch repository branches with user OAuth or public, unauthenticated Git access."""
    if current_user.github_connected and current_user.github_access_token_encrypted:
        try:
            token = github_oauth.decrypt_token(current_user.github_access_token_encrypted)
            parts = repo.split("/", 1)
            if len(parts) == 2:
                branches = await github_oauth.get_repo_branches(token, parts[0], parts[1])
                return {"branches": branches}
        except Exception:
            pass
    # Public repositories can be inspected without a credential. Never fall
    # back to a service-wide PAT for a user-supplied repository name.
    branches = git.get_branches(repo, None)
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
    cpu_samples = [metric.cpu_utilization for metric in metrics if metric.cpu_utilization is not None]
    memory_samples = [metric.memory_utilization for metric in metrics if metric.memory_utilization is not None]
    request_samples = [metric.request_count for metric in metrics if metric.request_count is not None]
    error_samples = [metric.error_rate for metric in metrics if metric.error_rate is not None]
    if not any((cpu_samples, memory_samples, request_samples, error_samples)):
        return {"available": False, "message": "Stored samples do not contain the requested runtime measurements."}
    return {
        "available": True,
        "cpu": round(sum(cpu_samples) / len(cpu_samples), 1) if cpu_samples else None,
        "memory": round(sum(memory_samples) / len(memory_samples), 1) if memory_samples else None,
        "traffic": sum(request_samples) if request_samples else None,
        "errorRate": round(sum(error_samples) / len(error_samples), 2) if error_samples else None,
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
    raise HTTPException(
        status_code=501,
        detail=(
            "The legacy secrets API is not available. Manage runtime values through "
            "the project environment-variable workflow."
        ),
    )


@app.get("/api/secrets/{project_id}")
async def list_secrets(project_id: str, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    proj_result = await db.execute(
        select(models.Project).filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    if not proj_result.scalars().first():
        raise HTTPException(status_code=404, detail="Project not found")
    raise HTTPException(
        status_code=501,
        detail=(
            "The legacy secrets API is not available. Manage runtime values through "
            "the project environment-variable workflow."
        ),
    )


@app.delete("/api/secrets/{project_id}/{key}")
async def delete_secret(project_id: str, key: str, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    proj_result = await db.execute(
        select(models.Project).filter(models.Project.id == project_id, models.Project.user_id == current_user.id)
    )
    if not proj_result.scalars().first():
        raise HTTPException(status_code=404, detail="Project not found")
    raise HTTPException(
        status_code=501,
        detail=(
            "The legacy secrets API is not available. Manage runtime values through "
            "the project environment-variable workflow."
        ),
    )


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
    
    # These are saved repository-analysis warnings, not a live vulnerability or
    # threat feed. Preserve the recorded count without inferring a threat level.
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

    return {
        "securityScore": None,
        "firewallStatus": "Unavailable",
        "httpsStatus": "Not assessed",
        "secretsManaged": secrets_count,
        "vulnerabilities": vuln_count,
        "soc2Status": "Not assessed",
        "threatLevel": "Unavailable",
        "namespaceIsolated": False,
        "rbacEnabled": False
    }


# ──────────────────────────────────────────────
# API KEY CAPABILITY BOUNDARY
# ──────────────────────────────────────────────

@app.get("/api/settings/api-key")
async def get_api_key(db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    raise HTTPException(
        status_code=501,
        detail=(
            "API keys are not available because API-key authentication is not "
            "implemented. No credential was generated."
        ),
    )

@app.post("/api/settings/api-key/regenerate")
async def regenerate_api_key(db: AsyncSession = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    raise HTTPException(
        status_code=501,
        detail=(
            "API keys are not available because API-key authentication is not "
            "implemented. No credential was generated."
        ),
    )


# ──────────────────────────────────────────────
# COLLABORATION, DOMAINS, HEALTH & COST OPTIMIZATION APIs
# ──────────────────────────────────────────────

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

    raise HTTPException(
        status_code=501,
        detail=(
            "Composite health scoring is not implemented. Use recorded deployment "
            "status, logs, and telemetry directly instead of an inferred score."
        ),
    )

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
    raise HTTPException(
        status_code=501,
        detail=(
            "Custom-domain provisioning is not implemented. ZeroOps AI does not "
            "claim DNS verification or certificate state without a provider integration."
        ),
    )

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
    raise HTTPException(
        status_code=501,
        detail=(
            "Custom-domain provisioning is not implemented. Configure domains through "
            "Azure App Service until a verified provider workflow is available."
        ),
    )

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
    raise HTTPException(
        status_code=501,
        detail=(
            "DNS and certificate verification are not implemented. No DNS lookup "
            "or certificate issuance was performed."
        ),
    )

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
    raise HTTPException(
        status_code=501,
        detail=(
            "Certificate renewal is not implemented. Manage the certificate through "
            "Azure App Service until a verified provider workflow is available."
        ),
    )

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
    raise HTTPException(
        status_code=501,
        detail=(
            "Custom-domain management is not implemented. Remove the binding through "
            "Azure App Service until a verified provider workflow is available."
        ),
    )

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
    raise HTTPException(
        status_code=501,
        detail=(
            "Project membership and role assignment are not implemented. Access remains "
            "limited to the project owner."
        ),
    )

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
    raise HTTPException(
        status_code=501,
        detail=(
            "Project invitations are not implemented. No invitation was sent and no "
            "access was granted."
        ),
    )

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
    raise HTTPException(
        status_code=501,
        detail=(
            "Project membership changes are not implemented. No access state was changed."
        ),
    )

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


async def require_worker_event_token(
    worker_token: Optional[str] = Header(default=None, alias="X-ZeroOps-Worker-Token"),
) -> None:
    """Reject callback requests before any database work is performed."""
    if not worker_token or not hmac.compare_digest(worker_token, config.WORKER_EVENT_TOKEN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid worker credentials.")


@app.post("/api/deployments/{deploy_id}/events")
async def receive_worker_event(
    deploy_id: uuid.UUID,
    event: schemas.WorkerDeploymentEvent,
    _: None = Depends(require_worker_event_token),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm.attributes import flag_modified

    event_data = event.model_dump(exclude_none=True)

    # Broadcast to active WebSockets
    await pipeline.broadcast_message(str(deploy_id), event_data)
    
    # Process event type
    evt_type = event.type
    if evt_type == "log":
        msg = event.text
        lvl = event.lineType.upper()
        line_num = event.line_number
        db_log = models.DeploymentLog(
            deployment_id=deploy_id,
            line_number=line_num,
            level=lvl,
            message=msg,
            timestamp=datetime.utcnow()
        )
        db.add(db_log)
        await db.commit()
    elif evt_type == "stage":
        res = await db.execute(
            select(models.Deployment).filter(models.Deployment.id == deploy_id)
        )
        dep = res.scalars().first()
        if dep:
            meta = dep.infrastructure_metadata or {}
            stages = meta.setdefault("stages", [])
            stage_found = False
            for stage in stages:
                if stage.get("id") == event.id:
                    stage["status"] = event.status or "pending"
                    stage["duration"] = event.duration
                    stage_found = True
                    break
            if not stage_found:
                stages.append({
                    "id": event.id,
                    "label": event.label,
                    "status": event.status or "pending",
                    "duration": event.duration,
                })
            flag_modified(dep, "infrastructure_metadata")
            await db.commit()
    elif evt_type == "status":
        res = await db.execute(
            select(models.Deployment).filter(models.Deployment.id == deploy_id)
        )
        dep = res.scalars().first()
        if dep:
            status_val = event.status
            dep.status = status_val
            if status_val in ("running", "failed", "stopped", "rolled_back"):
                dep.completed_at = datetime.utcnow()
                if status_val == "failed":
                    dep.failure_reason = event.failure_reason or "Worker build failure"
            await db.commit()
    return {"status": "ok"}


# ──────────────────────────────────────────────
# WEBSOCKET CHANNELS
# ──────────────────────────────────────────────

def websocket_origin_is_allowed(websocket: WebSocket) -> bool:
    """Apply browser-origin checks that HTTP CORS middleware cannot provide."""
    origin = (websocket.headers.get("origin") or "").strip().rstrip("/")
    if not origin:
        return not config.IS_PRODUCTION
    allowed_origins = {
        candidate.strip().rstrip("/")
        for candidate in config.CORS_ORIGINS
        if candidate and candidate.strip()
    }
    return origin in allowed_origins


@app.websocket("/ws/deployments/{deploy_id}")
async def deploy_websocket(websocket: WebSocket, deploy_id: str):
    """Stream deployment events only to the deployment owner.

    WebSockets do not run the normal HTTP dependency chain, so ownership must
    be checked explicitly before accepting the connection.
    """
    if not websocket_origin_is_allowed(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    access_token = websocket.cookies.get(auth.ACCESS_COOKIE)
    if not access_token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        payload = jwt.decode(access_token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        user_id = uuid.UUID(payload["sub"])
        if payload.get("type") != "access":
            raise ValueError("Invalid token type")
        deployment_id = uuid.UUID(deploy_id)
    except (JWTError, KeyError, ValueError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(models.Deployment.id).filter(
                    models.Deployment.id == deployment_id,
                    models.Deployment.user_id == user_id,
                )
            )
            if result.scalars().first() is None:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
    except Exception:
        logger.exception("Unable to authorize deployment WebSocket connection.")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    await websocket.accept()

    async def receive_until_disconnect() -> None:
        while True:
            await websocket.receive_text()

    polling_task = asyncio.create_task(
        pipeline.stream_deployment_updates(deploy_id, websocket)
    )
    receive_task = asyncio.create_task(receive_until_disconnect())
    try:
        done, _ = await asyncio.wait(
            {polling_task, receive_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for completed_task in done:
            completed_task.result()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Deployment WebSocket stream failed for %s.", deploy_id)
    finally:
        polling_task.cancel()
        receive_task.cancel()
        await asyncio.gather(polling_task, receive_task, return_exceptions=True)


# ──────────────────────────────────────────────
# AI CLOUD ARCHITECT EVOLVED ROUTERS
# ──────────────────────────────────────────────

try:
    from backend.services import analysis as zeroops_analysis
except ImportError:
    from services import analysis as zeroops_analysis

@app.post("/api/projects/{project_id}/analyze")
async def analyze_project_repository(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    project = await _owned_project_or_404(project_id, current_user, db)
    repo_path = project.source_path or project.full_name
    
    clone_token = None
    if current_user.github_access_token_encrypted:
        try:
            clone_token = github_oauth.decrypt_token(current_user.github_access_token_encrypted)
        except Exception:
            pass

    temp_dir = None
    if project.source_type != "upload" and not project.source_path:
        try:
            temp_dir = git.clone_repo(
                project.full_name,
                clone_token,
                branch=project.branch or "main",
                workspace_key=f"analysis-{uuid.uuid4()}",
            )
            repo_path = temp_dir
        except Exception as e:
            logger.warning("Failed to clone selected repository branch for analysis: %s", e)
            raise HTTPException(
                status_code=502,
                detail="The selected repository branch could not be fetched for analysis.",
            ) from e

    try:
        raw_analysis = zeroops_analysis.analyze_repository(repo_path, str(project_id))
    finally:
        if temp_dir:
            try:
                git.cleanup_workspace(temp_dir)
            except Exception as cleanup_error:
                logger.warning("Failed to clean analysis workspace %s: %s", temp_dir, cleanup_error)

    resources = raw_analysis.get("resources") or {}
    db_analysis = models.AIAnalysis(
        user_id=current_user.id,
        project_id=project.id,
        framework=raw_analysis.get("framework"),
        framework_version=raw_analysis.get("version"),
        language=raw_analysis.get("language"),
        risk_score=raw_analysis.get("risk_score", 0),
        confidence=raw_analysis.get("confidence", 0),
        cpu_recommendation=resources.get("cpu"),
        memory_recommendation=resources.get("memory"),
        storage_recommendation=resources.get("storage"),
        port=raw_analysis.get("port"),
        dependencies=raw_analysis.get("dependencies", []),
        vulnerabilities=raw_analysis.get("vulnerabilities", []),
        dockerfile=raw_analysis.get("dockerfile"),
        kubernetes_manifest=raw_analysis.get("kubernetes_manifest"),
        runtime=raw_analysis.get("runtime"),
        package_manager=raw_analysis.get("package_manager"),
        docker_support=raw_analysis.get("docker_support", False),
        monorepo_structure=raw_analysis.get("monorepo_structure"),
        database_dependencies=raw_analysis.get("database_dependencies", []),
        deployment_strategy=raw_analysis.get("deployment_strategy"),
        build_commands=raw_analysis.get("build_commands"),
        start_commands=raw_analysis.get("start_commands"),
        environment_variables=raw_analysis.get("environment_variables", []),
        explanation=raw_analysis.get("explanation"),
        recommended_compute_tier=raw_analysis.get("recommended_compute_tier"),
        estimated_cost=raw_analysis.get("estimated_cost"),
        recommended_region=raw_analysis.get("recommended_region"),
        expected_traffic=raw_analysis.get("expected_traffic"),
        pricing_breakdown=raw_analysis.get("pricing_breakdown")
    )
    db.add(db_analysis)
    db.add(models.ActivityEvent(
        user_id=current_user.id,
        project_id=project_id,
        action="Repository scanned",
        details=f"Codebase scanner detected {db_analysis.framework} framework and database dependencies."
    ))
    await db.commit()
    await db.refresh(db_analysis)
    return raw_analysis


@app.get("/api/projects/{project_id}/analysis")
async def get_project_analysis(
    project_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    project = await _owned_project_or_404(project_id, current_user, db)
    analysis = await _latest_project_analysis(db, project_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis found. Run analyze endpoint first.")
    
    return {
        "framework": analysis.framework,
        "version": analysis.framework_version,
        "language": analysis.language,
        "runtime": analysis.runtime,
        "package_manager": analysis.package_manager,
        "docker_support": analysis.docker_support,
        "database_dependencies": analysis.database_dependencies,
        "environment_variables": analysis.environment_variables,
        "vulnerabilities": analysis.vulnerabilities,
        "explanation": analysis.explanation,
        "risk_score": analysis.risk_score,
        "confidence": analysis.confidence
    }


@app.post("/api/projects/{project_id}/infrastructure-spec/explain/{component_id}")
async def explain_component_decision(
    project_id: uuid.UUID,
    component_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    project = await _owned_project_or_404(project_id, current_user, db)
    plan_result = await db.execute(
        select(models.InfrastructurePlan).filter(
            models.InfrastructurePlan.project_id == project_id,
            models.InfrastructurePlan.user_id == current_user.id
        )
    )
    plan = plan_result.scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Infrastructure plan not found.")
        
    explanation = ai.explain_infrastructure_decision(component_id, plan.plan_data or {})
    return {"explanation": explanation}


@app.post("/api/projects/{project_id}/deploy")
async def start_queue_deploy(
    project_id: uuid.UUID,
    req: schemas.DeploymentCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await start_deploy(req, current_user, db)


@app.get("/api/deployment-jobs/{job_id}/status")
async def get_deployment_job_status(
    job_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(models.DeploymentJob)
        .filter(models.DeploymentJob.id == job_id, models.DeploymentJob.user_id == current_user.id)
    )
    job = result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Deployment job not found.")
        
    return {
        "id": str(job.id),
        "status": job.status,
        "terraform_status": job.terraform_status,
        "deployment_status": job.deployment_status,
        "live_url": job.live_url,
        "failure_reason": job.failure_reason,
        "created_at": format_dt(job.created_at),
        "updated_at": format_dt(job.updated_at)
    }


@app.post("/api/ai/architect-chat", response_model=schemas.ArchitectChatResponse)
async def post_architect_chat(
    req: schemas.ChatRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not req.project_id:
        raise HTTPException(status_code=400, detail="project_id is required for architect chat.")
        
    project = await _owned_project_or_404(req.project_id, current_user, db)
    plan_result = await db.execute(
        select(models.InfrastructurePlan).filter(
            models.InfrastructurePlan.project_id == req.project_id,
            models.InfrastructurePlan.user_id == current_user.id
        )
    )
    plan = plan_result.scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Generate infrastructure plan first.")

    updated_plan_data, reply = ai.architect_chat(req.message, plan.plan_data or {})
    
    plan_updated = False
    if updated_plan_data != plan.plan_data:
        plan.plan_data = updated_plan_data
        plan.cost_estimate = updated_plan_data.get("cost")
        plan.security_score = updated_plan_data.get("assessment", {}).get("security", {}).get("value")
        plan.performance_score = updated_plan_data.get("assessment", {}).get("performance", {}).get("value")
        plan.reliability_score = updated_plan_data.get("assessment", {}).get("reliability", {}).get("value")
        plan.estimated_deploy_time = updated_plan_data.get("deployment_time", {}).get("estimate")
        plan.ai_explanations = updated_plan_data.get("ai_explanations")
        plan.status = "draft"
        plan.revision += 1
        
        db.add(models.ActivityEvent(
            user_id=current_user.id,
            project_id=req.project_id,
            action="Infrastructure spec updated by Architect chat",
            details=reply
        ))
        await db.commit()
        await db.refresh(plan)
        plan_updated = True
        
    return schemas.ArchitectChatResponse(
        reply=reply,
        plan_updated=plan_updated,
        plan=_serialize_infrastructure_plan(plan)
    )


