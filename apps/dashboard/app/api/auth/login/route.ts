import { NextRequest, NextResponse } from "next/server";
import { setSession } from "@/lib/session";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { email, password, organizationId } = body as {
    email: string;
    password: string;
    organizationId: string;
  };

  const apiRes = await fetch(`${API_INTERNAL_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, organization_id: organizationId }),
  });

  if (!apiRes.ok) {
    const detail = await apiRes.text();
    return NextResponse.json({ error: detail || "Login failed" }, { status: apiRes.status });
  }

  const setCookieHeader = apiRes.headers.get("set-cookie") ?? "";
  const refreshMatch = /lial_refresh_token=([^;]+)/.exec(setCookieHeader);
  const refreshToken = refreshMatch?.[1] ?? "";

  const { access_token: accessToken } = (await apiRes.json()) as { access_token: string };

  await setSession({ accessToken, refreshToken, organizationId, email });

  return NextResponse.json({ ok: true });
}
