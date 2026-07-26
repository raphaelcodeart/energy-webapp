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

/** Shared by every body-carrying method (POST/PATCH/PUT/DELETE) -- forwarding
 * logic is identical regardless of verb, only the HTTP method sent upstream
 * differs. Multipart (file uploads, e.g. photo-upload.tsx, document-
 * upload.tsx) must be forwarded as raw bytes with the ORIGINAL content-type
 * (including its boundary) -- reading it as text() and re-sending as
 * application/json would corrupt the binary body and lose the boundary
 * entirely. */
async function proxyWithBody(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
  method: string
) {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { path } = await params;
  const search = request.nextUrl.search;
  const requestContentType = request.headers.get("content-type") ?? "";
  const isMultipart = requestContentType.startsWith("multipart/form-data");

  const apiRes = await fetch(`${API_INTERNAL_URL}/api/${path.join("/")}${search}`, {
    method,
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

export async function POST(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyWithBody(request, ctx, "POST");
}

// Real bug, fixed here: PATCH had never been implemented on this route at
// all (only GET/POST existed) -- every "save changes" edit form that PATCHes
// through this proxy (customer edit, promoter edit, product edit, contract
// IBAN, supply-point label, document review, ...) was silently 405ing since
// the day each was built. Confirmed live before this fix.
export async function PATCH(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyWithBody(request, ctx, "PATCH");
}

export async function PUT(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyWithBody(request, ctx, "PUT");
}

export async function DELETE(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyWithBody(request, ctx, "DELETE");
}
