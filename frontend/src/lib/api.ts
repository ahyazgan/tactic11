/**
 * Backend API client — JWT bearer ile çalışır.
 *
 * Faz 3: gerçek refresh flow + race-condition'sız in-flight kuyruğu.
 * Aynı anda 3 isteğin 401 alması durumunda 1 refresh çağrısı yapılır,
 * üç istek de yeni access token ile retry edilir.
 */

const TOKEN_KEY = "manager2_access_token";
const REFRESH_KEY = "manager2_refresh_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(TOKEN_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

/**
 * In-flight refresh promise — race-condition guard.
 * Aynı anda birden çok 401 gelirse hepsi aynı promise'i bekler.
 */
let refreshInFlight: Promise<string | null> | null = null;

async function performRefresh(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;
  try {
    const res = await fetch("/api/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as {
      access_token: string;
      refresh_token: string;
    };
    setTokens(data.access_token, data.refresh_token);
    return data.access_token;
  } catch {
    return null;
  }
}

async function getOrRefreshToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

function redirectToLogin() {
  // Login akışı devre dışı (tek-kullanıcılı yerel kurulum). 401 gelirse sadece
  // bozuk/eski token'ı temizle; /login'e YÖNLENDİRME — sayfa auth'suz render olsun.
  clearTokens();
}

async function rawFetch(
  path: string,
  init: RequestInit,
  token: string | null,
): Promise<Response> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`/api${path}`, { ...init, headers });
}

export async function apiFetch<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = getAccessToken();
  let res = await rawFetch(path, init, token);

  if (res.status === 401) {
    // Refresh flow — singleton kuyruk
    const newToken = await getOrRefreshToken();
    if (!newToken) {
      redirectToLogin();
      throw new Error("Unauthorized");
    }
    // Tek bir retry
    res = await rawFetch(path, init, newToken);
    if (res.status === 401) {
      redirectToLogin();
      throw new Error("Unauthorized after refresh");
    }
  }

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`HTTP ${res.status}: ${body.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export async function login(
  email: string, password: string, tenantSlug?: string,
): Promise<{ access_token: string; refresh_token: string }> {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, tenant_slug: tenantSlug }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
