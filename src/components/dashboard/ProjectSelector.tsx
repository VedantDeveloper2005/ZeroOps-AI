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
        className="ops-input font-medium"
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
