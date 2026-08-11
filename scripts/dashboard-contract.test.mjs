import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function readProjectFile(relativePath) {
  return readFileSync(join(projectRoot, relativePath), "utf8");
}

function sourceFilesUnder(relativeDirectory) {
  const directory = join(projectRoot, relativeDirectory);
  const files = [];

  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const absolutePath = join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(
        ...sourceFilesUnder(relative(projectRoot, absolutePath)),
      );
    } else if (/\.(?:ts|tsx)$/.test(entry.name)) {
      files.push(relative(projectRoot, absolutePath).replaceAll("\\", "/"));
    }
  }

  return files;
}

const dashboardFiles = [
  ...sourceFilesUnder("src/app/dashboard"),
  ...sourceFilesUnder("src/components/dashboard"),
];
const dashboardSources = new Map(
  dashboardFiles.map((file) => [file, readProjectFile(file)]),
);
const dashboardSource = [...dashboardSources.entries()]
  .map(([file, source]) => `// ${file}\n${source}`)
  .join("\n");

test("dashboard source does not synthesize operational fixtures", () => {
  for (const [file, source] of dashboardSources) {
    assert.doesNotMatch(
      source,
      /\bMath\.random\s*\(/,
      `${file} must not generate dashboard values with Math.random().`,
    );
    assert.doesNotMatch(
      source,
      /\b(?:mock|fake|demo)(?:Data|Metrics|Stats|Projects|Deployments|Incidents|Alerts|Notifications|Logs|Activity|Telemetry|Series|ChartData)\b/i,
      `${file} must not declare mock, fake, or demo operational fixtures.`,
    );
  }

  assert.doesNotMatch(
    dashboardSource,
    /\b(?:security_score|cost_estimate|performance_score|reliability_score|estimated_deploy_time|estimated_cost|expected_traffic|pricing_breakdown)\b/,
    "Generated estimates and synthetic scores must not be presented as recorded dashboard telemetry.",
  );
});

test("overview derives release state from deployment records, not project lifecycle state", () => {
  const source = readProjectFile("src/app/dashboard/page.tsx");
  const successfulStatuses = source.match(
    /const\s+successfulStatuses\s*=\s*new Set\(\[([^\]]*)\]\)/,
  );

  assert.ok(successfulStatuses, "The overview must keep an explicit successful deployment status allowlist.");
  assert.deepEqual(
    [...successfulStatuses[1].matchAll(/["'`]([^"'`]+)["'`]/g)].map(
      (match) => match[1],
    ),
    ["running"],
    "Only a recorded running deployment may receive the positive release treatment.",
  );

  const stateCall = source.match(/const\s+state\s*=\s*projectState\(([\s\S]*?)\);/);
  assert.ok(stateCall, "The overview must derive each project presentation from a recorded release state.");
  assert.doesNotMatch(
    stateCall[1],
    /\bproject\.status\b/,
    "Project.status is a lifecycle field and must not be treated as release health.",
  );
  assert.match(source, /This is not a health signal\./);
  assert.doesNotMatch(
    source,
    /\b(?:healthy release|all systems (?:healthy|operational)|all clear|you(?:'|’)re up to date)\b/i,
    "The overview must not claim an all-clear state without explicit health evidence.",
  );
});

test("workspace API availability is distinct from empty data", () => {
  const context = readProjectFile("src/lib/NotificationContext.tsx");
  const topBar = readProjectFile("src/components/dashboard/TopBar.tsx");

  assert.match(
    context,
    /export type WorkspaceDataState = "idle" \| "loading" \| "ready" \| "error";/,
  );
  assert.match(context, /Promise\.allSettled\s*\(/);

  for (const resource of ["Notifications", "Projects", "DashboardStats"]) {
    assert.match(context, new RegExp(`set${resource}State\\(\"loading\"\\)`));
    assert.match(context, new RegExp(`set${resource}State\\(\"ready\"\\)`));
    assert.match(context, new RegExp(`set${resource}State\\(\"error\"\\)`));
  }

  for (const state of [
    "notificationsState",
    "projectsState",
    "dashboardStatsState",
  ]) {
    assert.match(
      context,
      new RegExp(`${state}: WorkspaceDataState`),
      `${state} must be part of the public workspace context contract.`,
    );
    assert.match(
      context,
      new RegExp(`\\n\\s*${state},`),
      `${state} must be exposed by NotificationProvider.`,
    );
  }

  const loadingIndex = topBar.indexOf('notificationsState === "loading"');
  const errorIndex = topBar.indexOf('notificationsState === "error"');
  const emptyIndex = topBar.indexOf("notifications.length === 0");
  assert.ok(
    loadingIndex >= 0 && loadingIndex < errorIndex && errorIndex < emptyIndex,
    "TopBar must resolve loading and API failure before rendering a true empty state.",
  );
  assert.match(topBar.slice(loadingIndex, errorIndex), /role="status"/);
  assert.match(topBar.slice(errorIndex, emptyIndex), /role="alert"/);
  assert.match(topBar.slice(errorIndex, emptyIndex), /refreshNotifications/);
  assert.doesNotMatch(topBar, /up to date/i);
});

test("API-driven dashboard pages retain semantic loading, error, and empty states", () => {
  const pagesWithAllThreeStates = [
    "src/app/dashboard/page.tsx",
    "src/app/dashboard/projects/page.tsx",
    "src/app/dashboard/activity/page.tsx",
    "src/app/dashboard/ai-analysis/page.tsx",
    "src/app/dashboard/ai-analysis/history/page.tsx",
    "src/app/dashboard/billing/page.tsx",
    "src/app/dashboard/deployments/page.tsx",
    "src/app/dashboard/incidents/page.tsx",
    "src/app/dashboard/logs/page.tsx",
    "src/app/dashboard/monitoring/page.tsx",
    "src/app/dashboard/security/page.tsx",
    "src/app/dashboard/settings/page.tsx",
  ];

  for (const file of pagesWithAllThreeStates) {
    const source = readProjectFile(file);
    assert.match(
      source,
      /role="status"|aria-busy/,
      `${file} needs a semantic loading state.`,
    );
    assert.match(
      source,
      /<StatePanel\b/,
      `${file} needs a shared empty or unavailable state.`,
    );
    assert.match(
      source,
      /variant="error"/,
      `${file} needs an explicit error state rather than empty-state copy.`,
    );
  }

  const statePanel = readProjectFile("src/components/ui/StatePanel.tsx");
  assert.match(
    statePanel,
    /role=\{variant === "error" \? "alert" : variant === "success" \? "status" : undefined\}/,
    "The shared state component must announce failures and success semantically.",
  );

  const routeLoading = readProjectFile("src/app/dashboard/loading.tsx");
  assert.match(routeLoading, /role="status"/);
  assert.match(routeLoading, /Loading workspace/);
});

test("dashboard motion and shared control contracts remain accessible", () => {
  const globalStyles = readProjectFile("src/app/globals.css");
  assert.match(globalStyles, /@media\s*\(prefers-reduced-motion:\s*reduce\)/);
  assert.match(
    globalStyles,
    /\.ops-primary,[\s\S]*?\.ops-danger\s*\{[\s\S]*?min-height:\s*44px;/,
  );
  assert.match(
    globalStyles,
    /\.ops-input\s*\{[\s\S]*?min-height:\s*44px;/,
  );

  const sharedControlFiles = [
    "src/components/dashboard/TopBar.tsx",
    "src/components/dashboard/Sidebar.tsx",
    "src/components/dashboard/ProjectTabs.tsx",
    "src/components/dashboard/ProjectSelector.tsx",
    "src/components/ui/StatePanel.tsx",
  ];
  const sharedControlSource = sharedControlFiles
    .map((file) => readProjectFile(file))
    .join("\n");
  assert.doesNotMatch(
    sharedControlSource,
    /\bmin-h-(?:[1-9]|10)\b/,
    "Shared interactive controls must not use a target height below 44px.",
  );
  assert.match(readProjectFile("src/components/dashboard/TopBar.tsx"), /min-h-11/);
  assert.match(readProjectFile("src/components/dashboard/Sidebar.tsx"), /min-h-11/);
  assert.match(readProjectFile("src/components/dashboard/ProjectTabs.tsx"), /min-h-11/);
  assert.match(readProjectFile("src/components/dashboard/ProjectSelector.tsx"), /ops-input/);
  assert.match(readProjectFile("src/components/ui/StatePanel.tsx"), /ops-secondary/);

  const motionFiles = [
    "src/components/dashboard/DecisionIntelligencePanel.tsx",
    "src/components/dashboard/InfrastructurePlan.tsx",
    "src/components/dashboard/Sidebar.tsx",
    "src/components/dashboard/pipeline/PipelineTimeline.tsx",
    "src/app/dashboard/loading.tsx",
  ];
  for (const file of motionFiles) {
    const lines = readProjectFile(file).split(/\r?\n/);
    for (const [index, line] of lines.entries()) {
      if (/\banimate-(?:spin|pulse|bounce)\b/.test(line)) {
        assert.match(
          line,
          /motion-reduce:animate-none/,
          `${file}:${index + 1} needs a reduced-motion animation fallback.`,
        );
      }
      if (/\btransition-(?:transform|\[transform)/.test(line)) {
        assert.match(
          line,
          /motion-reduce:transition-none/,
          `${file}:${index + 1} needs a reduced-motion transition fallback.`,
        );
      }
    }
  }
});
