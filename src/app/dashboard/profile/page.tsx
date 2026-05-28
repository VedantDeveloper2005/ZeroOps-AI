"use client";

import { motion } from "framer-motion";
import { useState, useEffect } from "react";
import { User, Mail, Shield, Calendar, Key, RefreshCw, Eye, EyeOff, Layout, Terminal, Server, Check } from "lucide-react";
import { api, type UserProfile } from "@/lib/api";
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
  const [apiKey, setApiKey] = useState("zo_live_84b72fd91c28c83e1a0b5a37f59b6c2d1e");

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
    navigator.clipboard.writeText(apiKey);
    setCopied(true);
    addToast("Access token copied to clipboard!", "success");
    setTimeout(() => setCopied(false), 2000);
  };

  const regenerateApiKey = () => {
    const chars = "abcdef0123456789";
    let tokenSuffix = "";
    for (let i = 0; i < 32; i++) {
      tokenSuffix += chars[Math.floor(Math.random() * chars.length)];
    }
    const newToken = `zo_live_${tokenSuffix}`;
    setApiKey(newToken);
    addToast("Regenerated CLI access token.", "success");
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
    : "—";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">User Profile & Account</h1>
        <p className="text-foreground-muted text-sm mt-1">
          Manage your personal details, plan settings, and terminal security keys.
        </p>
      </div>

      <div className="grid md:grid-cols-3 gap-6">
        {/* Left column: Overview & Stats */}
        <div className="space-y-6">
          {/* Profile Overview Card */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass rounded-xl p-6 text-center flex flex-col items-center justify-center relative overflow-hidden"
          >
            <div className="w-20 h-20 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center text-3xl font-extrabold text-white mb-4 shadow-xl border border-white/10">
              {initials || "VS"}
            </div>
            <h3 className="text-lg font-bold text-foreground">
              {profile?.first_name ? `${profile.first_name} ${profile.last_name || ""}` : "Vedant S."}
            </h3>
            <p className="text-xs text-foreground-muted mb-4">{profile?.email}</p>
            
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary-subtle text-primary text-xs font-semibold uppercase tracking-wider">
              <Shield size={12} />
              {profile?.plan || "Starter Plan"}
            </div>

            <div className="border-t border-border/50 w-full my-5" />

            <div className="flex flex-col gap-2 w-full text-left text-xs">
              <div className="flex justify-between">
                <span className="text-foreground-muted flex items-center gap-1"><Calendar size={12} /> Joined:</span>
                <span className="text-foreground font-medium">{dateStr}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-foreground-muted flex items-center gap-1"><Layout size={12} /> Projects:</span>
                <span className="text-foreground font-medium">{profile?.total_projects ?? 0} connected</span>
              </div>
              <div className="flex justify-between">
                <span className="text-foreground-muted flex items-center gap-1"><Server size={12} /> Deployments:</span>
                <span className="text-foreground font-medium">{profile?.total_deployments ?? 0} total</span>
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
            transition={{ delay: 0.1 }}
            className="glass rounded-xl p-6"
          >
            <h3 className="font-semibold text-lg mb-4 flex items-center gap-2">
              <User size={20} className="text-primary" />
              Edit Account Information
            </h3>

            <form onSubmit={handleUpdateProfile} className="space-y-4">
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground-muted uppercase">First Name</label>
                  <input
                    type="text"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    required
                    className="w-full bg-card border border-border rounded-xl px-4 py-2.5 text-sm text-foreground focus:ring-1 focus:ring-primary outline-none"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground-muted uppercase">Last Name</label>
                  <input
                    type="text"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    className="w-full bg-card border border-border rounded-xl px-4 py-2.5 text-sm text-foreground focus:ring-1 focus:ring-primary outline-none"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-foreground-muted uppercase">Email Address</label>
                <div className="flex items-center gap-2 bg-card border border-border rounded-xl px-4 py-2.5 text-sm text-foreground-muted">
                  <Mail size={16} />
                  <span>{profile?.email}</span>
                </div>
                <p className="text-[10px] text-foreground-muted">Contact support if you need to update your email address.</p>
              </div>

              <div className="pt-2 flex justify-end">
                <button
                  type="submit"
                  disabled={isUpdating}
                  className="px-5 py-2.5 bg-primary hover:bg-primary-hover text-white rounded-xl text-xs font-semibold transition glow-blue cursor-pointer"
                >
                  {isUpdating ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </motion.div>

          {/* CLI Keys Management (mirroring settings key) */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="glass rounded-xl p-6"
          >
            <h3 className="font-semibold text-lg mb-2 flex items-center gap-2">
              <Key size={20} className="text-primary" />
              CLI Access Tokens
            </h3>
            <p className="text-xs text-foreground-muted mb-4">
              Authorized credentials used by the ZeroOps CLI in your local development environment.
            </p>

            <div className="space-y-3">
              <div className="flex gap-2">
                <div className="flex-1 bg-card border border-border rounded-xl px-3 py-2 flex items-center justify-between min-w-0">
                  <span className="font-mono text-xs truncate select-none text-foreground-muted">
                    {apiKeyVisible ? apiKey : "••••••••••••••••••••••••••••••••••••"}
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
                  className="px-4 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-xl transition cursor-pointer"
                >
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
              
              <button 
                onClick={regenerateApiKey}
                className="w-full py-2.5 border border-border hover:bg-card-hover text-foreground text-xs font-semibold rounded-xl transition flex items-center justify-center gap-1.5 cursor-pointer"
              >
                <RefreshCw size={12} />
                Regenerate Access Key
              </button>
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
