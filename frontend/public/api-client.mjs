const DEFAULT_BASE_URL = "/api/v1";

export class ApiClientError extends Error {
  constructor({ code, message, retryable = false, status = 0 }) {
    super(message);
    this.name = "ApiClientError";
    this.code = code;
    this.retryable = retryable;
    this.status = status;
  }
}

async function request(baseUrl, path, options = {}) {
  let response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...options,
      headers: { Accept: "application/json", ...options.headers },
    });
  } catch (_error) {
    throw new ApiClientError({
      code: "API_UNAVAILABLE",
      message: "分析服务暂时无法访问，请稍后重试。",
      retryable: true,
    });
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.error;
    throw new ApiClientError({
      code: detail?.code || "REQUEST_FAILED",
      message: detail?.message || "分析服务请求失败。",
      retryable: Boolean(detail?.retryable),
      status: response.status,
    });
  }
  return payload;
}

function jsonRequest(baseUrl, path, body) {
  return request(baseUrl, path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function createApiClient(baseUrl = DEFAULT_BASE_URL) {
  const normalizedBaseUrl = baseUrl.replace(/\/$/, "");
  return {
    health: () => request(normalizedBaseUrl, "/health"),
    taskTypes: () => request(normalizedBaseUrl, "/task-types"),
    createRun: (body) => jsonRequest(normalizedBaseUrl, "/analysis-runs", body),
    listRuns: (filters = {}) => {
      const query = new URLSearchParams();
      for (const [key, value] of Object.entries(filters)) {
        if (value !== undefined && value !== null && value !== "") query.set(key, value);
      }
      const suffix = query.toString() ? `?${query}` : "";
      return request(normalizedBaseUrl, `/analysis-runs${suffix}`);
    },
    getRun: (runId) => request(normalizedBaseUrl, `/analysis-runs/${encodeURIComponent(runId)}`),
    getNodes: (runId) => request(normalizedBaseUrl, `/analysis-runs/${encodeURIComponent(runId)}/nodes`),
    getReport: (runId) => request(normalizedBaseUrl, `/analysis-runs/${encodeURIComponent(runId)}/report`),
    getMarketBars: ({ ticker, startDate, endDate } = {}) => {
      const query = new URLSearchParams({ ticker });
      if (startDate) query.set("start_date", startDate);
      if (endDate) query.set("end_date", endDate);
      return request(normalizedBaseUrl, `/market-bars?${query}`);
    },
  };
}

