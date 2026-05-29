"use client";

import { motion } from "framer-motion";
import {
  ArrowLeft,
  Brain,
  Calendar,
  ChevronDown,
  ChevronUp,
  Clock,
  Cpu,
  Database,
  HardDrive,
  Loader2,
  Shield,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { GaugeChart } from "@/components/ui/GaugeChart";
import { useNotifications } from "@/lib/NotificationContext";
import { api, type AIAnalysis } from "@/lib/api";

export default function AIAnalysisHistoryPage() {
  const router = useRouter();
  const { projects } = useNotifications();
  const [analyses, setAnalyses] = useState<AIAnalysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<string>("");

  // Default to first project
  useEffect(() => {
    if (projects.length > 0 && !selectedProject) {
      setSelectedProject(projects[0].id);
    }
  }, [projects, selectedProject]);

  // Fetch history when project changes
  useEffect(() => {
    if (!selectedProject) return;
    setLoading(true);
    api
      .getAIAnalysisHistory(selectedProject)
      .then((data) => setAnalyses(data))
      .catch(() => setAnalyses([]))
      .finally(() => setLoading(false));
  }, [selectedProject]);

  const formatDate = (iso: string | null) => {
    if (!iso) return "Unknown";
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const riskColor = (score: number) => {
    if (score <= 20) return "text-success";
    if (score <= 50) return "text-warning";
    return "text-error";
  };

  const riskLabel = (score: number) => {
    if (score <= 20) return "Low Risk";
    if (score <= 50) return "Medium Risk";
    return "High Risk";
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/dashboard/ai-analysis")}
            className="flex items-center gap-1.5 text-sm text-foreground-muted hover:text-foreground transition-colors cursor-pointer"
          >
            <ArrowLeft size={16} />
            Back
          </button>
          <div className="h-5 w-px bg-border" />
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-subtle border border-primary/20">
              <Clock size={18} className="text-primary" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-foreground">
                Scan History
              </h1>
              <p className="text-[11px] text-foreground-muted">
                Chronological AI analysis timeline
              </p>
            </div>
          </div>
        </div>

        {projects.length > 0 && (
          <select
            value={selectedProject}
            onChange={(e) => setSelectedProject(e.target.value)}
            className="rounded-xl border border-border bg-card px-3 py-2 text-sm text-foreground outline-none focus:border-primary cursor-pointer shadow-sm"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.full_name}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center min-h-[300px]">
          <Loader2 className="animate-spin text-primary" size={24} />
        </div>
      ) : analyses.length === 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col items-center justify-center min-h-[400px] bg-card border border-border rounded-xl p-12 shadow-sm"
        >
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary-subtle border border-primary/20 mb-4">
            <Brain size={32} className="text-primary" />
          </div>
          <h3 className="text-lg font-bold text-foreground mb-2">
            No Analyses Yet
          </h3>
          <p className="text-sm text-foreground-muted text-center max-w-md">
            Run an AI analysis on your project from the{" "}
            <button
              onClick={() => router.push("/dashboard/ai-analysis")}
              className="text-primary hover:underline cursor-pointer"
            >
              AI Analysis page
            </button>{" "}
            to see results here.
          </p>
        </motion.div>
      ) : (
        <div className="space-y-4">
          {/* Summary bar */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="grid grid-cols-2 sm:grid-cols-4 gap-3"
          >
            {[
              {
                label: "Total Scans",
                value: analyses.length,
                icon: Brain,
                color: "text-primary",
              },
              {
                label: "Latest Framework",
                value: analyses[0]?.framework || "—",
                icon: Cpu,
                color: "text-accent",
              },
              {
                label: "Latest Risk",
                value: `${analyses[0]?.risk_score ?? 0}/100`,
                icon: Shield,
                color: riskColor(analyses[0]?.risk_score ?? 0),
              },
              {
                label: "Latest Confidence",
                value: `${analyses[0]?.confidence ?? 0}%`,
                icon: Database,
                color: "text-success",
              },
            ].map((stat, i) => (
              <motion.div
                key={stat.label}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
                className="bg-card border border-border rounded-xl p-4 shadow-sm"
              >
                <stat.icon size={18} className={`mb-2 ${stat.color}`} />
                <p className="text-xl font-bold text-foreground">
                  {stat.value}
                </p>
                <p className="text-[10px] text-foreground-muted uppercase tracking-wider font-bold mt-0.5">
                  {stat.label}
                </p>
              </motion.div>
            ))}
          </motion.div>

          {/* Timeline */}
          <div className="relative">
            {/* Timeline line */}
            <div className="absolute left-6 top-0 bottom-0 w-px bg-border hidden sm:block" />

            {analyses.map((a, index) => {
              const isExpanded = expandedId === a.id;
              return (
                <motion.div
                  key={a.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.05 }}
                  className="relative sm:pl-14 mb-4"
                >
                  {/* Timeline dot */}
                  <div className="absolute left-4 top-5 hidden sm:flex h-5 w-5 items-center justify-center rounded-full bg-primary border-2 border-card z-10">
                    <div className="h-2 w-2 rounded-full bg-white" />
                  </div>

                  <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
                    {/* Header row — always visible */}
                    <button
                      onClick={() =>
                        setExpandedId(isExpanded ? null : a.id)
                      }
                      className="w-full flex items-center gap-4 p-4 hover:bg-card-hover transition-colors text-left cursor-pointer"
                    >
                      <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-primary-subtle border border-primary/20">
                        <Brain size={18} className="text-primary" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-foreground text-sm">
                            {a.framework}{" "}
                            {a.framework_version
                              ? `v${a.framework_version}`
                              : ""}
                          </span>
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-background-secondary border border-border/60 text-foreground-muted">
                            {a.language}
                          </span>
                          {index === 0 && (
                            <span className="text-[9px] font-bold uppercase px-2 py-0.5 rounded-full bg-primary/10 border border-primary/20 text-primary tracking-wider">
                              Latest
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 mt-1 text-[11px] text-foreground-muted">
                          <span className="flex items-center gap-1">
                            <Calendar size={11} />
                            {formatDate(a.created_at)}
                          </span>
                          <span className={`font-semibold ${riskColor(a.risk_score)}`}>
                            {riskLabel(a.risk_score)} ({a.risk_score}/100)
                          </span>
                          <span className="text-success font-semibold">
                            {a.confidence}% confidence
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="hidden md:flex items-center gap-2 text-[10px] text-foreground-muted">
                          <span className="bg-background-secondary px-2 py-0.5 rounded border border-border/60 font-mono">
                            {a.cpu_recommendation || "—"}
                          </span>
                          <span className="bg-background-secondary px-2 py-0.5 rounded border border-border/60 font-mono">
                            {a.memory_recommendation || "—"}
                          </span>
                        </div>
                        {isExpanded ? (
                          <ChevronUp
                            size={16}
                            className="text-foreground-muted"
                          />
                        ) : (
                          <ChevronDown
                            size={16}
                            className="text-foreground-muted"
                          />
                        )}
                      </div>
                    </button>

                    {/* Expanded details */}
                    {isExpanded && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        className="border-t border-border p-5 space-y-5"
                      >
                        {/* Resource cards */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                          {[
                            {
                              icon: Cpu,
                              label: "CPU",
                              value: a.cpu_recommendation || "200m",
                            },
                            {
                              icon: HardDrive,
                              label: "Memory",
                              value: a.memory_recommendation || "256Mi",
                            },
                            {
                              icon: Database,
                              label: "Storage",
                              value: a.storage_recommendation || "1Gi",
                            },
                          ].map((r) => (
                            <div
                              key={r.label}
                              className="bg-background-secondary/50 border border-border/40 rounded-lg p-3 text-center"
                            >
                              <r.icon
                                size={16}
                                className="mx-auto mb-1 text-primary"
                              />
                              <p className="text-lg font-bold text-foreground">
                                {r.value}
                              </p>
                              <p className="text-[10px] text-foreground-muted">
                                {r.label}
                              </p>
                            </div>
                          ))}
                          <div className="bg-background-secondary/50 border border-border/40 rounded-lg p-3 flex flex-col items-center justify-center">
                            <GaugeChart
                              value={a.risk_score}
                              label="Risk"
                              size={60}
                              color="hsl(142, 60%, 40%)"
                            />
                          </div>
                        </div>

                        {/* Build details */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                          {[
                            {
                              label: "Runtime",
                              value: a.runtime || "—",
                            },
                            {
                              label: "Package Manager",
                              value: a.package_manager || "—",
                            },
                            {
                              label: "Deploy Target",
                              value: a.deployment_strategy || "—",
                            },
                            {
                              label: "Docker",
                              value: a.docker_support
                                ? "Yes"
                                : "No",
                            },
                          ].map((d) => (
                            <div
                              key={d.label}
                              className="bg-background-secondary/40 p-2.5 rounded border border-border/40"
                            >
                              <p className="text-[9px] uppercase font-bold text-foreground-muted">
                                {d.label}
                              </p>
                              <p className="mt-0.5 font-semibold text-foreground font-mono text-[11px]">
                                {d.value}
                              </p>
                            </div>
                          ))}
                        </div>

                        {/* Dependencies */}
                        {a.dependencies && a.dependencies.length > 0 && (
                          <div>
                            <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider mb-2">
                              Dependencies
                            </h4>
                            <div className="flex flex-wrap gap-1.5">
                              {a.dependencies.map((dep) => (
                                <span
                                  key={dep}
                                  className="text-[10px] font-mono px-2 py-0.5 rounded bg-background-secondary border border-border/60 text-foreground"
                                >
                                  {dep}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Vulnerabilities */}
                        {a.vulnerabilities &&
                          a.vulnerabilities.length > 0 && (
                            <div>
                              <h4 className="text-xs font-bold text-foreground-muted uppercase tracking-wider mb-2">
                                Security Recommendations
                              </h4>
                              <div className="space-y-1.5">
                                {a.vulnerabilities.map((v) => (
                                  <div
                                    key={v}
                                    className="rounded-lg border border-warning/20 bg-warning/5 p-2.5 text-[11px] text-foreground-muted"
                                  >
                                    {v}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                      </motion.div>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
