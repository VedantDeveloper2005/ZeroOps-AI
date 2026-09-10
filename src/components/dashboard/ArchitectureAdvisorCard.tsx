"use client";

import { useState } from "react";
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  Cpu,
  DollarSign,
  ExternalLink,
  FileCode,
  FileText,
  Globe,
  HelpCircle,
  Layers,
  Loader2,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type { ArchitectureRecommendation, CitationEvidence } from "@/lib/api";

type Props = {
  recommendation?: ArchitectureRecommendation;
  onConsult?: () => Promise<void>;
  busy?: boolean;
  disabled?: boolean;
};

export function ArchitectureAdvisorCard({
  recommendation,
  onConsult,
  busy = false,
  disabled = false,
}: Props) {
  const [activeCitationTab, setActiveCitationTab] = useState<
    "all" | "knowledge" | "web" | "repository" | "assumption"
  >("all");

  const citations = recommendation?.evidence_sources ?? [];
  const filteredCitations =
    activeCitationTab === "all"
      ? citations
      : citations.filter((c) => c.source_type === activeCitationTab);

  const knowledgeCount = citations.filter((c) => c.source_type === "knowledge").length;
  const webCount = citations.filter((c) => c.source_type === "web").length;
  const repoCount = citations.filter((c) => c.source_type === "repository").length;
  const assumptionCount = citations.filter((c) => c.source_type === "assumption").length;

  return (
    <section
      aria-labelledby="advisor-panel-heading"
      className="ops-card rounded-2xl border border-primary/20 bg-card p-5 sm:p-6"
    >
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
            <Bot size={22} aria-hidden="true" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2
                id="advisor-panel-heading"
                className="text-base font-semibold tracking-tight text-foreground sm:text-lg"
              >
                Microsoft Foundry Architecture Advisor
              </h2>
              {recommendation?.provenance?.agent_version && (
                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary">
                  v{recommendation.provenance.agent_version}
                </span>
              )}
              {recommendation?.confidence && (
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                    recommendation.confidence === "high"
                      ? "bg-success/15 text-success"
                      : recommendation.confidence === "medium"
                        ? "bg-warning/15 text-warning"
                        : "bg-danger/15 text-danger"
                  }`}
                >
                  {recommendation.confidence.toUpperCase()} CONFIDENCE
                </span>
              )}
            </div>
            <p className="mt-1 text-xs text-foreground-muted">
              Powered by {recommendation?.provenance?.model || "GPT-5.6 Terra"} with server-side
              File Search and Web Search.
            </p>
          </div>
        </div>

        {onConsult && (
          <button
            type="button"
            disabled={busy || disabled}
            onClick={() => void onConsult()}
            className="ops-primary min-h-10 shrink-0 px-4 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? (
              <Loader2 size={14} className="animate-spin motion-reduce:animate-none" aria-hidden="true" />
            ) : (
              <Sparkles size={14} aria-hidden="true" />
            )}
            {busy ? "Consulting Advisor…" : recommendation ? "Re-consult Advisor" : "Consult Foundry Advisor"}
          </button>
        )}
      </div>

      {!recommendation ? (
        <div className="mt-4 rounded-xl border border-dashed border-border bg-background-secondary/30 p-6 text-center">
          <Bot size={28} className="mx-auto text-foreground-muted" aria-hidden="true" />
          <p className="mt-2 text-sm font-semibold text-foreground">
            No Microsoft Foundry recommendation captured for this revision yet
          </p>
          <p className="mt-1 text-xs text-foreground-muted">
            Consult the agent to analyze this repository against ZeroOps architecture rules, Azure
            App Service patterns, and real-time Microsoft documentation.
          </p>
        </div>
      ) : (
        <div className="mt-5 space-y-6">
          {/* Executive Recommendation */}
          <div className="rounded-xl border border-border bg-background p-4 sm:p-5">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-primary">
              Executive Recommendation
            </h3>
            <p className="mt-2 text-sm leading-6 text-foreground">{recommendation.recommendation}</p>

            {/* Provenance Badges */}
            <div className="mt-4 flex flex-wrap items-center gap-2 pt-3 border-t border-border text-[11px] text-foreground-muted">
              <span className="flex items-center gap-1 font-mono">
                <Cpu size={12} aria-hidden="true" /> {recommendation.provenance.model || "GPT-5.6 Terra"}
              </span>
              <span>•</span>
              <span className="flex items-center gap-1">
                <FileText size={12} className={recommendation.provenance.file_search_used ? "text-success" : ""} aria-hidden="true" />
                File Search: {recommendation.provenance.file_search_used ? "Active" : "Inactive"}
              </span>
              <span>•</span>
              <span className="flex items-center gap-1">
                <Globe size={12} className={recommendation.provenance.web_search_used ? "text-success" : ""} aria-hidden="true" />
                Web Search: {recommendation.provenance.web_search_used ? "Active" : "Inactive"}
              </span>
              {recommendation.provenance.latency_ms !== undefined && (
                <>
                  <span>•</span>
                  <span>Latency: {(recommendation.provenance.latency_ms / 1000).toFixed(1)}s</span>
                </>
              )}
            </div>
          </div>

          {/* Component Recommendations */}
          {recommendation.proposed_components.length > 0 && (
            <div>
              <div className="flex items-center gap-2">
                <Layers size={16} className="text-primary" aria-hidden="true" />
                <h3 className="text-sm font-semibold text-foreground">
                  Proposed Azure Components & Allowlist Status
                </h3>
              </div>
              <p className="mt-1 text-xs text-foreground-muted">
                Only components supported by the ZeroOps deployment engine can be provisioned.
                Unsupported recommendations are retained strictly as advisory reference.
              </p>

              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {recommendation.proposed_components.map((comp) => (
                  <article
                    key={comp.id}
                    className={`rounded-xl border p-4 ${
                      comp.deployable
                        ? "border-success/30 bg-background"
                        : "border-warning/30 bg-warning/5"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-foreground-muted">
                          {comp.role}
                        </span>
                        <h4 className="text-sm font-semibold text-foreground">{comp.service}</h4>
                      </div>
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                          comp.deployable
                            ? "bg-success/15 text-success"
                            : "bg-warning/15 text-warning"
                        }`}
                      >
                        {comp.deployable ? "Deployable" : "Advisory Only"}
                      </span>
                    </div>

                    <div className="mt-2 text-xs space-y-1 text-foreground-muted">
                      {comp.proposed_sku && (
                        <p>
                          <strong className="text-foreground">SKU:</strong> {comp.proposed_sku}
                        </p>
                      )}
                      <p className="leading-relaxed">{comp.reason}</p>
                    </div>

                    {!comp.deployable && comp.status_note && (
                      <div className="mt-3 rounded-lg border border-warning/20 bg-warning/10 p-2.5 text-[11px] text-warning-foreground">
                        <span className="font-semibold">Note:</span> {comp.status_note}
                      </div>
                    )}

                    {comp.security_requirements.length > 0 && (
                      <div className="mt-3 border-t border-border pt-2 text-[11px] text-foreground-muted">
                        <span className="font-semibold text-foreground flex items-center gap-1">
                          <ShieldCheck size={12} className="text-primary" aria-hidden="true" />
                          Security:
                        </span>
                        <ul className="mt-1 list-disc pl-4 space-y-0.5">
                          {comp.security_requirements.map((sec, idx) => (
                            <li key={idx}>{sec}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </article>
                ))}
              </div>
            </div>
          )}

          {/* Cost & Operational Considerations */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-xl border border-border bg-background p-4">
              <div className="flex items-center gap-2">
                <DollarSign size={16} className="text-primary" aria-hidden="true" />
                <h3 className="text-sm font-semibold text-foreground">Cost Considerations</h3>
              </div>
              <p className="mt-1 text-xs font-semibold text-foreground">
                Status: {recommendation.cost_status}
              </p>
              {recommendation.cost_considerations.length > 0 ? (
                <ul className="mt-2 list-disc pl-4 space-y-1 text-xs text-foreground-muted">
                  {recommendation.cost_considerations.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-xs text-foreground-muted">
                  Standard App Service Linux tier pricing applies.
                </p>
              )}
            </div>

            <div className="rounded-xl border border-border bg-background p-4">
              <div className="flex items-center gap-2">
                <HelpCircle size={16} className="text-primary" aria-hidden="true" />
                <h3 className="text-sm font-semibold text-foreground">Assumptions & Questions</h3>
              </div>
              {recommendation.assumptions.length > 0 && (
                <div className="mt-2">
                  <span className="text-[11px] font-semibold text-foreground">Assumptions:</span>
                  <ul className="mt-1 list-disc pl-4 space-y-0.5 text-xs text-foreground-muted">
                    {recommendation.assumptions.map((assump, idx) => (
                      <li key={idx}>{assump}</li>
                    ))}
                  </ul>
                </div>
              )}
              {recommendation.missing_information.length > 0 && (
                <div className="mt-3">
                  <span className="text-[11px] font-semibold text-foreground">Missing Info:</span>
                  <ul className="mt-1 list-disc pl-4 space-y-0.5 text-xs text-foreground-muted">
                    {recommendation.missing_information.map((missing, idx) => (
                      <li key={idx}>{missing}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>

          {/* Citations & Evidence Matrix */}
          {citations.length > 0 && (
            <div className="rounded-xl border border-border bg-background p-4">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-foreground">
                    Evidence & Citations Matrix
                  </h3>
                  <p className="text-xs text-foreground-muted">
                    Traceable grounding from ZeroOps internal knowledge, Azure documentation, and
                    repository facts.
                  </p>
                </div>

                <div className="flex flex-wrap gap-1 rounded-lg border border-border bg-card p-1">
                  <button
                    type="button"
                    onClick={() => setActiveCitationTab("all")}
                    className={`rounded px-2 py-1 text-[11px] font-medium transition-colors ${
                      activeCitationTab === "all"
                        ? "bg-primary text-primary-foreground"
                        : "text-foreground-muted hover:text-foreground"
                    }`}
                  >
                    All ({citations.length})
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveCitationTab("knowledge")}
                    className={`rounded px-2 py-1 text-[11px] font-medium transition-colors ${
                      activeCitationTab === "knowledge"
                        ? "bg-primary text-primary-foreground"
                        : "text-foreground-muted hover:text-foreground"
                    }`}
                  >
                    Knowledge ({knowledgeCount})
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveCitationTab("web")}
                    className={`rounded px-2 py-1 text-[11px] font-medium transition-colors ${
                      activeCitationTab === "web"
                        ? "bg-primary text-primary-foreground"
                        : "text-foreground-muted hover:text-foreground"
                    }`}
                  >
                    Web ({webCount})
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveCitationTab("repository")}
                    className={`rounded px-2 py-1 text-[11px] font-medium transition-colors ${
                      activeCitationTab === "repository"
                        ? "bg-primary text-primary-foreground"
                        : "text-foreground-muted hover:text-foreground"
                    }`}
                  >
                    Repo Facts ({repoCount})
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveCitationTab("assumption")}
                    className={`rounded px-2 py-1 text-[11px] font-medium transition-colors ${
                      activeCitationTab === "assumption"
                        ? "bg-primary text-primary-foreground"
                        : "text-foreground-muted hover:text-foreground"
                    }`}
                  >
                    Assumptions ({assumptionCount})
                  </button>
                </div>
              </div>

              <div className="mt-3 divide-y divide-border rounded-lg border border-border">
                {filteredCitations.map((item) => (
                  <div key={item.id} className="p-3 text-xs flex items-start gap-2.5">
                    {item.source_type === "knowledge" && (
                      <FileText size={15} className="shrink-0 text-primary mt-0.5" aria-hidden="true" />
                    )}
                    {item.source_type === "web" && (
                      <Globe size={15} className="shrink-0 text-info mt-0.5" aria-hidden="true" />
                    )}
                    {item.source_type === "repository" && (
                      <FileCode size={15} className="shrink-0 text-success mt-0.5" aria-hidden="true" />
                    )}
                    {item.source_type === "assumption" && (
                      <HelpCircle size={15} className="shrink-0 text-warning mt-0.5" aria-hidden="true" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-foreground">
                          {item.title || item.source_type.toUpperCase()}
                        </span>
                        <span className="rounded bg-background-secondary px-1.5 py-0.5 text-[10px] uppercase font-mono text-foreground-muted">
                          {item.source_type}
                        </span>
                      </div>
                      <p className="mt-1 text-foreground-muted leading-relaxed">{item.citation}</p>
                      {item.url && (
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="mt-1 inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
                        >
                          View source documentation <ExternalLink size={10} aria-hidden="true" />
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
