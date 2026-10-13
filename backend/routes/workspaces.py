"""Company workspace, member, and invitation APIs."""

from __future__ import annotations

import hashlib
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

try:
    from backend import auth, config, models, schemas
    from backend.database import get_db
    from backend.services import email_service, tenancy
except ImportError:
    import auth, config, models, schemas
    from database import get_db
    from services import email_service, tenancy


router = APIRouter(prefix="/api/workspaces", tags=["company workspaces"])
INVITATION_TTL_HOURS = 72
MANAGER_ROLES = {"owner", "admin"}


def _require_verified(user: models.User) -> None:
    if not user.email_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verify your email address before managing a company workspace.")


def _require_mfa(user: models.User) -> None:
    if not user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company workspaces require MFA. Enable an authenticator or email code in Profile and security first.",
        )


async def _workspace_and_membership(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user: models.User,
) -> tuple[models.Tenant, models.TenantMembership]:
    _require_verified(user)
    tenant = await db.get(models.Tenant, workspace_id)
    if tenant is None or tenant.status != "active":
        raise HTTPException(status_code=404, detail="Workspace not found.")
    membership = await tenancy.require_tenant_membership(db, user_id=user.id, tenant_id=tenant.id)
    if tenant.require_mfa:
        _require_mfa(user)
    return tenant, membership


def _audit(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor: models.User,
    action: str,
    details: str,
    event_data: dict[str, Any] | None = None,
) -> None:
    db.add(
        models.ActivityEvent(
            tenant_id=tenant_id,
            user_id=actor.id,
            actor_type="user",
            actor_id=str(actor.id),
            action=action,
            details=details,
            event_data=event_data or {},
        )
    )


@router.get("")
async def list_workspaces(
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Include the personal workspace in the selector even when a company
    # workspace is selected or requires MFA.
    personal = await tenancy.ensure_personal_tenant(db, current_user)
    result = await db.execute(
        select(models.Tenant, models.TenantMembership)
        .join(models.TenantMembership, models.TenantMembership.tenant_id == models.Tenant.id)
        .where(
            models.TenantMembership.user_id == current_user.id,
            models.TenantMembership.status == "active",
            models.Tenant.status == "active",
        )
        .order_by(models.Tenant.kind, models.Tenant.display_name)
    )
    await db.commit()
    rows = result.all()
    if not any(tenant.id == personal.id for tenant, _ in rows):
        return [{"id": str(personal.id), "name": personal.display_name, "kind": personal.kind, "role": "owner", "require_mfa": False}] + [
            {"id": str(tenant.id), "name": tenant.display_name, "kind": tenant.kind, "role": membership.role, "require_mfa": tenant.require_mfa}
            for tenant, membership in rows
        ]
    return [
        {"id": str(tenant.id), "name": tenant.display_name, "kind": tenant.kind, "role": membership.role, "require_mfa": tenant.require_mfa}
        for tenant, membership in rows
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    req: schemas.WorkspaceCreateRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_verified(current_user)
    _require_mfa(current_user)
    tenant = models.Tenant(
        id=uuid.uuid4(),
        display_name=req.name,
        kind="organization",
        status="active",
        require_mfa=True,
    )
    db.add(tenant)
    await db.flush()
    membership = models.TenantMembership(
        id=uuid.uuid4(), tenant_id=tenant.id, user_id=current_user.id, role="owner", status="active"
    )
    db.add(membership)
    _audit(db, tenant_id=tenant.id, actor=current_user, action="workspace_created", details="Company workspace created.")
    await db.commit()
    return {"id": str(tenant.id), "name": tenant.display_name, "kind": tenant.kind, "role": membership.role, "require_mfa": tenant.require_mfa}


@router.get("/{workspace_id}/members")
async def list_workspace_members(
    workspace_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant, _ = await _workspace_and_membership(db, workspace_id=workspace_id, user=current_user)
    result = await db.execute(
        select(models.TenantMembership, models.User)
        .join(models.User, models.User.id == models.TenantMembership.user_id)
        .where(models.TenantMembership.tenant_id == tenant.id, models.TenantMembership.status == "active")
        .order_by(models.TenantMembership.created_at)
    )
    return [
        {
            "user_id": str(membership.user_id),
            "email": member.email,
            "name": " ".join(part for part in [member.first_name, member.last_name] if part) or member.email,
            "role": membership.role,
            "created_at": membership.created_at.isoformat() if membership.created_at else None,
            "mfa_enabled": bool(member.mfa_enabled),
        }
        for membership, member in result.all()
    ]


@router.get("/{workspace_id}/invitations")
async def list_workspace_invitations(
    workspace_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant, membership = await _workspace_and_membership(db, workspace_id=workspace_id, user=current_user)
    if membership.role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Only workspace owners and admins can manage invitations.")
    result = await db.execute(
        select(models.WorkspaceInvitation)
        .where(models.WorkspaceInvitation.tenant_id == tenant.id, models.WorkspaceInvitation.status == "pending")
        .order_by(desc(models.WorkspaceInvitation.created_at))
    )
    invitations = result.scalars().all()
    now = datetime.utcnow()
    for invitation in invitations:
        if invitation.expires_at <= now:
            invitation.status = "expired"
    if invitations:
        await db.commit()
    return [
        {
            "id": str(invitation.id),
            "email": invitation.email,
            "role": invitation.role,
            "status": invitation.status,
            "expires_at": invitation.expires_at.isoformat(),
            "created_at": invitation.created_at.isoformat() if invitation.created_at else None,
        }
        for invitation in invitations
        if invitation.status == "pending"
    ]


@router.post("/{workspace_id}/invitations", status_code=status.HTTP_201_CREATED)
async def invite_workspace_member(
    workspace_id: uuid.UUID,
    req: schemas.WorkspaceInvitationCreateRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_verified(current_user)
    tenant, membership = await _workspace_and_membership(db, workspace_id=workspace_id, user=current_user)
    if membership.role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Only workspace owners and admins can invite engineers.")
    if tenant.kind != "organization":
        raise HTTPException(status_code=409, detail="Create a company workspace before inviting engineers.")
    if req.role == "admin" and membership.role != "owner":
        raise HTTPException(status_code=403, detail="Only a workspace owner can grant admin access.")
    if req.email.strip().lower() == current_user.email.strip().lower():
        raise HTTPException(status_code=409, detail="You already belong to this workspace.")

    # Serialize invitations within a workspace so duplicate submissions from
    # multiple admins cannot create multiple active links for one address.
    await db.execute(select(models.Tenant.id).where(models.Tenant.id == tenant.id).with_for_update())

    email = req.email.strip().lower()
    existing_user_result = await db.execute(select(models.User).where(func.lower(models.User.email) == email))
    existing_user = existing_user_result.scalars().first()
    if existing_user:
        existing_membership_result = await db.execute(
            select(models.TenantMembership).where(
                models.TenantMembership.tenant_id == tenant.id,
                models.TenantMembership.user_id == existing_user.id,
                models.TenantMembership.status == "active",
            )
        )
        if existing_membership_result.scalars().first():
            raise HTTPException(status_code=409, detail="This person is already a workspace member.")

    pending_result = await db.execute(
        select(models.WorkspaceInvitation).where(
            models.WorkspaceInvitation.tenant_id == tenant.id,
            models.WorkspaceInvitation.email == email,
            models.WorkspaceInvitation.status == "pending",
        )
    )
    for previous in pending_result.scalars().all():
        previous.status = "revoked"

    raw_token = auth.create_verification_token()
    invitation = models.WorkspaceInvitation(
        id=uuid.uuid4(), tenant_id=tenant.id, email=email, role=req.role,
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        status="pending", invited_by_user_id=current_user.id,
        expires_at=datetime.utcnow() + timedelta(hours=INVITATION_TTL_HOURS),
    )
    db.add(invitation)
    inviter_name = " ".join(part for part in [current_user.first_name, current_user.last_name] if part) or current_user.email
    invitation_url = f"{config.FRONTEND_URL.rstrip('/')}/join-workspace?token={raw_token}"
    delivered = await asyncio.to_thread(
        email_service.send_workspace_invitation_email,
        email,
        workspace_name=tenant.display_name,
        inviter_name=inviter_name,
        role=req.role,
        invitation_url=invitation_url,
        expires_in_hours=INVITATION_TTL_HOURS,
    )
    if not delivered:
        await db.rollback()
        raise HTTPException(status_code=503, detail="The invitation email could not be delivered. Check email settings and try again.")
    _audit(db, tenant_id=tenant.id, actor=current_user, action="workspace_member_invited", details="A workspace invitation was sent.", event_data={"email": email, "role": req.role})
    await db.commit()
    return {"id": str(invitation.id), "email": invitation.email, "role": invitation.role, "status": invitation.status, "expires_at": invitation.expires_at.isoformat()}


@router.delete("/{workspace_id}/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_workspace_invitation(
    workspace_id: uuid.UUID,
    invitation_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant, membership = await _workspace_and_membership(db, workspace_id=workspace_id, user=current_user)
    if membership.role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Only workspace owners and admins can revoke invitations.")
    result = await db.execute(
        select(models.WorkspaceInvitation).where(
            models.WorkspaceInvitation.id == invitation_id,
            models.WorkspaceInvitation.tenant_id == tenant.id,
            models.WorkspaceInvitation.status == "pending",
        )
    )
    invitation = result.scalars().first()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found.")
    invitation.status = "revoked"
    _audit(db, tenant_id=tenant.id, actor=current_user, action="workspace_invitation_revoked", details="A pending workspace invitation was revoked.", event_data={"email": invitation.email})
    await db.commit()


@router.post("/invitations/accept")
async def accept_workspace_invitation(
    req: schemas.WorkspaceInvitationAcceptRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_verified(current_user)
    token_hash = hashlib.sha256(req.token.encode("utf-8")).hexdigest()
    result = await db.execute(
        select(models.WorkspaceInvitation)
        .where(models.WorkspaceInvitation.token_hash == token_hash, models.WorkspaceInvitation.status == "pending")
        .with_for_update()
    )
    invitation = result.scalars().first()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation is invalid, expired, or already used.")
    if invitation.expires_at <= datetime.utcnow():
        invitation.status = "expired"
        await db.commit()
        raise HTTPException(status_code=410, detail="This workspace invitation has expired. Ask an owner to send a new one.")
    if invitation.email.lower() != current_user.email.lower():
        raise HTTPException(status_code=403, detail="Sign in with the email address that received this invitation.")

    membership_result = await db.execute(
        select(models.TenantMembership).where(
            models.TenantMembership.tenant_id == invitation.tenant_id,
            models.TenantMembership.user_id == current_user.id,
        )
    )
    existing_membership = membership_result.scalars().first()
    if existing_membership:
        if existing_membership.status == "active":
            raise HTTPException(status_code=409, detail="This person is already a workspace member.")
        existing_membership.status = "active"
        existing_membership.role = invitation.role
        existing_membership.updated_at = datetime.utcnow()
    else:
        db.add(models.TenantMembership(
            id=uuid.uuid4(), tenant_id=invitation.tenant_id, user_id=current_user.id,
            role=invitation.role, status="active",
        ))
    invitation.status = "accepted"
    invitation.accepted_by_user_id = current_user.id
    invitation.updated_at = datetime.utcnow()
    _audit(db, tenant_id=invitation.tenant_id, actor=current_user, action="workspace_invitation_accepted", details="A workspace invitation was accepted.")
    tenant_id = invitation.tenant_id
    await db.commit()
    tenant = await db.get(models.Tenant, tenant_id)
    return {"status": "accepted", "workspace_id": str(tenant_id), "workspace_name": tenant.display_name if tenant else "Company workspace", "role": invitation.role, "mfa_required": bool(tenant.require_mfa) if tenant else True}


@router.put("/{workspace_id}/members/{member_user_id}/role")
async def update_workspace_member_role(
    workspace_id: uuid.UUID,
    member_user_id: uuid.UUID,
    req: schemas.WorkspaceMemberRoleRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant, actor_membership = await _workspace_and_membership(db, workspace_id=workspace_id, user=current_user)
    if actor_membership.role != "owner":
        raise HTTPException(status_code=403, detail="Only a workspace owner can change member roles.")
    await db.execute(select(models.Tenant.id).where(models.Tenant.id == tenant.id).with_for_update())
    result = await db.execute(
        select(models.TenantMembership).where(
            models.TenantMembership.tenant_id == tenant.id,
            models.TenantMembership.user_id == member_user_id,
            models.TenantMembership.status == "active",
        ).with_for_update()
    )
    target = result.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="Workspace member not found.")
    if target.role == "owner" and req.role != "owner":
        owners_result = await db.execute(
            select(models.TenantMembership.id).where(
                models.TenantMembership.tenant_id == tenant.id,
                models.TenantMembership.role == "owner",
                models.TenantMembership.status == "active",
            )
        )
        if len(owners_result.scalars().all()) <= 1:
            raise HTTPException(status_code=409, detail="Transfer ownership before removing the final workspace owner.")
    target.role = req.role
    target.updated_at = datetime.utcnow()
    _audit(db, tenant_id=tenant.id, actor=current_user, action="workspace_member_role_changed", details="A workspace member role was changed.", event_data={"member_user_id": str(member_user_id), "role": req.role})
    await db.commit()
    return {"user_id": str(member_user_id), "role": target.role}


@router.delete("/{workspace_id}/members/{member_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_workspace_member(
    workspace_id: uuid.UUID,
    member_user_id: uuid.UUID,
    current_user: models.User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant, actor_membership = await _workspace_and_membership(db, workspace_id=workspace_id, user=current_user)
    if actor_membership.role not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Only workspace owners and admins can remove members.")
    await db.execute(select(models.Tenant.id).where(models.Tenant.id == tenant.id).with_for_update())
    result = await db.execute(
        select(models.TenantMembership).where(
            models.TenantMembership.tenant_id == tenant.id,
            models.TenantMembership.user_id == member_user_id,
            models.TenantMembership.status == "active",
        ).with_for_update()
    )
    target = result.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="Workspace member not found.")
    if actor_membership.role != "owner" and target.role in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Admins cannot remove owners or other admins.")
    if target.role == "owner":
        owners_result = await db.execute(
            select(models.TenantMembership.id).where(
                models.TenantMembership.tenant_id == tenant.id,
                models.TenantMembership.role == "owner",
                models.TenantMembership.status == "active",
            )
        )
        if len(owners_result.scalars().all()) <= 1:
            raise HTTPException(status_code=409, detail="Transfer ownership before removing the final workspace owner.")
    target.status = "removed"
    target.updated_at = datetime.utcnow()
    _audit(db, tenant_id=tenant.id, actor=current_user, action="workspace_member_removed", details="A member was removed from the workspace.", event_data={"member_user_id": str(member_user_id)})
    await db.commit()
