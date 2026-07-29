import type { Project } from "@/lib/api";

type ProjectSelectorProps = {
  projects: Project[];
  value: string;
  onChange: (projectId: string) => void;
  label?: string;
  className?: string;
};

export function ProjectSelector({
  projects,
  value,
  onChange,
  label = "Project",
  className,
}: ProjectSelectorProps) {
  return (
    <label className={className}>
      <span className="mb-1.5 block text-xs font-medium text-foreground-muted">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-11 w-full rounded-lg border border-border bg-card px-3 text-sm font-medium text-foreground outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/15"
      >
        {projects.map((project) => (
          <option key={project.id} value={project.id}>
            {project.name} · {project.branch || "default branch"}
          </option>
        ))}
      </select>
    </label>
  );
}
