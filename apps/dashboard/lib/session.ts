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
 * This is a deliberate simplification for the vertical slice: silent
 * refresh-on-expiry at the BFF layer is not implemented yet, so a session expires
 * with the 15-minute access token and the user must log in again. Full silent
 * refresh is tracked as Phase F/H follow-up work.
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
