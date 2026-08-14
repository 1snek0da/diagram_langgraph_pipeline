const ROUTES = new Set(["workspace", "analysis", "workflow", "market", "report", "history"]);

export function routeFromLocation(location = window.location) {
  const requested = location.pathname.replace(/^\/+|\/+$/g, "").split("/")[0];
  const page = ROUTES.has(requested) ? requested : "workspace";
  return { page, runId: new URLSearchParams(location.search).get("run_id") };
}

export function routePath(page, runId = null) {
  if (!ROUTES.has(page)) throw new Error(`Unknown page: ${page}`);
  const query = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  return `/${page}${query}`;
}

export function navigateTo(page, runId = null, { replace = false } = {}) {
  const path = routePath(page, runId);
  window.history[replace ? "replaceState" : "pushState"]({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
  return path;
}

