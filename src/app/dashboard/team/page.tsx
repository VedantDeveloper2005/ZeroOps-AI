"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Building2, Check, Clock3, Loader2, MailPlus, RefreshCw, ShieldCheck, UserMinus, Users } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatePanel } from "@/components/ui/StatePanel";
import { useAuth } from "@/lib/AuthContext";
import { useNotifications } from "@/lib/NotificationContext";
import { api, getErrorMessage, type WorkspaceInvitation, type WorkspaceMember, type WorkspaceSummary } from "@/lib/api";

const WORKSPACE_KEY = "zeroops:active-workspace";

function prettyRole(role: string) {
  return role.slice(0, 1).toUpperCase() + role.slice(1);
}

function formatExpiry(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Expiry unavailable" : `Expires ${date.toLocaleDateString()}`;
}

export default function TeamPage() {
  const { user } = useAuth();
  const { addToast } = useNotifications();
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [invitations, setInvitations] = useState<WorkspaceInvitation[]>([]);
  const [workspaceName, setWorkspaceName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("engineer");
  const [mfaEnabled, setMfaEnabled] = useState(Boolean(user?.mfa_enabled));
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const selectedWorkspace = useMemo(
    () => workspaces.find((workspace) => workspace.id === workspaceId) || null,
    [workspaces, workspaceId],
  );
  const isOrganization = selectedWorkspace?.kind === "organization";
  const canManage = selectedWorkspace?.role === "owner" || selectedWorkspace?.role === "admin";
  const isOwner = selectedWorkspace?.role === "owner";
  const hasMfa = mfaEnabled;

  useEffect(() => {
    if (!user?.id) return;
    void api.getMfaStatus().then((status) => setMfaEnabled(status.enabled)).catch(() => setMfaEnabled(Boolean(user.mfa_enabled)));
  }, [user?.id, user?.mfa_enabled]);

  const loadWorkspaceData = useCallback(async (id: string, includeInvitations: boolean) => {
    setLoading(true);
    setError(null);
    const results = await Promise.allSettled([
      api.listWorkspaceMembers(id),
      includeInvitations ? api.listWorkspaceInvitations(id) : Promise.resolve([] as WorkspaceInvitation[]),
    ] as const);
    if (results[0].status === "fulfilled") setMembers(results[0].value);
    else setError(getErrorMessage(results[0].reason, "Workspace members could not be loaded."));
    if (results[1].status === "fulfilled") setInvitations(results[1].value);
    else setError(getErrorMessage(results[1].reason, "Pending invitations could not be loaded."));
    setLoading(false);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([
      api.listWorkspaces(),
      api.getMfaStatus().then((status) => status.enabled).catch(() => Boolean(user?.mfa_enabled)),
    ]).then(([items, mfaEnabledForAccount]) => {
      if (cancelled) return;
      setWorkspaces(items);
      const saved = window.localStorage.getItem(WORKSPACE_KEY);
      const defaultWorkspace = items.find((item) => item.id === saved && (!item.require_mfa || mfaEnabledForAccount))
        || items.find((item) => item.id === user?.id)
        || items[0];
      if (defaultWorkspace) {
        setWorkspaceId(defaultWorkspace.id);
        if (saved && saved !== defaultWorkspace.id) {
          window.localStorage.setItem(WORKSPACE_KEY, defaultWorkspace.id);
          if (user?.id) window.localStorage.setItem("zeroops:active-workspace-owner", user.id);
        }
      }
    }).catch((loadError) => {
      if (!cancelled) {
        setError(getErrorMessage(loadError, "Your workspaces could not be loaded."));
        setLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, [user?.id]);

  useEffect(() => {
    if (!workspaceId || !selectedWorkspace) return;
    window.localStorage.setItem(WORKSPACE_KEY, workspaceId);
    if (user?.id) window.localStorage.setItem("zeroops:active-workspace-owner", user.id);
    if (!isOrganization) {
      setMembers([]);
      setInvitations([]);
      setLoading(false);
      setError(null);
      return;
    }
    if (selectedWorkspace.require_mfa && !hasMfa) {
      setMembers([]);
      setInvitations([]);
      setLoading(false);
      setError(null);
      return;
    }
    void loadWorkspaceData(workspaceId, canManage);
  }, [workspaceId, selectedWorkspace, isOrganization, hasMfa, canManage, loadWorkspaceData]);

  const refresh = async () => {
    if (workspaceId && isOrganization) await loadWorkspaceData(workspaceId, canManage);
  };

  const createWorkspace = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await api.createWorkspace(workspaceName.trim());
      setWorkspaceName("");
      const items = await api.listWorkspaces();
      setWorkspaces(items);
      setWorkspaceId(created.id);
      window.localStorage.setItem(WORKSPACE_KEY, created.id);
      if (user?.id) window.localStorage.setItem("zeroops:active-workspace-owner", user.id);
      addToast("Company workspace created. MFA is required for every member.", "success");
      window.location.reload();
    } catch (createError) {
      setError(getErrorMessage(createError, "The company workspace could not be created."));
    } finally {
      setBusy(false);
    }
  };

  const inviteMember = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedWorkspace) return;
    setBusy(true);
    setError(null);
    try {
      await api.inviteWorkspaceMember(selectedWorkspace.id, inviteEmail.trim(), inviteRole);
      setInviteEmail("");
      await refresh();
      addToast("Invitation email sent.", "success");
    } catch (inviteError) {
      setError(getErrorMessage(inviteError, "The invitation could not be sent."));
    } finally {
      setBusy(false);
    }
  };

  const revokeInvite = async (invitation: WorkspaceInvitation) => {
    if (!selectedWorkspace || !window.confirm(`Revoke the invitation for ${invitation.email}?`)) return;
    setBusy(true);
    setError(null);
    try {
      await api.revokeWorkspaceInvitation(selectedWorkspace.id, invitation.id);
      await refresh();
      addToast("Invitation revoked.", "success");
    } catch (revokeError) {
      setError(getErrorMessage(revokeError, "The invitation could not be revoked."));
    } finally {
      setBusy(false);
    }
  };

  const changeRole = async (member: WorkspaceMember, role: string) => {
    if (!selectedWorkspace || role === member.role) return;
    setBusy(true);
    setError(null);
    try {
      await api.updateWorkspaceMemberRole(selectedWorkspace.id, member.user_id, role);
      await refresh();
      addToast(`${member.name}'s role updated.`, "success");
    } catch (roleError) {
      setError(getErrorMessage(roleError, "The member role could not be updated."));
    } finally {
      setBusy(false);
    }
  };

  const removeMember = async (member: WorkspaceMember) => {
    if (!selectedWorkspace || !window.confirm(`Remove ${member.name} from this workspace? Their company access ends immediately.`)) return;
    setBusy(true);
    setError(null);
    try {
      await api.removeWorkspaceMember(selectedWorkspace.id, member.user_id);
      await refresh();
      addToast("Member removed from workspace.", "success");
    } catch (removeError) {
      setError(getErrorMessage(removeError, "The member could not be removed."));
    } finally {
      setBusy(false);
    }
  };

  const selectWorkspace = (id: string) => {
    window.localStorage.setItem(WORKSPACE_KEY, id);
    if (user?.id) window.localStorage.setItem("zeroops:active-workspace-owner", user.id);
    window.location.reload();
  };

  if (loading && workspaces.length === 0) {
    return <div className="mx-auto max-w-6xl"><PageHeader eyebrow="Company" title="Team and access" description="Manage company workspaces, engineers, and secure deployment access." /><div role="status" className="flex min-h-64 items-center justify-center rounded-xl border border-border bg-card"><Loader2 size={22} className="animate-spin text-primary" aria-hidden="true" /><span className="ml-3 text-sm text-foreground-muted">Loading workspaces…</span></div></div>;
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        eyebrow="Company"
        title="Team and access"
        description="Bring engineers into one company workspace. Members can share projects and deployment history, while every action stays tied to its engineer."
        actions={(
          <button type="button" onClick={() => void refresh()} disabled={busy || loading} className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-4 text-sm font-medium text-foreground transition-colors hover:bg-surface-raised disabled:opacity-60">
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} aria-hidden="true" /> Refresh
          </button>
        )}
      />

      {error && <div role="alert" className="rounded-xl border border-danger/30 bg-danger-subtle px-4 py-3 text-sm text-danger">{error}</div>}

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(300px,0.65fr)]">
        <div className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <span className="grid size-11 place-items-center rounded-xl bg-primary/10 text-primary"><Building2 size={20} aria-hidden="true" /></span>
              <div>
                <h2 className="text-base font-semibold text-foreground">Workspace</h2>
                <p className="mt-1 max-w-xl text-sm text-foreground-muted">Switch company context to see its shared projects, deployment runs, and team access.</p>
              </div>
            </div>
            <label className="sr-only" htmlFor="team-workspace">Select workspace</label>
            <select id="team-workspace" value={workspaceId} onChange={(event) => selectWorkspace(event.target.value)} className="min-h-11 min-w-56 rounded-lg border border-border bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              {workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}{workspace.kind === "organization" ? ` · ${prettyRole(workspace.role)}` : " · Personal"}</option>)}
            </select>
          </div>

          {selectedWorkspace?.require_mfa && !hasMfa ? (
            <div className="mt-5 flex flex-col gap-3 rounded-xl border border-warning/30 bg-warning-subtle p-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex gap-3"><ShieldCheck className="mt-0.5 shrink-0 text-warning" size={19} aria-hidden="true" /><div><p className="text-sm font-semibold text-foreground">Enroll MFA to access this company</p><p className="mt-1 text-sm text-foreground-muted">Company workspaces require each engineer to use an authenticator or email-code MFA.</p></div></div>
              <Link href="/dashboard/profile" className="inline-flex min-h-11 shrink-0 items-center justify-center rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground hover:bg-primary-hover">Set up MFA</Link>
            </div>
          ) : selectedWorkspace?.kind === "personal" ? (
            <div className="mt-5 rounded-xl border border-border bg-surface-subtle p-4">
              <p className="text-sm font-medium text-foreground">You are in your personal workspace.</p>
              <p className="mt-1 text-sm text-foreground-muted">Create a company workspace to invite engineers and collaborate on shared projects.</p>
            </div>
          ) : (
            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-border bg-surface-subtle p-4"><p className="text-2xl font-semibold text-foreground">{members.length}</p><p className="mt-1 text-xs text-foreground-muted">Active members</p></div>
              <div className="rounded-xl border border-border bg-surface-subtle p-4"><p className="text-2xl font-semibold text-foreground">{invitations.length}</p><p className="mt-1 text-xs text-foreground-muted">Pending invites</p></div>
              <div className="rounded-xl border border-border bg-surface-subtle p-4"><p className="inline-flex items-center gap-2 text-sm font-semibold text-success"><ShieldCheck size={16} aria-hidden="true" /> MFA required</p><p className="mt-1 text-xs text-foreground-muted">For every member</p></div>
            </div>
          )}

          {isOrganization && hasMfa && (
            <div className="mt-6 border-t border-border pt-5">
              <div className="mb-4 flex items-center justify-between gap-3"><h3 className="inline-flex items-center gap-2 text-sm font-semibold text-foreground"><Users size={17} aria-hidden="true" /> People</h3><span className="text-xs text-foreground-muted">{members.length} active</span></div>
              {loading ? <div role="status" className="py-8 text-center text-sm text-foreground-muted">Loading team…</div> : members.length === 0 ? <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-foreground-muted">No active team members yet.</div> : (
                <div className="overflow-x-auto rounded-xl border border-border">
                  <table className="w-full min-w-[620px] text-left text-sm">
                    <thead className="bg-surface-subtle text-xs uppercase tracking-wide text-foreground-subtle"><tr><th scope="col" className="px-4 py-3 font-semibold">Member</th><th scope="col" className="px-4 py-3 font-semibold">Role</th><th scope="col" className="px-4 py-3 font-semibold">MFA</th><th scope="col" className="px-4 py-3 text-right font-semibold">Access</th></tr></thead>
                    <tbody className="divide-y divide-border">
                      {members.map((member) => {
                        const isSelf = member.user_id === user?.id;
                        return <tr key={member.user_id}>
                          <td className="px-4 py-3"><p className="font-medium text-foreground">{member.name}{isSelf ? " (you)" : ""}</p><p className="mt-0.5 text-xs text-foreground-muted">{member.email}</p></td>
                          <td className="px-4 py-3">{isOwner && !isSelf ? <label className="sr-only" htmlFor={`role-${member.user_id}`}>Role for {member.name}</label> : null}{isOwner && !isSelf ? <select id={`role-${member.user_id}`} value={member.role} disabled={busy} onChange={(event) => void changeRole(member, event.target.value)} className="min-h-10 rounded-lg border border-border bg-background px-2 text-sm text-foreground"><option value="owner">Owner</option><option value="admin">Admin</option><option value="engineer">Engineer</option><option value="viewer">Viewer</option></select> : <span className="rounded-full border border-border bg-surface-subtle px-2.5 py-1 text-xs font-medium text-foreground">{prettyRole(member.role)}</span>}</td>
                          <td className="px-4 py-3"><span className={member.mfa_enabled ? "inline-flex items-center gap-1.5 text-success" : "inline-flex items-center gap-1.5 text-warning"}>{member.mfa_enabled ? <Check size={15} aria-hidden="true" /> : <Clock3 size={15} aria-hidden="true" />}{member.mfa_enabled ? "Enrolled" : "Required"}</span></td>
                          <td className="px-4 py-3 text-right">{canManage && !isSelf && <button type="button" aria-label={`Remove ${member.name}`} disabled={busy || (member.role === "owner" && !isOwner)} onClick={() => void removeMember(member)} className="inline-flex min-h-10 items-center gap-2 rounded-lg px-3 text-sm font-medium text-danger transition-colors hover:bg-danger-subtle disabled:cursor-not-allowed disabled:opacity-50"><UserMinus size={15} aria-hidden="true" /> Remove</button>}</td>
                        </tr>;
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>

        <aside className="space-y-5">
          {selectedWorkspace?.kind === "personal" && (
            <section className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6">
              <h2 className="text-base font-semibold text-foreground">Create a company workspace</h2>
              <p className="mt-1 text-sm text-foreground-muted">A separate boundary for your company’s people, projects, runs, and audit history.</p>
              {!hasMfa && <p className="mt-4 rounded-lg bg-warning-subtle p-3 text-sm text-foreground">Set up MFA before creating a company workspace. <Link className="font-semibold text-primary underline underline-offset-2" href="/dashboard/profile">Go to security settings</Link>.</p>}
              <form onSubmit={(event) => void createWorkspace(event)} className="mt-4 space-y-3">
                <label htmlFor="workspace-name" className="block text-sm font-medium text-foreground">Company name</label>
                <input id="workspace-name" value={workspaceName} onChange={(event) => setWorkspaceName(event.target.value)} minLength={2} maxLength={120} required placeholder="Acme engineering" className="min-h-11 w-full rounded-lg border border-border bg-background px-3 text-sm text-foreground placeholder:text-foreground-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" />
                <button disabled={busy || !hasMfa} type="submit" className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60">{busy ? <Loader2 size={17} className="animate-spin" aria-hidden="true" /> : <Building2 size={17} aria-hidden="true" />} Create workspace</button>
              </form>
            </section>
          )}

          {isOrganization && canManage && hasMfa && (
            <section className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6">
              <div className="flex items-start gap-3"><span className="grid size-10 place-items-center rounded-xl bg-primary/10 text-primary"><MailPlus size={18} aria-hidden="true" /></span><div><h2 className="text-base font-semibold text-foreground">Invite an engineer</h2><p className="mt-1 text-sm text-foreground-muted">They must verify this email and enable MFA before entering the company workspace.</p></div></div>
              <form onSubmit={(event) => void inviteMember(event)} className="mt-5 space-y-3">
                <div><label htmlFor="invite-email" className="mb-1.5 block text-sm font-medium text-foreground">Work email</label><input id="invite-email" type="email" autoComplete="email" value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} required maxLength={254} placeholder="engineer@company.com" className="min-h-11 w-full rounded-lg border border-border bg-background px-3 text-sm text-foreground placeholder:text-foreground-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" /></div>
                <div><label htmlFor="invite-role" className="mb-1.5 block text-sm font-medium text-foreground">Workspace role</label><select id="invite-role" value={inviteRole} onChange={(event) => setInviteRole(event.target.value)} className="min-h-11 w-full rounded-lg border border-border bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><option value="engineer">Engineer · deploy and operate</option><option value="viewer">Viewer · read only</option>{isOwner && <option value="admin">Admin · manage team access</option>}</select></div>
                <button type="submit" disabled={busy || !inviteEmail.trim()} className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60">{busy ? <Loader2 size={17} className="animate-spin" aria-hidden="true" /> : <MailPlus size={17} aria-hidden="true" />} Send invitation</button>
              </form>
            </section>
          )}

          {isOrganization && canManage && hasMfa && (
            <section className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-6">
              <div className="mb-4 flex items-center justify-between gap-2"><h2 className="text-base font-semibold text-foreground">Pending invitations</h2><span className="rounded-full bg-surface-subtle px-2.5 py-1 text-xs font-medium text-foreground-muted">{invitations.length}</span></div>
              {invitations.length === 0 ? <p className="rounded-xl border border-dashed border-border px-3 py-5 text-center text-sm text-foreground-muted">Invitations you send will appear here for 72 hours.</p> : <ul className="divide-y divide-border">{invitations.map((invitation) => <li key={invitation.id} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"><div className="min-w-0"><p className="truncate text-sm font-medium text-foreground">{invitation.email}</p><p className="mt-1 text-xs text-foreground-muted">{prettyRole(invitation.role)} · {formatExpiry(invitation.expires_at)}</p></div><button type="button" disabled={busy} onClick={() => void revokeInvite(invitation)} className="min-h-10 shrink-0 rounded-lg px-3 text-sm font-medium text-danger hover:bg-danger-subtle disabled:opacity-50">Revoke</button></li>)}</ul>}
            </section>
          )}
        </aside>
      </section>

      {isOrganization && <StatePanel variant="info" title="Shared projects; attributed deployment runs" description="Projects and deployment history are scoped to this company, and every run records its initiating engineer. GitHub repository access and Azure deployment credentials remain connected per engineer, so the person starting a deploy must have access to both." />}

      {workspaces.length === 0 && <StatePanel variant="error" title="No workspace membership found" description="Refresh your account or contact your organization owner for a verified invitation." />}
    </div>
  );
}
