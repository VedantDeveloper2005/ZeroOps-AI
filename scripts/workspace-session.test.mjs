import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const source = readFileSync(new URL("../src/lib/NotificationContext.tsx", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React },
}).outputText;

const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const flush = () => new Promise((resolve) => setImmediate(resolve));

// Exercise the provider's real event handlers and asynchronous state updates with
// deterministic hook storage, without adding a browser/DOM dependency to CI.
function mountWorkspace(api) {
  const slots = [];
  let cursor = 0;
  let pendingEffects = [];
  const sameDeps = (previous, next) => previous && next && previous.length === next.length && previous.every((value, index) => Object.is(value, next[index]));
  const react = {
    createContext: () => ({ Provider: "Provider" }),
    createElement: (_type, props) => props,
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], (value) => { slots[index] = typeof value === "function" ? value(slots[index]) : value; }];
    },
    useRef(initial) {
      const index = cursor++;
      return slots[index] ??= { current: initial };
    },
    useCallback(callback, deps) {
      const index = cursor++;
      if (!sameDeps(slots[index]?.deps, deps)) slots[index] = { callback, deps };
      return slots[index].callback;
    },
    useEffect(effect, deps) {
      const index = cursor++;
      if (!sameDeps(slots[index]?.deps, deps)) {
        slots[index]?.cleanup?.();
        slots[index] = { deps };
        pendingEffects.push(() => { slots[index].cleanup = effect(); });
      }
    },
  };
  const window = new EventTarget();
  const exports = {};
  vm.runInNewContext(compiled, {
    exports,
    window,
    setTimeout,
    require(name) {
      if (name === "react") return { ...react, default: react };
      if (name === "next/navigation") return { usePathname: () => "/dashboard" };
      if (name === "./api") return { api };
      throw new Error(`Unexpected import: ${name}`);
    },
  });
  function snapshot() {
    cursor = 0;
    const { value } = exports.NotificationProvider({ children: null });
    const effects = pendingEffects;
    pendingEffects = [];
    effects.forEach((effect) => effect());
    return value;
  }
  snapshot();
  return {
    snapshot,
    dispatch: (name) => window.dispatchEvent(new Event(name)),
    cleanup: () => slots.forEach((slot) => slot?.cleanup?.()),
  };
}

const oldProject = { id: "old-user-project", deployment_count: 1, last_deployed_at: "2026-09-07", latest_deployment_status: "running" };
const oldNotification = { id: "old-user-notification", read: false };

test("signing out clears all previous workspace data before another account signs in", async () => {
  let unavailable = false;
  const respond = (value) => unavailable ? Promise.reject(new Error("Unavailable")) : Promise.resolve(value);
  const workspace = mountWorkspace({
    getProjects: () => respond([oldProject]),
    getNotifications: () => respond([oldNotification]),
    getDashboardStats: () => respond({ total_projects: 1 }),
  });
  try {
    await flush();
    assert.equal(workspace.snapshot().projects[0].id, oldProject.id);
    workspace.dispatch("zeroops:signed-out");
    let state = workspace.snapshot();
    assert.equal(state.projects.length, 0);
    assert.equal(state.notifications.length, 0);
    assert.equal(state.dashboardStats, null);
    assert.equal(state.hasDeployed, false);
    unavailable = true;
    workspace.dispatch("zeroops:authenticated");
    await flush();
    state = workspace.snapshot();
    assert.equal(state.projects.length, 0);
    assert.equal(state.notifications.length, 0);
    assert.equal(state.dashboardStats, null);
    assert.equal(state.projectsState, "error");
  } finally { workspace.cleanup(); }
});

test("a delayed previous-account load cannot overwrite the newly signed-in workspace", async () => {
  const oldRequest = deferred();
  let newAccount = false;
  const respond = (value) => newAccount ? Promise.resolve(value) : oldRequest.promise;
  const workspace = mountWorkspace({
    getProjects: () => respond([{ ...oldProject, id: "new-user-project" }]),
    getNotifications: () => respond([]),
    getDashboardStats: () => respond({ total_projects: 1 }),
  });
  try {
    workspace.dispatch("zeroops:signed-out");
    newAccount = true;
    workspace.dispatch("zeroops:authenticated");
    await flush();
    oldRequest.resolve([oldProject]);
    await flush();
    const state = workspace.snapshot();
    assert.equal(state.projects[0].id, "new-user-project");
    assert.equal(state.notifications.length, 0);
    assert.equal(state.dashboardStats.total_projects, 1);
  } finally { workspace.cleanup(); }
});

for (const [refresh, resource, stateKey] of [
  ["refreshProjects", "getProjects", "projectsState"],
  ["refreshNotifications", "getNotifications", "notificationsState"],
  ["refreshStats", "getDashboardStats", "dashboardStatsState"],
]) {
  test(`${refresh} ignores pending results and failures after sign-out`, async () => {
    for (const shouldReject of [false, true]) {
      const pending = deferred();
      const api = {
        getProjects: async () => [oldProject],
        getNotifications: async () => [oldNotification],
        getDashboardStats: async () => ({ total_projects: 1 }),
      };
      const workspace = mountWorkspace(api);
      try {
        await flush();
        api[resource] = () => pending.promise;
        const refreshResult = workspace.snapshot()[refresh]();
        workspace.dispatch("zeroops:signed-out");
        if (shouldReject) pending.reject(new Error("Previous session expired"));
        else pending.resolve([oldProject]);
        await refreshResult;
        const state = workspace.snapshot();
        assert.equal(state.projects.length, 0);
        assert.equal(state.notifications.length, 0);
        assert.equal(state.dashboardStats, null);
        assert.equal(state[stateKey], "idle");
      } finally { workspace.cleanup(); }
    }
  });
}
