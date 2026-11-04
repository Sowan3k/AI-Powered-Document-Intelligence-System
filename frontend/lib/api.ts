// Client for the DocIntel REST API. The browser calls the API directly
// (DECISIONS.md D14). NEXT_PUBLIC_API_BASE_URL is inlined at build time, so
// Vercel must have it set before it builds.

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"
).replace(/\/+$/, "");

export type HealthResponse = {
  status: "ok" | "degraded";
  database: "connected" | "unavailable";
  database_latency_ms: number | null;
  environment: string;
  version: string;
};

export type HealthResult =
  | { kind: "healthy"; body: HealthResponse }
  | { kind: "degraded"; body: HealthResponse }
  | { kind: "unreachable"; reason: string };

// A sleeping Render free instance can take close to a minute to wake up.
export const HEALTH_TIMEOUT_MS = 90_000;

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResult> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/health`, {
      cache: "no-store",
      signal,
    });
  } catch (error) {
    const aborted = error instanceof DOMException && error.name === "AbortError";
    return {
      kind: "unreachable",
      reason: aborted ? "The API did not answer in time." : "The API could not be reached.",
    };
  }

  // The API answers 503 with a JSON body when the database is down.
  if (response.status !== 200 && response.status !== 503) {
    return { kind: "unreachable", reason: `The API answered with status ${response.status}.` };
  }
  try {
    const body = (await response.json()) as HealthResponse;
    const healthy = body.status === "ok" && body.database === "connected";
    return healthy ? { kind: "healthy", body } : { kind: "degraded", body };
  } catch {
    return { kind: "unreachable", reason: "The API sent a response that is not valid JSON." };
  }
}

// --- Authenticated calls ---------------------------------------------------

const TOKEN_KEY = "docintel.token";
export const SIGNED_OUT_EVENT = "docintel:signed-out";
// A request waits this long before the page says the backend may be waking up.
export const COLD_START_HINT_MS = 5_000;

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type StoredToken = { token: string; expiresAt: number };

// Kept in sessionStorage: it ends with the tab, and nothing else on this
// origin reads it. The API never sets cookies, so there is no CSRF surface.
export function saveToken(token: string, expiresInS: number): void {
  const value: StoredToken = { token, expiresAt: Date.now() + expiresInS * 1000 };
  sessionStorage.setItem(TOKEN_KEY, JSON.stringify(value));
}

export function readToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(TOKEN_KEY);
    if (!raw) return null;
    const stored = JSON.parse(raw) as StoredToken;
    if (stored.expiresAt <= Date.now()) {
      sessionStorage.removeItem(TOKEN_KEY);
      return null;
    }
    return stored.token;
  } catch {
    return null;
  }
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

function detailOf(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string; loc?: unknown[] };
      const where = Array.isArray(first.loc) ? first.loc.slice(1).join(".") : "";
      return [where, first.msg].filter(Boolean).join(": ") || `Request failed (${status})`;
    }
  }
  return `Request failed (${status})`;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = readToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    throw new ApiError(0, "The API could not be reached. It may be waking up; try again.");
  }
  if (response.status === 401 && path !== "/api/auth/login") {
    // The token expired or is wrong: forget it and let the app send the user to login.
    clearToken();
    if (typeof window !== "undefined") window.dispatchEvent(new Event(SIGNED_OUT_EVENT));
  }
  const text = await response.text();
  const body: unknown = text ? safeJson(text) : null;
  if (!response.ok) throw new ApiError(response.status, detailOf(body, response.status));
  return body as T;
}

// A file from the API (it needs the token, so a plain link cannot fetch it).
export async function apiBlob(path: string): Promise<Blob> {
  const headers = new Headers();
  const token = readToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { headers, cache: "no-store" });
  } catch {
    throw new ApiError(0, "The API could not be reached. It may be waking up; try again.");
  }
  if (response.status === 401) {
    clearToken();
    if (typeof window !== "undefined") window.dispatchEvent(new Event(SIGNED_OUT_EVENT));
  }
  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(response.status, detailOf(text ? safeJson(text) : null, response.status));
  }
  return response.blob();
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export function query(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
