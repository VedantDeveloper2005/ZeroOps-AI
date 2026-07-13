"use client";

import { motion } from "framer-motion";
import { useState, useEffect } from "react";
import Image from "next/image";
import { User, Mail, Shield, Calendar, Key, RefreshCw, Eye, EyeOff, Layout, Server, Smartphone, Copy, CheckCircle2, XCircle } from "lucide-react";
import { api, type MFASetup, type MFAStatus, type UserProfile } from "@/lib/api";
import { useNotifications } from "@/lib/NotificationContext";

export default function ProfilePage() {
  const { addToast } = useNotifications();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [isUpdating, setIsUpdating] = useState(false);
  const [apiKeyVisible, setApiKeyVisible] = useState(false);
  const [copied, setCopied] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [apiKeyLoading, setApiKeyLoading] = useState(true);
  const [apiKeyRegenerating, setApiKeyRegenerating] = useState(false);
  const [mfaStatus, setMfaStatus] = useState<MFAStatus | null>(null);
  const [mfaSetup, setMfaSetup] = useState<MFASetup | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [mfaBusy, setMfaBusy] = useState(false);

  useEffect(() => {
    async function loadProfile() {
      try {
        const data = await api.getProfile();
        setProfile(data);
        setFirstName(data.first_name || "");
        setLastName(data.last_name || "");
      } catch (err) {
        console.error("Failed to load profile:", err);
      } finally {
        setIsLoading(false);
      }
    }
    loadProfile();
  }, []);

  useEffect(() => {
    async function loadApiKey() {
      setApiKeyLoading(true);
      try {
        const data = await api.getApiKey();
        setApiKey(data.apiKey);
      } catch (err) {
        console.error("Failed to load API key:", err);
        addToast("Failed to load API key", "error");
      } finally {
        setApiKeyLoading(false);
      }
    }
    loadApiKey();
  }, [addToast]);

  useEffect(() => {
    async function loadMfaStatus() {
      try {
        setMfaStatus(await api.getMfaStatus());
      } catch (err) {
        console.error("Failed to load MFA status:", err);
        addToast("Failed to load multi-factor authentication status", "error");
      }
    }
    loadMfaStatus();
  }, [addToast]);

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsUpdating(true);
    try {
      await api.updateProfile({
        first_name: firstName,
        last_name: lastName,
      });
      addToast("Profile updated successfully!", "success");
      const updated = await api.getProfile();
      setProfile(updated);
    } catch (err) {
      console.error(err);
      addToast("Failed to update profile", "error");
    } finally {
      setIsUpdating(false);
    }
  };

  const copyApiKey = () => {
    if (!apiKey) return;
    navigator.clipboard.writeText(apiKey);
    setCopied(true);
    addToast("Access token copied to clipboard!", "success");
    setTimeout(() => setCopied(false), 2000);
  };

  const regenerateApiKey = async () => {
    setApiKeyRegenerating(true);
    try {
      const data = await api.regenerateApiKey();
      setApiKey(data.apiKey);
      addToast("Regenerated CLI access token.", "success");
    } catch (err) {
      console.error(err);
      addToast("Failed to regenerate access key", "error");
    } finally {
      setApiKeyRegenerating(false);
    }
  };

  const startEmailMfaSetup = async () => {
    setMfaBusy(true);
    try {
      const result = await api.setupEmailMfa();
      setRecoveryCodes(result.recovery_codes);
      setMfaSetup(null);
      setMfaCode("");
      setMfaStatus({ enabled: true, method: "email", recovery_codes_remaining: result.recovery_codes.length });
      addToast("Email Multi-factor authentication is now enabled", "success");
    } catch (err) {
      console.error(err);
      addToast("Unable to start MFA setup. Sign in again if your session is older than 10 minutes.", "error");
    } finally {
      setMfaBusy(false);
    }
  };

  const toggleMfaMethod = async (method: "totp" | "email") => {
    setMfaBusy(true);
    try {
      await api.updateMfaMethod(method);
      setMfaStatus(prev => prev ? { ...prev, method } : null);
      addToast(`MFA method updated to ${method === "totp" ? "Authenticator App" : "Email Code"}`, "success");
    } catch (err) {
      console.error(err);
      addToast("Failed to update MFA method", "error");
    } finally {
      setMfaBusy(false);
    }
  };

  const startMfaSetup = async () => {
    setMfaBusy(true);
    try {
      const setup = await api.startMfaSetup();
      setMfaSetup(setup);
      setRecoveryCodes([]);
      setMfaCode("");
    } catch (err) {
      console.error(err);
      addToast("Unable to start MFA setup. Sign in again if your session is older than 10 minutes.", "error");
    } finally {
      setMfaBusy(false);
    }
  };

  const confirmMfaSetup = async (event: React.FormEvent) => {
    event.preventDefault();
    setMfaBusy(true);
    try {
      const result = await api.confirmMfaSetup(mfaCode);
      setRecoveryCodes(result.recovery_codes);
      setMfaSetup(null);
      setMfaCode("");
      setMfaStatus({ enabled: true, recovery_codes_remaining: result.recovery_codes.length });
      addToast("Multi-factor authentication is now enabled", "success");
    } catch (err) {
      console.error(err);
      addToast("The authenticator code could not be verified", "error");
    } finally {
      setMfaBusy(false);
    }
  };

  const disableMfa = async (event: React.FormEvent) => {
    event.preventDefault();
    setMfaBusy(true);
    try {
      await api.disableMfa(mfaCode);
      setMfaStatus({ enabled: false, recovery_codes_remaining: 0 });
      setMfaCode("");
      setRecoveryCodes([]);
      addToast("Multi-factor authentication has been disabled", "success");
    } catch (err) {
      console.error(err);
      addToast("The authenticator or recovery code could not be verified", "error");
    } finally {
      setMfaBusy(false);
    }
  };

  const copyRecoveryCodes = async () => {
    await navigator.clipboard.writeText(recoveryCodes.join("\n"));
    addToast("Recovery codes copied. Store them somewhere safe.", "success");
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <RefreshCw className="animate-spin text-primary" size={24} />
      </div>
    );
  }

  const initials = profile
    ? `${(profile.first_name || "")[0] || ""}${(profile.last_name || "")[0] || ""}`.toUpperCase()
    : "U";

  const dateStr = profile?.created_at
    ? new Date(profile.created_at).toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : "Not recorded";

  return (
    <div className="space-y-6">
      <div className="grid md:grid-cols-3 gap-6">
        {/* Left column: Overview & Stats */}
        <div className="space-y-6">
          {/* Profile Overview Card */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-card border border-border rounded-xl p-6 text-center flex flex-col items-center justify-center relative overflow-hidden shadow-sm"
          >
            <div className="w-20 h-20 rounded-full bg-primary-subtle flex items-center justify-center text-3xl font-extrabold text-primary mb-4 border border-primary/20 shadow-inner">
              {initials || "U"}
            </div>
            <h3 className="text-lg font-bold text-foreground">
              {profile?.first_name ? `${profile.first_name} ${profile.last_name || ""}` : profile?.email || "Account"}
            </h3>
            <p className="text-xs text-foreground-muted mb-4">{profile?.email}</p>
            
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary-subtle text-primary text-xs font-semibold uppercase tracking-wider">
              <Shield size={12} />
              {profile?.plan || "No plan assigned"}
            </div>

            <div className="border-t border-border/60 w-full my-5" />

            <div className="flex flex-col gap-2 w-full text-left text-xs">
              <div className="flex justify-between">
                <span className="text-foreground-muted flex items-center gap-1"><Calendar size={12} /> Joined:</span>
                <span className="text-foreground font-semibold">{dateStr}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-foreground-muted flex items-center gap-1"><Layout size={12} /> Projects:</span>
                <span className="text-foreground font-semibold">{profile?.total_projects ?? 0} connected</span>
              </div>
              <div className="flex justify-between">
                <span className="text-foreground-muted flex items-center gap-1"><Server size={12} /> Deployments:</span>
                <span className="text-foreground font-semibold">{profile?.total_deployments ?? 0} total</span>
              </div>
            </div>
          </motion.div>
        </div>

        {/* Right column: Form & Security */}
        <div className="md:col-span-2 space-y-6">
          {/* Edit Profile Form */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="bg-card border border-border rounded-xl p-6 shadow-sm"
          >
            <h3 className="font-bold text-base mb-4 flex items-center gap-2 text-foreground">
              <User size={18} className="text-primary" />
              Edit Account Information
            </h3>

            <form onSubmit={handleUpdateProfile} className="space-y-4">
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-foreground-muted uppercase">First Name</label>
                  <input
                    type="text"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    required
                    className="w-full bg-background-secondary border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:ring-1 focus:ring-primary outline-none"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-foreground-muted uppercase">Last Name</label>
                  <input
                    type="text"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    className="w-full bg-background-secondary border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:ring-1 focus:ring-primary outline-none"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] font-bold text-foreground-muted uppercase">Email Address</label>
                <div className="flex items-center gap-2 bg-background-secondary border border-border/80 rounded-lg px-3 py-2 text-xs text-foreground-muted">
                  <Mail size={14} />
                  <span>{profile?.email}</span>
                  {profile?.email_verified ? (
                    <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold text-emerald-400">
                      <CheckCircle2 size={10} /> Verified
                    </span>
                  ) : (
                    <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-0.5 text-[10px] font-bold text-red-400">
                      <XCircle size={10} /> Unverified
                    </span>
                  )}
                </div>
                <p className="text-[10px] text-foreground-muted">Contact support if you need to update your email address.</p>
              </div>

              <div className="pt-2 flex justify-end">
                <button
                  type="submit"
                  disabled={isUpdating}
                  className="px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-xs font-bold transition cursor-pointer shadow-sm"
                >
                  {isUpdating ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.08 }}
            className="bg-card border border-border rounded-xl p-6 shadow-sm"
          >
            <h3 className="font-bold text-base mb-2 flex items-center gap-2 text-foreground">
              <Smartphone size={18} className="text-primary" />
              Multi-factor authentication
            </h3>
            <p className="text-xs text-foreground-muted mb-4 leading-5">
              Protect this account with a time-based code from an authenticator app. Google Authenticator, 1Password, Authy, and similar apps are supported.
            </p>

            {recoveryCodes.length > 0 ? (
              <div className="rounded-xl border border-success/30 bg-success/10 p-4">
                <div className="mb-2 flex items-center gap-2 text-sm font-bold text-foreground"><CheckCircle2 size={16} className="text-success" /> Save your recovery codes now</div>
                <p className="mb-3 text-xs leading-5 text-foreground-muted">Each code works once. They will not be shown again after you leave this page.</p>
                <div className="grid grid-cols-2 gap-2 rounded-lg border border-border bg-background-secondary p-3 font-mono text-xs text-foreground sm:grid-cols-5">
                  {recoveryCodes.map((code) => <code key={code}>{code}</code>)}
                </div>
                <button type="button" onClick={copyRecoveryCodes} className="mt-3 inline-flex min-h-11 items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-xs font-bold text-foreground transition hover:bg-card-hover">
                  <Copy size={14} /> Copy recovery codes
                </button>
              </div>
            ) : mfaSetup ? (
              <form onSubmit={confirmMfaSetup} className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-[160px_1fr] sm:items-center">
                  <div className="mx-auto rounded-lg border border-border bg-white p-2"><Image src={mfaSetup.qr_code_data_uri} alt="QR code for configuring your authenticator app" width={144} height={144} unoptimized /></div>
                  <div className="space-y-2">
                    <p className="text-xs font-semibold text-foreground">1. Scan the QR code with your authenticator app.</p>
                    <p className="text-xs text-foreground-muted">2. If you cannot scan it, enter this key manually:</p>
                    <code className="block break-all rounded-lg border border-border bg-background-secondary p-2 font-mono text-xs text-foreground">{mfaSetup.manual_key}</code>
                    <p className="text-[11px] text-foreground-muted">This setup code expires at {new Date(mfaSetup.expires_at).toLocaleTimeString()}.</p>
                  </div>
                </div>
                <div className="space-y-1.5">
                  <label htmlFor="mfa-confirmation-code" className="text-[10px] font-bold text-foreground-muted uppercase">3. Enter the six-digit code</label>
                  <input id="mfa-confirmation-code" value={mfaCode} onChange={(event) => setMfaCode(event.target.value)} type="text" inputMode="numeric" autoComplete="one-time-code" required className="w-full min-h-11 bg-background-secondary border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:ring-2 focus:ring-primary/30 outline-none" placeholder="123456" />
                </div>
                <div className="flex flex-wrap gap-3">
                  <button type="submit" disabled={mfaBusy || !mfaCode.trim()} className="min-h-11 rounded-lg bg-primary px-4 py-2 text-xs font-bold text-white transition hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60">{mfaBusy ? "Verifying..." : "Enable MFA"}</button>
                  <button type="button" onClick={() => { setMfaSetup(null); setMfaCode(""); }} disabled={mfaBusy} className="min-h-11 rounded-lg border border-border px-4 py-2 text-xs font-bold text-foreground transition hover:bg-background-secondary">Cancel</button>
                </div>
              </form>
            ) : mfaStatus?.enabled ? (
              <div className="space-y-4">
                <div className="space-y-2">
                  <label className="text-[10px] font-bold text-foreground-muted uppercase">Preferred Verification Method</label>
                  <div className="flex gap-4">
                    <label className="flex items-center gap-2 text-xs font-semibold text-foreground cursor-pointer">
                      <input 
                        type="radio" 
                        name="mfa_method" 
                        value="totp" 
                        checked={mfaStatus.method === "totp"}
                        onChange={() => toggleMfaMethod("totp")}
                        disabled={mfaBusy}
                        className="accent-primary" 
                      />
                      Authenticator App
                    </label>
                    <label className="flex items-center gap-2 text-xs font-semibold text-foreground cursor-pointer">
                      <input 
                        type="radio" 
                        name="mfa_method" 
                        value="email" 
                        checked={mfaStatus.method === "email"}
                        onChange={() => toggleMfaMethod("email")}
                        disabled={mfaBusy}
                        className="accent-primary" 
                      />
                      Email Code
                    </label>
                  </div>
                </div>

                <form onSubmit={disableMfa} className="space-y-3 pt-2 border-t border-border/40">
                  <div className="rounded-lg border border-success/30 bg-success/10 px-3 py-2 text-xs text-foreground">
                    <span className="font-bold">MFA is enabled.</span> {mfaStatus.recovery_codes_remaining} recovery code{mfaStatus.recovery_codes_remaining === 1 ? "" : "s"} remaining.
                  </div>
                  <div className="space-y-1.5">
                    <label htmlFor="mfa-disable-code" className="text-[10px] font-bold text-foreground-muted uppercase">
                      {mfaStatus.method === "email" ? "Verification code or recovery code" : "Authenticator code or recovery code"}
                    </label>
                    <input id="mfa-disable-code" value={mfaCode} onChange={(event) => setMfaCode(event.target.value)} type="text" inputMode="numeric" autoComplete="one-time-code" required className="w-full min-h-11 bg-background-secondary border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:ring-2 focus:ring-primary/30 outline-none" placeholder="123456 or XXXX-XXXX" />
                  </div>
                  <button type="submit" disabled={mfaBusy || !mfaCode.trim()} className="min-h-11 rounded-lg border border-danger/40 bg-danger/10 px-4 py-2 text-xs font-bold text-danger transition hover:bg-danger/20 disabled:cursor-not-allowed disabled:opacity-60">{mfaBusy ? "Disabling..." : "Disable MFA"}</button>
                </form>
              </div>
            ) : (
              <div className="flex flex-col sm:flex-row gap-3">
                <button type="button" onClick={startMfaSetup} disabled={mfaBusy || mfaStatus === null} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-bold text-white transition hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60">
                  <Shield size={14} /> {mfaBusy ? "Preparing..." : "Set up Authenticator App"}
                </button>
                <button type="button" onClick={startEmailMfaSetup} disabled={mfaBusy || mfaStatus === null} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-xs font-bold text-foreground transition hover:bg-background-secondary disabled:cursor-not-allowed disabled:opacity-60">
                  <Mail size={14} /> {mfaBusy ? "Preparing..." : "Set up Email Code MFA"}
                </button>
              </div>
            )}
          </motion.div>

          {/* CLI Keys Management (mirroring settings key) */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="bg-card border border-border rounded-xl p-6 shadow-sm"
          >
            <h3 className="font-bold text-base mb-2 flex items-center gap-2 text-foreground">
              <Key size={18} className="text-primary" />
              CLI Access Tokens
            </h3>
            <p className="text-xs text-foreground-muted mb-4">
              Authorized credentials used by the ZeroOps CLI in your local development environment.
            </p>

            <div className="space-y-3">
              <div className="flex gap-2">
                <div className="flex-1 bg-background-secondary border border-border rounded-lg px-3 py-2 flex items-center justify-between min-w-0">
                  <span className="font-mono text-xs truncate select-none text-foreground-muted">
                    {apiKeyLoading ? "Loading..." : apiKeyVisible ? apiKey || "No key available" : "••••••••••••••••••••••••••••••••"}
                  </span>
                  <button
                    onClick={() => setApiKeyVisible(!apiKeyVisible)}
                    className="text-foreground-muted hover:text-foreground p-0.5 ml-2 flex-shrink-0 cursor-pointer"
                  >
                    {apiKeyVisible ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
                <button
                  onClick={copyApiKey}
                  disabled={!apiKey || apiKeyLoading}
                  className="px-3 bg-primary hover:bg-primary-hover text-white text-xs font-bold rounded-lg transition cursor-pointer shadow-sm disabled:opacity-50"
                >
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
              
              <button 
                onClick={regenerateApiKey}
                disabled={apiKeyRegenerating}
                className="w-full py-2 bg-background-secondary border border-border hover:bg-card-hover text-foreground text-xs font-bold rounded-lg transition flex items-center justify-center gap-1.5 cursor-pointer shadow-sm disabled:opacity-50"
              >
                <RefreshCw size={12} className={apiKeyRegenerating ? "animate-spin" : ""} />
                {apiKeyRegenerating ? "Regenerating..." : "Regenerate Access Key"}
              </button>
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
