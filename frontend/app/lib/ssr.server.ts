/**
 * SSR data fetching utility.
 *
 * This module is server-only (.server.ts) — it reads SSR_API_URL from
 * the Node process environment and fetches lightweight entity data from
 * the Django backend for meta tags and above-the-fold skeletons.
 */

const SSR_API_URL = process.env.SSR_API_URL ?? "http://backend:8000/api";

/**
 * Fetch SSR data from a Django /ssr/ endpoint.
 * Returns null on any error (404, network, timeout) — SSR should never block rendering.
 */
export async function fetchSSR<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${SSR_API_URL}${path}`, {
      signal: AbortSignal.timeout(3000), // 3s timeout — don't block SSR
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}
