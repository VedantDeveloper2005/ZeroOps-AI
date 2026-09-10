import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const source = readFileSync(new URL("../src/lib/useProjectSelection.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;

function selectionHarness() {
  let selected = "";
  const previousRequest = { current: undefined };
  let dependencies;
  let effect;
  const exports = {};
  vm.runInNewContext(compiled, {
    exports,
    require: () => ({
      useState: () => [selected, (next) => { selected = typeof next === "function" ? next(selected) : next; }],
      useRef: () => previousRequest,
      useEffect(callback, next) {
        if (!dependencies || next.some((value, index) => !Object.is(value, dependencies[index]))) effect = callback;
        dependencies = next;
      },
    }),
  });
  return {
    render(projects, requested) {
      const [, select] = exports.useProjectSelection(projects, requested);
      effect?.();
      effect = undefined;
      return { selected, select };
    },
  };
}

const projects = [{ id: "a" }, { id: "b" }];

test("a deep-linked project can be changed manually without snapping back on render or refresh", () => {
  const harness = selectionHarness();
  let state = harness.render(projects, "a");
  assert.equal(state.selected, "a");
  state.select("b");
  assert.equal(harness.render(projects, "a").selected, "b");
  assert.equal(harness.render([...projects], "a").selected, "b");
});

test("a changed deep link takes precedence over the previous selection", () => {
  const harness = selectionHarness();
  harness.render(projects, "a");
  assert.equal(harness.render(projects, "b").selected, "b");
});

test("deep links survive initial loading and removed projects fall back to an existing project", () => {
  const harness = selectionHarness();
  assert.equal(harness.render([], "b").selected, "");
  assert.equal(harness.render(projects, "b").selected, "b");
  assert.equal(harness.render([{ id: "a" }], "b").selected, "a");
  assert.equal(harness.render([], "b").selected, "");
});

test("all affected project dashboards share the corrected selection behavior", () => {
  for (const page of ["ai-analysis", "ai-analysis/history", "infrastructure", "monitoring", "incidents", "security", "logs", "settings/pipeline"]) {
    const content = readFileSync(new URL(`../src/app/dashboard/${page}/page.tsx`, import.meta.url), "utf8");
    assert.match(content, /useProjectSelection\(projects, searchParams\.get\("project"\)\)/);
    assert.doesNotMatch(content, /\[projects, searchParams, selectedProjectId\]/);
  }
});

test("pipeline settings resolves missing projects and API errors before showing configuration loading", () => {
  const content = readFileSync(new URL("../src/app/dashboard/settings/pipeline/page.tsx", import.meta.url), "utf8");
  const loadingIndex = content.indexOf('loadState === "idle"');
  assert.ok(content.indexOf('projectsState === "error"') < loadingIndex);
  assert.ok(content.indexOf("projects.length === 0") < loadingIndex);
  assert.match(content, /title="No projects yet"/);
});
