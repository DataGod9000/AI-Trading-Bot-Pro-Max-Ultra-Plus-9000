const DEFAULT_SERVER_BASE = "http://127.0.0.1:8000";

/**
 * API URL for fetches.
 * - In the browser, default is same-origin `/api/...` so Next.js can proxy to FastAPI (avoids CORS:
 *   `localhost:3000` vs `127.0.0.1:8000` are different sites).
 * - Set NEXT_PUBLIC_API_URL only when the API is on another host (e.g. production).
 */
export function apiBase(): string {
  const explicit =
    typeof process.env.NEXT_PUBLIC_API_URL === "string" ? process.env.NEXT_PUBLIC_API_URL.trim() : "";
  if (typeof window !== "undefined") {
    if (explicit.length > 0) {
      return explicit.replace(/\/$/, "");
    }
    return "";
  }
  const internal = process.env.INTERNAL_API_URL?.trim();
  if (internal && internal.length > 0) {
    return internal.replace(/\/$/, "");
  }
  if (explicit.length > 0) {
    return explicit.replace(/\/$/, "");
  }
  return DEFAULT_SERVER_BASE;
}

export function apiUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  const base = apiBase();
  if (base === "") {
    return p;
  }
  return `${base}${p}`;
}

export type ApiGetOptions = {
  /** Abort after this many ms (CoinGecko-heavy routes may need 90s+). */
  timeoutMs?: number;
};

export async function apiGet<T>(path: string, opts?: ApiGetOptions): Promise<T> {
  const timeoutMs = opts?.timeoutMs ?? 90_000;
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(apiUrl(path), { cache: "no-store", signal: ctrl.signal });
    if (!r.ok) {
      const text = await r.text();
      throw new Error(text || r.statusText);
    }
    return r.json() as Promise<T>;
  } catch (e) {
    const aborted =
      (e instanceof DOMException && e.name === "AbortError") ||
      (e instanceof Error && e.name === "AbortError");
    if (aborted) {
      throw new Error(
        `Request timed out after ${Math.round(timeoutMs / 1000)}s. ` +
          `Is btc-paper-api running? (proxied from this app to ${DEFAULT_SERVER_BASE} by default.) ` +
          "Heavy routes (e.g. /api/technical/live) call CoinGecko and can be slow.",
      );
    }
    if (e instanceof TypeError) {
      throw new Error(
        `Cannot reach API — start the backend: \`btc-paper-api\` (repo root), or check API_PROXY_TARGET / NEXT_PUBLIC_API_URL. ` +
          `(${e.message})`,
      );
    }
    throw e;
  } finally {
    clearTimeout(t);
  }
}

export async function apiPost<T>(path: string, body?: object, opts?: ApiGetOptions): Promise<T> {
  const timeoutMs = opts?.timeoutMs ?? 60_000;
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(apiUrl(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: "no-store",
      signal: ctrl.signal,
    });
    if (!r.ok) {
      const text = await r.text();
      throw new Error(text || r.statusText);
    }
    return r.json() as Promise<T>;
  } catch (e) {
    const aborted =
      (e instanceof DOMException && e.name === "AbortError") ||
      (e instanceof Error && e.name === "AbortError");
    if (aborted) {
      throw new Error(
        `Request timed out after ${Math.round(timeoutMs / 1000)}s. Check the API is running.`,
      );
    }
    if (e instanceof TypeError) {
      throw new Error(`Cannot reach API. (${e.message})`);
    }
    throw e;
  } finally {
    clearTimeout(t);
  }
}
