import { NextRequest, NextResponse } from "next/server";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/**
 * Public (no session) registration -- invite-only, gated on a referral_code
 * from a promoter's shared link. Just proxies to the backend, which does all
 * real validation (referral code, duplicate email, password strength); this
 * route exists only so the browser never needs API_INTERNAL_URL directly.
 */
export async function POST(request: NextRequest) {
  const body = await request.json();
  const apiRes = await fetch(`${API_INTERNAL_URL}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const responseBody = await apiRes.text();
  return new NextResponse(responseBody, {
    status: apiRes.status,
    headers: { "Content-Type": apiRes.headers.get("content-type") ?? "application/json" },
  });
}
