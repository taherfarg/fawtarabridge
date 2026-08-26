import type { ErrorDetail, TokenPair } from "./types";

const BASE = `${import.meta.env.VITE_API_URL ?? ""}/api/v1`;
const STORAGE_KEY = "fawtara.tokens";

export class ApiError extends Error {
  errors: ErrorDetail[];
  status: number;
  constructor(status: number, errors: ErrorDetail[]) {
    super(errors[0]?.message_en ?? `HTTP ${status}`);
    this.status = status;
    this.errors = errors;
  }
}

export function getTokens(): TokenPair | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  return raw ? (JSON.parse(raw) as TokenPair) : null;
}

export function setTokens(tokens: TokenPair | null): void {
  if (tokens) localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
  else localStorage.removeItem(STORAGE_KEY);
}

let onUnauthorized: (() => void) | null = null;
export function setOnUnauthorized(handler: () => void): void {
  onUnauthorized = handler;
}

async function refreshTokens(): Promise<boolean> {
  const tokens = getTokens();
  if (!tokens) return false;
  const response = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: tokens.refresh_token }),
  });
  if (!response.ok) return false;
  setTokens((await response.json()) as TokenPair);
  return true;
}

async function parseError(response: Response): Promise<ApiError> {
  let errors: ErrorDetail[] = [];
  try {
    const body = await response.json();
    if (Array.isArray(body?.errors)) errors = body.errors;
  } catch {
    /* non-JSON body */
  }
  if (errors.length === 0) {
    errors = [
      {
        code: "http.error",
        message_en: `Request failed (${response.status})`,
        message_ar: `فشل الطلب (${response.status})`,
      },
    ];
  }
  return new ApiError(response.status, errors);
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  retryOn401 = true,
): Promise<T> {
  const tokens = getTokens();
  const headers = new Headers(options.headers);
  if (tokens) headers.set("Authorization", `Bearer ${tokens.access_token}`);
  if (options.body && typeof options.body === "string") {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${BASE}${path}`, { ...options, headers });

  if (response.status === 401 && retryOn401 && tokens) {
    if (await refreshTokens()) return request<T>(path, options, false);
    setTokens(null);
    onUnauthorized?.();
  }
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) return (await response.json()) as T;
  return (await response.blob()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  postForm: <T>(path: string, form: FormData) => request<T>(path, { method: "POST", body: form }),
  blob: (path: string) => request<Blob>(path),
};

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
