import type {
  AnalysisStatus,
  ChatMessage,
  ChatResponse,
  ChunkResponse,
  ConfigStatus,
  ConnectionTest,
  ProjectResponse,
  SettingsUpdate,
  TriageEntry,
} from "./types";

export class ApiError extends Error {
  code: string;
  details?: Record<string, unknown> | null;
  constructor(code: string, message: string, details?: Record<string, unknown> | null) {
    super(message);
    this.code = code;
    this.details = details;
  }
}

const DIRECT_BACKEND = "http://127.0.0.1:8000";

function unreachableMessage(): string {
  if (typeof window !== "undefined" && window.location.protocol === "file:") {
    return "This page was opened as a file. Start the app with run.bat / ./run.sh / python run.py and open http://127.0.0.1:8000 instead.";
  }
  return "Could not reach the server. Start the backend (python run.py, or run.bat on Windows), keep that window open, then try again.";
}

/** Same-origin first. If the UI is on a dev server (not the backend itself) and /api is unreachable, try the backend directly. */
async function send(path: string, init?: RequestInit): Promise<Response> {
  let response: Response | null = null;
  try {
    response = await fetch(path, init);
  } catch {
    response = null;
  }
  // A dev-server proxy answers 500/502/503/504 with an empty body when the backend is down.
  const proxyDown = response !== null && [500, 502, 503, 504].includes(response.status) &&
    !(response.headers.get("content-type") ?? "").includes("json");
  if (response && !proxyDown) return response;

  const onBackend = typeof window !== "undefined" && window.location.port === "8000";
  const canFallback = typeof window !== "undefined" && window.location.protocol !== "file:" && !onBackend;
  if (canFallback) {
    try {
      return await fetch(DIRECT_BACKEND + path, init);
    } catch {
      /* fall through to the error below */
    }
  }
  if (response && !proxyDown) return response;
  throw new ApiError("network", unreachableMessage());
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await send(path, init);
  if (!response.ok) {
    let code = "http_error";
    let message = `The server returned an error (${response.status}).`;
    let details: Record<string, unknown> | null = null;
    try {
      const body = await response.json();
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
        details = body.error.details ?? null;
      }
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(code, message, details);
  }
  return (await response.json()) as T;
}

export const api = {
  configStatus: () => request<ConfigStatus>("/api/config/status"),

  createProject(description: string, files: File[]) {
    const form = new FormData();
    form.append("description", description);
    for (const file of files) form.append("files", file);
    return request<ProjectResponse>("/api/projects", { method: "POST", body: form });
  },

  /** Create the sample project with predefined, labelled demo results (works without model keys). */
  createDemo: () => request<ProjectResponse>("/api/demo", { method: "POST" }),

  startAnalysis: (projectId: string) =>
    request<AnalysisStatus>(`/api/projects/${projectId}/analyze`, { method: "POST" }),

  getAnalysis: (projectId: string) => request<AnalysisStatus>(`/api/projects/${projectId}/analysis`),

  chat: (projectId: string, question: string, history: ChatMessage[]) =>
    request<ChatResponse>(`/api/projects/${projectId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history }),
    }),

  getChunk: (projectId: string, chunkId: string) =>
    request<ChunkResponse>(`/api/projects/${projectId}/chunks/${encodeURIComponent(chunkId)}`),

  getTriage: (projectId: string) => request<Record<string, TriageEntry>>(`/api/projects/${projectId}/triage`),

  setTriage: (projectId: string, findingId: string, entry: TriageEntry) =>
    request<TriageEntry>(`/api/projects/${projectId}/triage/${encodeURIComponent(findingId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(entry),
    }),

  getSettings: () => request<ConfigStatus>("/api/settings"),

  saveSettings: (update: SettingsUpdate) =>
    request<ConfigStatus>("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    }),

  testConnection: (provider: string, model: string, apiKey: string | null) =>
    request<ConnectionTest>("/api/settings/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, model, api_key: apiKey }),
    }),

  /** Download a generated report (Markdown or PDF). */
  async downloadReport(projectId: string, format: "md" | "pdf"): Promise<void> {
    const response = await send(`/api/projects/${projectId}/export.${format}`);
    if (response.status === 404) {
      throw new ApiError("export_unavailable", "This project is no longer on the server. Start a new analysis to export a report.");
    }
    if (!response.ok) {
      throw new ApiError("export_failed", "The report could not be generated.");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `unasked-question-report.${format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
};
