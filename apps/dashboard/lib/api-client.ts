import "server-only";
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
