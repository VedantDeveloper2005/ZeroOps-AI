"use client";

import { GitBranch, Brain, Cloud, Database, Globe } from "lucide-react";

interface ArchitectureDiagramProps {
  repo: string;
  branch: string;
  framework: string;
  runtime: string;
  database: string;
  liveUrl: string;
}

export function ArchitectureDiagram({ 
  repo, 
  branch, 
  framework, 
  runtime, 
  database, 
  liveUrl 
}: ArchitectureDiagramProps) {
  const showDb = database && database.toLowerCase() !== "none" && database.toLowerCase() !== "undefined";
  
  return (
    <div className="relative w-full bg-zinc-950/40 border border-border/40 rounded-2xl p-6 overflow-hidden shadow-inner">
      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-accent/5 to-transparent pointer-events-none" />
      
      {/* Node Layout Grid */}
      <div className="relative flex flex-col md:flex-row items-center justify-between gap-8 md:gap-4 py-8 z-10">
        
        {/* Node 1: Source */}
        <div className="flex flex-col items-center text-center space-y-2 min-w-[120px]">
          <div className="w-14 h-14 rounded-2xl bg-zinc-900 border border-border/80 flex items-center justify-center shadow-lg glow-blue group cursor-default">
            <GitBranch size={24} className="text-foreground-muted group-hover:text-primary transition-colors" />
          </div>
          <div>
            <p className="text-[11px] font-bold text-foreground truncate max-w-[120px]">{repo.split("/").pop() || repo}</p>
            <p className="text-[9px] font-mono text-foreground-muted">git: {branch}</p>
          </div>
        </div>

        {/* Connector 1 */}
        <div className="hidden md:block flex-1 h-0.5 max-w-[60px] bg-gradient-to-r from-primary to-accent relative overflow-hidden">
          <div className="absolute inset-0 bg-white/40 w-1/2 h-full animate-[shimmer_1.5s_infinite] bg-gradient-to-r from-transparent via-white/40 to-transparent" />
        </div>

        {/* Node 2: ZeroOps Builder */}
        <div className="flex flex-col items-center text-center space-y-2 min-w-[120px]">
          <div className="w-14 h-14 rounded-2xl bg-primary/10 border border-primary/30 flex items-center justify-center shadow-lg glow-blue group cursor-default">
            <Brain size={24} className="text-primary animate-pulse" />
          </div>
          <div>
            <p className="text-[11px] font-bold text-foreground">ZeroOps Builder</p>
            <p className="text-[9px] text-foreground-muted">Build & Containerize</p>
          </div>
        </div>

        {/* Connector 2 */}
        <div className="hidden md:block flex-1 h-0.5 max-w-[60px] bg-gradient-to-r from-accent to-success relative overflow-hidden">
          <div className="absolute inset-0 bg-white/40 w-1/2 h-full animate-[shimmer_1.5s_infinite] bg-gradient-to-r from-transparent via-white/40 to-transparent" />
        </div>

        {/* Node 3: Cloud Target */}
        <div className="flex flex-col items-center text-center space-y-2 min-w-[120px] relative">
          <div className="w-14 h-14 rounded-2xl bg-success/10 border border-success/30 flex items-center justify-center shadow-lg glow-green group cursor-default">
            <Cloud size={24} className="text-success" />
          </div>
          <div>
            <p className="text-[11px] font-bold text-foreground">Azure App Service</p>
            <p className="text-[9px] text-foreground-muted">{framework} ({runtime})</p>
          </div>
        </div>

        {/* Connector 3 */}
        <div className="hidden md:block flex-1 h-0.5 max-w-[60px] bg-gradient-to-r from-success to-primary relative overflow-hidden">
          <div className="absolute inset-0 bg-white/40 w-1/2 h-full animate-[shimmer_1.5s_infinite] bg-gradient-to-r from-transparent via-white/40 to-transparent" />
        </div>

        {/* Node 4: Endpoint (Live URL) */}
        <div className="flex flex-col items-center text-center space-y-2 min-w-[120px]">
          <a href={liveUrl} target="_blank" rel="noopener noreferrer" className="w-14 h-14 rounded-2xl bg-zinc-900 border border-border/80 hover:border-primary/50 transition-all flex items-center justify-center shadow-lg glow-blue group">
            <Globe size={24} className="text-primary group-hover:scale-105 transition-transform" />
          </a>
          <div>
            <p className="text-[11px] font-bold text-foreground">Production Ingress</p>
            <p className="text-[9px] font-mono text-primary truncate max-w-[120px]">{liveUrl.replace("https://", "")}</p>
          </div>
        </div>
      </div>

      {/* Database Node (rendered on a lower level for full-diagram representation) */}
      {showDb && (
        <div className="relative md:-mt-6 flex flex-col items-center justify-center z-10">
          {/* Connector down to DB */}
          <div className="hidden md:block w-0.5 h-8 bg-gradient-to-b from-success to-purple-500 relative overflow-hidden mb-2">
            <div className="absolute inset-0 bg-white/40 w-full h-1/2 animate-[shimmer_1.5s_infinite]" />
          </div>
          
          <div className="flex flex-col items-center text-center space-y-2 min-w-[120px]">
            <div className="w-14 h-14 rounded-2xl bg-purple-500/10 border border-purple-500/30 flex items-center justify-center shadow-lg glow-purple group cursor-default">
              <Database size={24} className="text-purple-400" />
            </div>
            <div>
              <p className="text-[11px] font-bold text-foreground">Azure Database</p>
              <p className="text-[9px] text-foreground-muted">{database}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
