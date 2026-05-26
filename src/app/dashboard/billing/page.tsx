"use client";

import { motion } from "framer-motion";
import { CreditCard, Check, Download, TrendingUp } from "lucide-react";

const billingHistory = [
  { id: "inv-001", date: "May 15, 2026", amount: "$99.00", status: "paid", plan: "Pro Plan (Monthly)" },
  { id: "inv-002", date: "Apr 15, 2026", amount: "$99.00", status: "paid", plan: "Pro Plan (Monthly)" },
  { id: "inv-003", date: "Mar 15, 2026", amount: "$99.00", status: "paid", plan: "Pro Plan (Monthly)" },
];

const usageStats = [
  { name: "AKS CPU Hours", used: "4,250", limit: "10,000", unit: "hrs", percent: 42.5, color: "bg-primary" },
  { name: "Bandwidth Egress", used: "324.5", limit: "500", unit: "GB", percent: 64.9, color: "bg-accent" },
  { name: "Container Deployments", used: "78", limit: "200", unit: "builds", percent: 39, color: "bg-success" },
  { name: "AI Autopilot Actions", used: "2,450", limit: "5,000", unit: "actions", percent: 49, color: "bg-info" },
];

export default function BillingPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Billing & Usage</h1>
        <p className="text-foreground-muted text-sm mt-1">
          Manage your subscription plans, payment details, and track real-time resource utilization.
        </p>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Subscription Details + Usage */}
        <div className="lg:col-span-2 space-y-6">
          {/* Active Plan Card */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass rounded-xl p-6 relative overflow-hidden"
          >
            <div className="absolute top-0 right-0 w-32 h-32 bg-primary/10 rounded-full blur-3xl pointer-events-none" />
            
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <span className="text-xs px-2.5 py-1 rounded-full bg-primary-subtle text-primary font-medium tracking-wide">
                  CURRENT SUBSCRIPTION
                </span>
                <h3 className="text-3xl font-extrabold text-foreground mt-3">Pro Plan</h3>
                <p className="text-foreground-muted text-sm mt-1">For production clusters and growing engineering teams.</p>
              </div>
              <div className="text-left sm:text-right">
                <p className="text-3xl font-extrabold text-foreground">$99<span className="text-sm font-medium text-foreground-muted">/month</span></p>
                <p className="text-xs text-foreground-muted mt-1">Next renewal: June 15, 2026</p>
              </div>
            </div>

            <div className="border-t border-border/50 my-5" />

            <div className="grid md:grid-cols-3 gap-4">
              {["Unlimited Deployments", "5 Active AKS Clusters", "Autonomous AI Copilot"].map((feature) => (
                <div key={feature} className="flex items-center gap-2 text-sm text-foreground-muted">
                  <div className="w-5 h-5 rounded-full bg-success/15 flex items-center justify-center flex-shrink-0">
                    <Check size={12} className="text-success" />
                  </div>
                  <span>{feature}</span>
                </div>
              ))}
            </div>

            <div className="mt-6 flex flex-wrap gap-3">
              <button className="px-4 py-2 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-xl transition glow-blue">
                Change Plan
              </button>
              <button className="px-4 py-2 glass hover:bg-card-hover text-foreground text-xs font-semibold rounded-xl transition">
                Cancel Subscription
              </button>
            </div>
          </motion.div>

          {/* Usage Meter Card */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="glass rounded-xl p-6"
          >
            <h3 className="font-semibold text-lg mb-6 flex items-center gap-2">
              <TrendingUp size={20} className="text-primary" />
              Monthly Resource Usage
            </h3>

            <div className="grid md:grid-cols-2 gap-6">
              {usageStats.map((stat) => (
                <div key={stat.name} className="space-y-2">
                  <div className="flex justify-between text-xs font-medium">
                    <span className="text-foreground-muted">{stat.name}</span>
                    <span className="text-foreground">
                      {stat.used} / {stat.limit} {stat.unit}
                    </span>
                  </div>
                  <div className="h-2 bg-card rounded-full overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${stat.percent}%` }}
                      transition={{ duration: 1, delay: 0.3 }}
                      className={`h-full rounded-full ${stat.color}`}
                    />
                  </div>
                  <p className="text-[10px] text-foreground-muted text-right">{stat.percent}% Consumed</p>
                </div>
              ))}
            </div>
          </motion.div>
        </div>

        {/* Right Col: Credit Card Mock + Invoices */}
        <div className="space-y-6">
          {/* Credit Card Mock */}
          <motion.div
            initial={{ opacity: 0, x: 15 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2 }}
            className="rounded-2xl p-5 bg-gradient-to-br from-primary via-accent to-purple-800 text-white relative overflow-hidden shadow-2xl h-48 flex flex-col justify-between"
          >
            {/* Hologram chip */}
            <div className="absolute top-5 right-5 w-12 h-8 bg-white/20 rounded-md border border-white/30 backdrop-blur-md flex items-center justify-center font-bold text-xs uppercase tracking-widest text-white/50">
              ZeroOps
            </div>
            
            <div>
              <CreditCard size={32} className="text-white/80" />
              <p className="mt-6 text-lg font-mono tracking-widest">••••  ••••  ••••  4829</p>
            </div>
            
            <div className="flex justify-between items-end">
              <div>
                <p className="text-[9px] text-white/60 uppercase">Card Holder</p>
                <p className="text-sm font-semibold tracking-wide">Vedant S.</p>
              </div>
              <div>
                <p className="text-[9px] text-white/60 uppercase">Expires</p>
                <p className="text-sm font-semibold tracking-wide">12/30</p>
              </div>
            </div>
          </motion.div>

          {/* Invoices List */}
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="glass rounded-xl p-5"
          >
            <h3 className="font-semibold text-sm mb-4">Billing History</h3>
            <div className="space-y-3">
              {billingHistory.map((invoice) => (
                <div key={invoice.id} className="flex items-center justify-between p-3 rounded-lg bg-card/45 hover:bg-card-hover/40 transition">
                  <div>
                    <p className="text-xs font-semibold text-foreground">{invoice.plan}</p>
                    <p className="text-[10px] text-foreground-muted">{invoice.date}</p>
                  </div>
                  <div className="text-right flex items-center gap-3">
                    <div>
                      <p className="text-xs font-bold text-foreground">{invoice.amount}</p>
                      <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-success/15 text-success font-medium uppercase">
                        {invoice.status}
                      </span>
                    </div>
                    <button className="p-1.5 hover:bg-card-hover rounded text-foreground-muted hover:text-foreground">
                      <Download size={14} />
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
