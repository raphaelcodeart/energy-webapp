import "server-only";
import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/**
 * Server-side-only fetch to FastAPI. Always attaches the caller's access token --
 * there is no code path that calls the API without it, since authorization is
 * enforced by FastAPI regardless of what the frontend does or doesn't render.
 */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const session = await getSession();
  if (!session) {
    throw new ApiError(401, "No active session");
  }

  const res = await fetch(`${API_INTERNAL_URL}/api${path}`, {
    ...init,
    headers: {
      ...init?.headers,
      Authorization: `Bearer ${session.accessToken}`,
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body || res.statusText);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

/**
 * Same as apiFetch(), but a 401 (session cookie present but the access token
 * inside it has expired -- 15-minute TTL, no silent refresh yet, see
 * lib/session.ts) redirects to /login instead of throwing. Every dashboard
 * page's initial server-side data fetch should use this, not apiFetch()
 * directly -- an uncaught ApiError from a Server Component previously
 * surfaced as Next's generic 500 error page, which is exactly what a user
 * with an old tab open (or a session older than 15 minutes) would hit on
 * every visit to /admin, /promoter or /customer until they manually logged
 * out and back in.
 *
 * Deliberately does NOT clear the stale cookie here: cookies can only be
 * written from a Server Action or Route Handler, never from a plain Server
 * Component render (this function is called from page.tsx components) --
 * doing so throws "Cookies can only be modified in a Server Action or Route
 * Handler" and replaces one 500 with another. The stale cookie is harmless
 * to leave in place: /login doesn't check for an existing session, and a
 * successful login overwrites it via setSession() in the actual login Route
 * Handler.
 */
export async function apiFetchOrRedirectToLogin<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    return await apiFetch<T>(path, init);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      redirect("/login");
    }
    throw err;
  }
}
