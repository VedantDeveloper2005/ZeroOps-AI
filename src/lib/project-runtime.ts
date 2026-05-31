export const DEFAULT_PROJECT_ID = "web-app";

export function normalizeProjectId(repo: string) {
  const basename = repo.split("/").pop() || repo || DEFAULT_PROJECT_ID;
  return (
    basename
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || DEFAULT_PROJECT_ID
  );
}

export function namespaceForProject(projectId: string) {
  return `zeroops-${normalizeProjectId(projectId)}`;
}

export const deploymentStageLabels = [
  "Repository Connected",
  "Analyzing Code",
  "Preparing Build",
  "Installing Dependencies",
  "Building Application",
  "Provisioning Infrastructure",
  "Configuring SSL",
  "Running Health Checks",
  "Application Live",
];
