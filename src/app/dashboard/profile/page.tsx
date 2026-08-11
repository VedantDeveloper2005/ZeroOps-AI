"use client";

import { useCallback, useEffect, useState } from "react";
import Image from "next/image";
import {
  CalendarDays,
  CheckCircle2,
  Copy,
  Loader2,
  LockKeyhole,
  Mail,
  RefreshCw,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatePanel } from "@/components/ui/StatePanel";
import { useAuth } from "@/lib/AuthContext";
import { useNotifications } from "@/lib/NotificationContext";
import {
  api,
  getErrorMessage,
  type MFASetup,
  type MFAStatus,
  type UserProfile,
} from "@/lib/api";

const providerLabel = (provider: string) => {
  if (provider === "github") return "GitHub";
  if (provider === "google") return "Google";
  if (provider === "local") return "Email and password";
  return provider || "Not reported";
};

const formatDate = (value: string | null) => {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
};

export default function ProfilePage() {
  const { user } = useAuth();
  const { addToast } = useNotifications();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [mfaStatus, setMfaStatus] = useState<MFAStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [profileLoadError, setProfileLoadError] = useState<string | null>(null);
  const [mfaError, setMfaError] = useState<string | null>(null);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [isUpdating, setIsUpdating] = useState(false);
  const [mfaSetup, setMfaSetup] = useState<MFASetup | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [mfaBusy, setMfaBusy] = useState(false);

  const loadAccount = useCallback(async () => {
    setIsLoading(true);
    setProfileLoadError(null);
    setMfaError(null);

    const [profileResult, mfaResult] = await Promise.allSettled([
      api.getProfile(),
      api.getMfaStatus(),
    ]);

    if (profileResult.status === "fulfilled") {
      setProfile(profileResult.value);
      setFirstName(profileResult.value.first_name || "");
      setLastName(profileResult.value.last_name || "");
    } else {
      setProfileLoadError(
        getErrorMessage(profileResult.reason, "Your account profile could not be loaded."),
      );
    }

    if (mfaResult.status === "fulfilled") {
      setMfaStatus(mfaResult.value);
    } else {
      setMfaError(
        getErrorMessage(mfaResult.reason, "Multi-factor authentication status could not be loaded."),
      );
    }

    setIsLoading(false);
  }, []);

  useEffect(() => {
    void loadAccount();
  }, [loadAccount]);

  const updateProfile = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsUpdating(true);
    setProfileLoadError(null);
    try {
      await api.updateProfile({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
      });
      const updated = await api.getProfile();
      setProfile(updated);
      setFirstName(updated.first_name || "");
      setLastName(updated.last_name || "");
      addToast("Account details updated.", "success");
    } catch (updateError) {
      setProfileLoadError(
        getErrorMessage(updateError, "Your account details could not be updated."),
      );
    } finally {
      setIsUpdating(false);
    }
  };

  const startAuthenticatorSetup = async () => {
    setMfaBusy(true);
    setMfaError(null);
    try {
      setMfaSetup(await api.startMfaSetup());
      setRecoveryCodes([]);
      setMfaCode("");
    } catch (setupError) {
      setMfaError(
        getErrorMessage(
          setupError,
          "Authenticator setup could not be started. Sign in again if your session is not recent.",
        ),
      );
    } finally {
      setMfaBusy(false);
    }
  };

  const enableEmailMfa = async () => {
    const confirmed = window.confirm(
      "Enable email-code MFA? Future sign-ins will require a code delivered to your account email.",
    );
    if (!confirmed) return;

    setMfaBusy(true);
    setMfaError(null);
    try {
      const result = await api.setupEmailMfa();
      setRecoveryCodes(result.recovery_codes);
      setMfaSetup(null);
      setMfaCode("");
      setMfaStatus({
        enabled: true,
        method: "email",
        recovery_codes_remaining: result.recovery_codes.length,
      });
      addToast("Email-code MFA enabled.", "success");
    } catch (setupError) {
      setMfaError(
        getErrorMessage(
          setupError,
          "Email-code MFA could not be enabled. Sign in again if your session is not recent.",
        ),
      );
    } finally {
      setMfaBusy(false);
    }
  };

  const confirmAuthenticatorSetup = async (event: React.FormEvent) => {
    event.preventDefault();
    setMfaBusy(true);
    setMfaError(null);
    try {
      const result = await api.confirmMfaSetup(mfaCode);
      setRecoveryCodes(result.recovery_codes);
      setMfaSetup(null);
      setMfaCode("");
      setMfaStatus({
        enabled: true,
        method: "totp",
        recovery_codes_remaining: result.recovery_codes.length,
      });
      addToast("Authenticator MFA enabled.", "success");
    } catch (setupError) {
      setMfaError(
        getErrorMessage(setupError, "The authenticator code could not be verified."),
      );
    } finally {
      setMfaBusy(false);
    }
  };

  const disableMfa = async (event: React.FormEvent) => {
    event.preventDefault();
    const confirmed = window.confirm(
      "Disable multi-factor authentication for this account?",
    );
    if (!confirmed) return;

    setMfaBusy(true);
    setMfaError(null);
    try {
      await api.disableMfa(mfaCode);
      setMfaStatus({
        enabled: false,
        method: mfaStatus?.method,
        recovery_codes_remaining: 0,
      });
      setMfaCode("");
      setRecoveryCodes([]);
      addToast("Multi-factor authentication disabled.", "success");
    } catch (disableError) {
      setMfaError(
        getErrorMessage(disableError, "The verification or recovery code was not accepted."),
      );
    } finally {
      setMfaBusy(false);
    }
  };

  const copyRecoveryCodes = async () => {
    try {
      await navigator.clipboard.writeText(recoveryCodes.join("\n"));
      addToast("Recovery codes copied. Store them somewhere safe.", "success");
    } catch {
      addToast("Recovery codes could not be copied. Select and save them manually.", "error");
    }
  };

  if (isLoading) {
    return (
      <div className="mx-auto max-w-6xl">
        <PageHeader
          eyebrow="Account"
          title="Profile and security"
          description="Manage account details and the multi-factor method enforced at sign-in."
        />
        <div role="status" className="flex min-h-80 items-center justify-center rounded-xl border border-border bg-card shadow-sm">
          <Loader2 size={24} className="animate-spin text-primary motion-reduce:animate-none" aria-hidden="true" />
          <span className="ml-3 text-sm text-foreground-muted">Loading account…</span>
        </div>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="mx-auto max-w-6xl">
        <PageHeader
          eyebrow="Account"
          title="Profile and security"
          description="Manage account details and the multi-factor method enforced at sign-in."
        />
        <StatePanel
          variant="error"
          title="Account profile is unavailable"
          description={profileLoadError || "The profile response was empty."}
          action={{ label: "Try again", onClick: () => void loadAccount() }}
        />
      </div>
    );
  }

  const displayName =
    [profile.first_name, profile.last_name].filter(Boolean).join(" ") || profile.email;
  const initials =
    `${profile.first_name?.[0] || ""}${profile.last_name?.[0] || ""}`.toUpperCase() ||
    profile.email[0]?.toUpperCase() ||
    "U";

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        eyebrow="Account"
        title="Profile and security"
        description="Manage account details and the multi-factor method enforced at sign-in."
      />

      {profileLoadError && (
        <div
          role="alert"
          className="mb-5 rounded-xl border border-danger/25 bg-danger-subtle p-4 text-sm text-danger"
        >
          {profileLoadError}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
          <section className="overflow-hidden rounded-xl border border-border bg-card text-center shadow-sm">
            <div className="h-1 bg-primary" aria-hidden="true" />
            <div className="p-5">
            <div
              aria-hidden="true"
              className="mx-auto grid h-16 w-16 place-items-center rounded-full border border-primary/25 bg-primary-subtle text-xl font-semibold text-primary"
            >
              {initials}
            </div>
            <h2 className="mt-4 break-words text-base font-semibold text-foreground">
              {displayName}
            </h2>
            <p className="mt-1 break-all text-xs text-foreground-muted">{profile.email}</p>
            {user?.email_verified === true && (
              <span className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-success/25 bg-success-subtle px-2.5 py-1 text-xs font-semibold text-success">
                <CheckCircle2 size={12} aria-hidden="true" />
                Verified email
              </span>
            )}
            </div>
          </section>

          <section
            aria-labelledby="account-record-heading"
            className="rounded-xl border border-border bg-card p-5 shadow-sm"
          >
            <h2 id="account-record-heading" className="text-sm font-semibold text-foreground">
              Account record
            </h2>
            <dl className="mt-4 space-y-3 text-xs">
              <div className="flex items-start justify-between gap-3">
                <dt className="flex items-center gap-1.5 text-foreground-muted">
                  <LockKeyhole size={13} aria-hidden="true" />
                  Sign-in
                </dt>
                <dd className="text-right font-medium text-foreground">
                  {providerLabel(profile.provider)}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-3">
                <dt className="flex items-center gap-1.5 text-foreground-muted">
                  <CalendarDays size={13} aria-hidden="true" />
                  Joined
                </dt>
                <dd className="text-right font-medium text-foreground">
                  {formatDate(profile.created_at)}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-3">
                <dt className="text-foreground-muted">Projects</dt>
                <dd className="font-mono font-medium tabular-nums text-foreground">
                  {profile.total_projects}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-3">
                <dt className="text-foreground-muted">Deployments</dt>
                <dd className="font-mono font-medium tabular-nums text-foreground">
                  {profile.total_deployments}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-3">
                <dt className="text-foreground-muted">Active now</dt>
                <dd className="font-mono font-medium tabular-nums text-foreground">
                  {profile.active_deployments}
                </dd>
              </div>
            </dl>
          </section>
        </aside>

        <div className="space-y-6">
          <section
            aria-labelledby="profile-details-heading"
            className="rounded-xl border border-border bg-card p-5 shadow-sm sm:p-6"
          >
            <div className="flex items-center gap-3 border-b border-border pb-4">
              <span className="grid h-10 w-10 place-items-center rounded-lg bg-primary-subtle text-primary">
                <UserRound size={18} aria-hidden="true" />
              </span>
              <div>
              <h2 id="profile-details-heading" className="text-base font-semibold text-foreground">
                Account details
              </h2>
                <p className="mt-0.5 text-xs text-foreground-muted">Identity fields stored for this account.</p>
              </div>
            </div>

            <form onSubmit={updateProfile} className="mt-5 space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="profile-first-name" className="text-sm font-medium text-foreground">
                    First name
                  </label>
                  <input
                    id="profile-first-name"
                    type="text"
                    autoComplete="given-name"
                    value={firstName}
                    onChange={(event) => setFirstName(event.target.value)}
                    className="mt-2 min-h-11 w-full rounded-lg border border-border bg-background-secondary px-3 text-base text-foreground outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/15 sm:text-sm"
                  />
                </div>
                <div>
                  <label htmlFor="profile-last-name" className="text-sm font-medium text-foreground">
                    Last name
                  </label>
                  <input
                    id="profile-last-name"
                    type="text"
                    autoComplete="family-name"
                    value={lastName}
                    onChange={(event) => setLastName(event.target.value)}
                    className="mt-2 min-h-11 w-full rounded-lg border border-border bg-background-secondary px-3 text-base text-foreground outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/15 sm:text-sm"
                  />
                </div>
              </div>

              <div>
                <p className="text-sm font-medium text-foreground">Email address</p>
                <div className="mt-2 flex min-h-11 items-center gap-2 rounded-lg border border-border bg-surface-subtle px-3 text-sm text-foreground-muted">
                  <Mail size={15} aria-hidden="true" />
                  <span className="min-w-0 break-all">{profile.email}</span>
                </div>
                <p className="mt-1.5 text-xs leading-5 text-foreground-muted">
                  Email changes are not available in the current account API.
                </p>
              </div>

              <div className="flex justify-end pt-1">
                <button type="submit" disabled={isUpdating} className="ops-primary disabled:opacity-60">
                  {isUpdating ? (
                    <>
                      <Loader2 size={15} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                      Saving…
                    </>
                  ) : (
                    "Save changes"
                  )}
                </button>
              </div>
            </form>
          </section>

          <section
            aria-labelledby="mfa-heading"
            className="rounded-xl border border-border bg-card p-5 shadow-sm sm:p-6"
          >
            <div className="flex items-center gap-3 border-b border-border pb-4">
              <span className="grid h-10 w-10 place-items-center rounded-lg bg-success-subtle text-success">
                <ShieldCheck size={18} aria-hidden="true" />
              </span>
              <div>
              <h2 id="mfa-heading" className="text-base font-semibold text-foreground">
                Multi-factor authentication
              </h2>
                <p className="mt-0.5 max-w-2xl text-xs leading-5 text-foreground-muted">
                  Require a second code after primary sign-in.
                </p>
              </div>
            </div>

            {mfaError && (
              <div
                role="alert"
                className="mt-4 rounded-lg border border-danger/25 bg-danger-subtle p-3 text-xs leading-5 text-danger"
              >
                {mfaError}
              </div>
            )}

            {recoveryCodes.length > 0 ? (
              <div role="status" className="mt-5 rounded-xl border border-success/25 bg-success-subtle p-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <CheckCircle2 size={16} className="text-success" aria-hidden="true" />
                  Save these recovery codes now
                </div>
                <p className="mt-1.5 text-xs leading-5 text-foreground-muted">
                  Each code works once. The backend will not return them again after this page is left.
                </p>
                <div className="mt-3 grid grid-cols-2 gap-2 rounded-lg border border-border bg-card p-3 font-mono text-xs text-foreground sm:grid-cols-3 md:grid-cols-5">
                  {recoveryCodes.map((code) => (
                    <code key={code} className="select-all">
                      {code}
                    </code>
                  ))}
                </div>
                <button type="button" onClick={() => void copyRecoveryCodes()} className="ops-secondary mt-3">
                  <Copy size={15} aria-hidden="true" />
                  Copy recovery codes
                </button>
              </div>
            ) : mfaSetup ? (
              <form onSubmit={confirmAuthenticatorSetup} className="mt-5 space-y-5">
                <div className="grid gap-5 sm:grid-cols-[160px_minmax(0,1fr)] sm:items-center">
                  <div className="mx-auto rounded-lg border border-border bg-white p-2">
                    <Image
                      src={mfaSetup.qr_code_data_uri}
                      alt="QR code for authenticator setup"
                      width={144}
                      height={144}
                      unoptimized
                    />
                  </div>
                  <div className="space-y-2 text-xs leading-5 text-foreground-muted">
                    <p className="font-medium text-foreground">
                      Scan the QR code with your authenticator app.
                    </p>
                    <p>If scanning is unavailable, enter this setup key manually:</p>
                    <code className="block break-all rounded-lg border border-border bg-background-secondary p-2 font-mono text-foreground">
                      {mfaSetup.manual_key}
                    </code>
                    <p>
                      Setup expires at{" "}
                      {new Date(mfaSetup.expires_at).toLocaleTimeString(undefined, {
                        hour: "numeric",
                        minute: "2-digit",
                      })}
                      .
                    </p>
                  </div>
                </div>
                <div>
                  <label htmlFor="mfa-setup-code" className="text-sm font-medium text-foreground">
                    Six-digit authenticator code
                  </label>
                  <input
                    id="mfa-setup-code"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    value={mfaCode}
                    onChange={(event) =>
                      setMfaCode(event.target.value.replace(/\D/g, "").slice(0, 6))
                    }
                    required
                    className="mt-2 min-h-11 w-full rounded-lg border border-border bg-background-secondary px-3 font-mono text-base tracking-[0.18em] text-foreground outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/15"
                  />
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="submit"
                    disabled={mfaBusy || mfaCode.length !== 6}
                    className="ops-primary disabled:opacity-60"
                  >
                    {mfaBusy ? (
                      <>
                        <Loader2 size={15} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                        Verifying…
                      </>
                    ) : (
                      "Enable authenticator MFA"
                    )}
                  </button>
                  <button
                    type="button"
                    disabled={mfaBusy}
                    onClick={() => {
                      setMfaSetup(null);
                      setMfaCode("");
                      setMfaError(null);
                    }}
                    className="ops-secondary disabled:opacity-60"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            ) : mfaStatus?.enabled ? (
              <div className="mt-5 space-y-4">
                <div className="rounded-lg border border-success/25 bg-success-subtle p-3 text-xs leading-5 text-foreground">
                  <span className="font-semibold">MFA is enabled.</span>{" "}
                  Current method:{" "}
                  {mfaStatus.method === "email" ? "email code" : "authenticator app"}.{" "}
                  {mfaStatus.recovery_codes_remaining} recovery{" "}
                  {mfaStatus.recovery_codes_remaining === 1 ? "code remains" : "codes remain"}.
                </div>
                <p className="text-xs leading-5 text-foreground-muted">
                  To use a different method, disable the current method and enroll again.
                </p>
                <form onSubmit={disableMfa} className="space-y-3 border-t border-border pt-4">
                  <div>
                    <label htmlFor="mfa-disable-code" className="text-sm font-medium text-foreground">
                      {mfaStatus.method === "email"
                        ? "Recovery code"
                        : "Authenticator or recovery code"}
                    </label>
                    <input
                      id="mfa-disable-code"
                      type="text"
                      autoComplete="one-time-code"
                      maxLength={16}
                      value={mfaCode}
                      onChange={(event) => setMfaCode(event.target.value)}
                      required
                      className="mt-2 min-h-11 w-full rounded-lg border border-border bg-background-secondary px-3 font-mono text-base text-foreground outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/15 sm:text-sm"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={mfaBusy || !mfaCode.trim()}
                    className="ops-danger disabled:opacity-60"
                  >
                    {mfaBusy ? (
                      <>
                        <Loader2 size={15} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                        Disabling…
                      </>
                    ) : (
                      "Disable MFA"
                    )}
                  </button>
                </form>
              </div>
            ) : mfaStatus ? (
              <div className="mt-5 flex flex-col gap-3 sm:flex-row">
                <button
                  type="button"
                  onClick={() => void startAuthenticatorSetup()}
                  disabled={mfaBusy}
                  className="ops-primary disabled:opacity-60"
                >
                  {mfaBusy ? (
                    <Loader2 size={15} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                  ) : (
                    <ShieldCheck size={15} aria-hidden="true" />
                  )}
                  Set up authenticator
                </button>
                <button
                  type="button"
                  onClick={() => void enableEmailMfa()}
                  disabled={mfaBusy}
                  className="ops-secondary disabled:opacity-60"
                >
                  <Mail size={15} aria-hidden="true" />
                  Use email codes
                </button>
              </div>
            ) : (
              <div className="mt-5 rounded-lg border border-border bg-surface-subtle p-4">
                <p className="text-xs text-foreground-muted">
                  MFA status is unavailable.
                </p>
                <button type="button" onClick={() => void loadAccount()} className="ops-secondary mt-3">
                  <RefreshCw size={15} aria-hidden="true" />
                  Try again
                </button>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
