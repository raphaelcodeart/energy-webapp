import "server-only";
import { cookies } from "next/headers";

const SESSION_COOKIE = "lial_session";

export type Session = {
  accessToken: string;
  refreshToken: string;
  organizationId: string;
  email: string;
};

/**
 * The BFF's own session cookie -- HttpOnly/Secure/SameSite=Lax, never readable
 * from browser JS. It bundles the short-lived API access token and the API
 * refresh token so the browser itself never sees either (see docs/security-model.md).
 */
export async function getSession(): Promise<Session | null> {
  const store = await cookies();
  const raw = store.get(SESSION_COOKIE)?.value;
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Session;
  } catch {
    return null;
  }
}

export async function setSession(session: Session): Promise<void> {
  const store = await cookies();
  store.set(SESSION_COOKIE, JSON.stringify(session), {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
}

export async function clearSession(): Promise<void> {
  const store = await cookies();
  store.delete(SESSION_COOKIE);
}

/** Reads the roles baked into an access token's JWT payload (see
 * auth/service.py:authenticate) -- used both right after login (to route to
 * the correct dashboard) and later, by /api/auth/me, to let an already
 * logged-in page ask "what am I right now" (e.g. the customer/promoter area
 * switcher, for someone who holds both roles). */
export function decodeRolesFromAccessToken(accessToken: string): string[] {
  try {
    const payload = accessToken.split(".")[1] ?? "";
    const json = Buffer.from(payload, "base64url").toString("utf-8");
    const { roles } = JSON.parse(json) as { roles?: string[] };
    return roles ?? [];
  } catch {
    return [];
  }
}

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/**
 * Silent refresh: the access token embedded in the session cookie lives only
 * `access_token_expire_minutes` (15 min) -- any proxied call can hit it
 * mid-session (e.g. filling out a form for a while). The refresh token
 * (`session.refreshToken`) lives `refresh_token_expire_days` (30, matching
 * this cookie's own maxAge), so re-authenticating on every 15-minute access
 * token expiry would be pure friction. The backend expects the refresh token
 * as a cookie (not a header/body field, see auth/router.py's REFRESH_COOKIE_NAME)
 * even though this BFF stores it inside its own session JSON blob instead of a
 * real browser cookie -- so it has to be replayed as one here, server-to-server.
 * Returns the updated session (already persisted) on success, or null if the
 * refresh token itself is invalid/expired too -- at that point only a real
 * login can recover, there is nothing left to silently retry.
 */
export async function refreshSession(session: Session): Promise<Session | null> {
  const apiRes = await fetch(
    `${API_INTERNAL_URL}/api/auth/refresh?organization_id=${encodeURIComponent(session.organizationId)}`,
    {
      method: "POST",
      headers: { Cookie: `lial_refresh_token=${session.refreshToken}` },
      cache: "no-store",
    }
  );
  if (!apiRes.ok) return null;

  const setCookieHeader = apiRes.headers.get("set-cookie") ?? "";
  const refreshMatch = /lial_refresh_token=([^;]+)/.exec(setCookieHeader);
  const { access_token: accessToken } = (await apiRes.json()) as { access_token: string };

  const updated: Session = {
    ...session,
    accessToken,
    refreshToken: refreshMatch?.[1] ?? session.refreshToken,
  };
  await setSession(updated);
  return updated;
}
