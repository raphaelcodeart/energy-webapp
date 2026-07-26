import { NextRequest, NextResponse } from "next/server";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/**
 * Public (no session) password-reset request. Always proxies through as-is --
 * the backend itself is the one that guarantees a generic response regardless
 * of whether the email exists (enumeration-safety), this route just avoids
 * exposing API_INTERNAL_URL to the browser.
 */
export async function POST(request: NextRequest) {
  const body = await request.json();
  const apiRes = await fetch(`${API_INTERNAL_URL}/api/auth/forgot-password`, {
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
