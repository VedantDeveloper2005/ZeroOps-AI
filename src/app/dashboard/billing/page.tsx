"use client";

import { motion } from "framer-motion";
import { CreditCard, Check, Download, TrendingUp, Loader2 } from "lucide-react";
import { useState, useEffect } from "react";
import { api, type UserProfile } from "@/lib/api";

const billingHistory = [
  { id: "inv-001", date: "May 15, 2026", amount: "$99.00", status: "paid", plan: "Pro Plan (Monthly)" },
  { id: "inv-002", date: "Apr 15, 2026", amount: "$99.00", status: "paid", plan: "Pro Plan (Monthly)" },
  { id: "inv-003", date: "Mar 15, 2026", amount: "$99.00", status: "paid", plan: "Pro Plan (Monthly)" },
];

export default function BillingPage() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadProfile() {
      try {
        const data = await api.getProfile();
        setProfile(data);
      } catch (err) {
        console.error("Failed to load profile for billing:", err);
      } finally {
        setIsLoading(false);
      }
    }
    loadProfile();
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="animate-spin text-primary" size={24} />
      </div>
    );
  }

  const fullName = profile?.first_name 
    ? `${profile.first_name} ${profile.last_name || ""}`.trim()
    : "Vedant S.";

  const planName = profile?.plan 
    ? profile.plan.charAt(0).toUpperCase() + profile.plan.slice(1) + " Plan"
    : "Starter Plan";

  const isPro = profile?.plan === "pro";
  const planPrice = isPro ? 99 : 29;
  const maxDeploymentsLimit = isPro ? 200 : 5;
  const totalDeployments = profile?.total_deployments ?? 0;
  const deploymentsPercent = Math.min(100, Math.round((totalDeployments / maxDeploymentsLimit) * 100));

  const usageStats = [
    { name: "Compute CPU Hours", used: isPro ? "4,250" : "120", limit: isPro ? "10,000" : "500", unit: "hrs", percent: isPro ? 42.5 : 24, color: "bg-primary" },
    { name: "Bandwidth Egress", used: isPro ? "324.5" : "15.2", limit: isPro ? "500" : "50", unit: "GB", percent: isPro ? 64.9 : 30.4, color: "bg-accent" },
    { name: "Container Deployments", used: String(totalDeployments), limit: String(maxDeploymentsLimit), unit: "builds", percent: deploymentsPercent, color: "bg-success" },
    { name: "AI Autopilot Actions", used: isPro ? "2,450" : "0", limit: isPro ? "5,000" : "100", unit: "actions", percent: isPro ? 49 : 0, color: "bg-info" },
  ];

  return (
    <div className="space-y-6">
      <div className="grid lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Subscription Details + Usage */}
        <div className="lg:col-span-2 space-y-6">
          {/* Active Plan Card */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-card border border-border rounded-xl p-6 relative overflow-hidden shadow-sm"
          >
            <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-3xl pointer-events-none" />
            
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <span className="text-[10px] px-2.5 py-1 rounded-full bg-primary/10 text-primary font-bold tracking-wide uppercase">
                  Current Subscription
                </span>
                <h3 className="text-2xl font-bold text-foreground mt-3">{planName}</h3>
                <p className="text-foreground-muted text-xs mt-1">For production clusters and growing engineering teams.</p>
              </div>
              <div className="text-left sm:text-right">
                <p className="text-3xl font-extrabold text-foreground">${planPrice}<span className="text-xs font-semibold text-foreground-muted">/mo</span></p>
                <p className="text-[10px] text-foreground-muted mt-1.5 font-semibold">Next renewal: June 15, 2026</p>
              </div>
            </div>

            <div className="border-t border-border/60 my-5" />

            <div className="grid md:grid-cols-3 gap-4">
              {[(isPro ? "Unlimited Deployments" : "5 Deployments/mo"), (isPro ? "5 Active Environments" : "1 Active Environment"), "Autonomous AI Copilot"].map((feature) => (
                <div key={feature} className="flex items-center gap-2 text-xs font-semibold text-foreground-muted">
                  <div className="w-5 h-5 rounded-full bg-success/15 flex items-center justify-center flex-shrink-0">
                    <Check size={12} className="text-success" />
                  </div>
                  <span>{feature}</span>
                </div>
              ))}
            </div>

            <div className="mt-6 flex flex-wrap gap-3">
              <button className="px-3.5 py-2 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-lg transition cursor-pointer shadow-sm">
                Change Subscription Plan
              </button>
              <button className="px-3.5 py-2 bg-background-secondary border border-border hover:bg-background text-foreground text-xs font-semibold rounded-lg transition cursor-pointer">
                Cancel Subscription
              </button>
            </div>
          </motion.div>

          {/* Usage Meter Card */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="bg-card border border-border rounded-xl p-6 shadow-sm"
          >
            <h3 className="text-sm font-bold text-foreground mb-6 flex items-center gap-2">
              <TrendingUp size={16} className="text-primary" />
              Monthly Resource Usage
            </h3>

            <div className="grid md:grid-cols-2 gap-6">
              {usageStats.map((stat) => (
                <div key={stat.name} className="space-y-2">
                  <div className="flex justify-between text-xs font-semibold">
                    <span className="text-foreground-muted">{stat.name}</span>
                    <span className="text-foreground">
                      {stat.used} / {stat.limit} {stat.unit}
                    </span>
                  </div>
                  <div className="h-2 bg-background-secondary border border-border/40 rounded-full overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${stat.percent}%` }}
                      transition={{ duration: 1, delay: 0.3 }}
                      className={`h-full rounded-full ${stat.color}`}
                    />
                  </div>
                  <p className="text-[10px] text-foreground-muted text-right font-semibold">{stat.percent}% Consumed</p>
                </div>
              ))}
            </div>
          </motion.div>
        </div>

        {/* Right Col: Credit Card Mock + Invoices */}
        <div className="space-y-6">
          {/* Credit Card Mock (Premium Matte Graphite) */}
          <motion.div
            initial={{ opacity: 0, x: 15 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2 }}
            className="rounded-2xl p-5 bg-gradient-to-br from-zinc-800 to-zinc-950 text-white relative overflow-hidden shadow-xl h-48 flex flex-col justify-between border border-zinc-700/50"
          >
            <div className="absolute top-5 right-5 w-14 h-7 bg-white/10 rounded border border-white/20 backdrop-blur-md flex items-center justify-center font-bold text-[9px] uppercase tracking-widest text-white/70">
              ZeroOps
            </div>
            
            <div>
              <CreditCard size={28} className="text-white/80" />
              <p className="mt-6 text-base font-mono tracking-widest font-bold">••••  ••••  ••••  4829</p>
            </div>
            
            <div className="flex justify-between items-end">
              <div>
                <p className="text-[9px] text-white/50 uppercase font-semibold">Card Holder</p>
                <p className="text-xs font-bold tracking-wide mt-0.5">{fullName}</p>
              </div>
              <div>
                <p className="text-[9px] text-white/50 uppercase font-semibold">Expires</p>
                <p className="text-xs font-bold tracking-wide mt-0.5">12/30</p>
              </div>
            </div>
          </motion.div>

          {/* Invoices List */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="bg-card border border-border rounded-xl p-5 shadow-sm"
          >
            <h3 className="text-sm font-bold text-foreground mb-4">Billing History</h3>
            <div className="space-y-3">
              {billingHistory.map((invoice) => (
                <div key={invoice.id} className="flex items-center justify-between p-3 rounded-lg bg-background-secondary border border-border/50 hover:bg-card transition">
                  <div>
                    <p className="text-xs font-bold text-foreground">{invoice.plan}</p>
                    <p className="text-[10px] text-foreground-muted mt-0.5 font-semibold">{invoice.date}</p>
                  </div>
                  <div className="text-right flex items-center gap-3">
                    <div>
                      <p className="text-xs font-bold text-foreground">{invoice.amount}</p>
                      <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-success/15 text-success font-bold uppercase mt-0.5 inline-block">
                        {invoice.status}
                      </span>
                    </div>
                    <button className="p-1.5 bg-card border border-border/60 hover:bg-background-secondary rounded-lg text-foreground-muted hover:text-foreground cursor-pointer transition">
                      <Download size={12} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
