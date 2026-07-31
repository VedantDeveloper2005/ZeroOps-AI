"""Tenant resolution helpers for the current personal-workspace UX."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

try:
    from backend import models
except ImportError:
    import models


def _personal_workspace_name(user: models.User) -> str:
    full_name = " ".join(part.strip() for part in [user.first_name or "", user.last_name or ""] if part.strip())
    return f"{full_name}'s workspace" if full_name else "Personal workspace"


async def ensure_personal_tenant(db: AsyncSession, user: models.User) -> models.Tenant:
    """Return the user's hidden personal tenant, creating it when necessary.

    The personal tenant UUID intentionally equals the user UUID. This gives
    existing single-user records a deterministic, idempotent backfill target.
    """

    tenant = await db.get(models.Tenant, user.id)
    if tenant is None:
        tenant = models.Tenant(
            id=user.id,
            display_name=_personal_workspace_name(user),
            kind="personal",
            status="active",
        )
        db.add(tenant)
        await db.flush()
    elif tenant.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your personal workspace is not active.",
        )

    membership_result = await db.execute(
        select(models.TenantMembership).where(
            and_(
                models.TenantMembership.tenant_id == tenant.id,
                models.TenantMembership.user_id == user.id,
            )
        )
    )
    membership = membership_result.scalars().first()
    if membership is None:
        membership = models.TenantMembership(
            id=uuid.uuid5(user.id, "zeroops-personal-membership"),
            tenant_id=tenant.id,
            user_id=user.id,
            role="owner",
            status="active",
        )
        db.add(membership)
        await db.flush()
    elif membership.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your personal workspace is not active.",
        )
    return tenant


async def require_tenant_membership(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> models.TenantMembership:
    result = await db.execute(
        select(models.TenantMembership)
        .join(models.Tenant, models.Tenant.id == models.TenantMembership.tenant_id)
        .where(
            and_(
                models.TenantMembership.tenant_id == tenant_id,
                models.TenantMembership.user_id == user_id,
                models.TenantMembership.status == "active",
                models.Tenant.status == "active",
            )
        )
    )
    membership = result.scalars().first()
    if membership is None:
        # A 404 avoids confirming another tenant's existence.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    return membership


async def resolve_tenant(
    db: AsyncSession,
    *,
    user: models.User,
    requested_tenant_id: Optional[uuid.UUID] = None,
) -> models.Tenant:
    if requested_tenant_id is None:
        return await ensure_personal_tenant(db, user)

    await require_tenant_membership(db, user_id=user.id, tenant_id=requested_tenant_id)
    tenant = await db.get(models.Tenant, requested_tenant_id)
    if tenant is None or tenant.status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    return tenant
