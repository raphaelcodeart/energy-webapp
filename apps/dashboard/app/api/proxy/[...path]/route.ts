import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/session";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/**
 * Same-origin proxy for client components that need TanStack Query's
 * client-side caching/refetching. The browser only ever talks to this route;
 * the access token is attached here, server-side, and never reaches client JS.
 */
export async function GET(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { path } = await params;
  const search = request.nextUrl.search;
  const apiRes = await fetch(`${API_INTERNAL_URL}/api/${path.join("/")}${search}`, {
    headers: { Authorization: `Bearer ${session.accessToken}` },
    cache: "no-store",
  });

  const body = await apiRes.text();
  return new NextResponse(body, {
    status: apiRes.status,
    headers: { "Content-Type": apiRes.headers.get("content-type") ?? "application/json" },
  });
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { path } = await params;
  const search = request.nextUrl.search;
  const requestContentType = request.headers.get("content-type") ?? "";

  // Multipart (file uploads, e.g. photo-upload.tsx) must be forwarded as raw
  // bytes with the ORIGINAL content-type (including its boundary) -- reading
  // it as text() and re-sending as application/json (the JSON-only path
  // below) would corrupt the binary body and lose the boundary entirely.
  const isMultipart = requestContentType.startsWith("multipart/form-data");

  const apiRes = await fetch(`${API_INTERNAL_URL}/api/${path.join("/")}${search}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${session.accessToken}`,
      "Content-Type": isMultipart ? requestContentType : "application/json",
    },
    body: isMultipart ? await request.arrayBuffer() : await request.text().catch(() => undefined),
    cache: "no-store",
  });

  const body = await apiRes.text();
  return new NextResponse(body, {
    status: apiRes.status,
    headers: { "Content-Type": apiRes.headers.get("content-type") ?? "application/json" },
  });
}

