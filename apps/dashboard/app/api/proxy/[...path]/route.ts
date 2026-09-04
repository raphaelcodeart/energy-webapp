import { NextRequest, NextResponse } from "next/server";
import { getSession, refreshSession, type Session } from "@/lib/session";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

/** True only for this app's own "your access token is bad/expired" 401 --
 * never for a permission (403) or a business-rule 401 from elsewhere -- so a
 * refresh is attempted exactly when it can actually help. See core/deps.py's
 * get_current_user for where these three strings come from. */
async function isExpiredTokenResponse(apiRes: Response): Promise<boolean> {
  if (apiRes.status !== 401) return false;
  const body = await apiRes.clone().text().catch(() => "");
  return /Invalid or expired token|Missing bearer token|Wrong token type/.test(body);
}

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
  const url = `${API_INTERNAL_URL}/api/${path.join("/")}${search}`;

  let apiRes = await fetch(url, {
    headers: { Authorization: `Bearer ${session.accessToken}` },
    cache: "no-store",
  });

  if (await isExpiredTokenResponse(apiRes)) {
    const refreshed: Session | null = await refreshSession(session);
    if (refreshed) {
      apiRes = await fetch(url, {
        headers: { Authorization: `Bearer ${refreshed.accessToken}` },
        cache: "no-store",
      });
    }
  }

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
  // Read the incoming body exactly once -- request.text()/arrayBuffer() can't
  // be replayed, but a possible retry-after-refresh below needs the same
  // bytes sent twice.
  const requestBody = isMultipart ? await request.arrayBuffer() : await request.text().catch(() => undefined);

  const url = `${API_INTERNAL_URL}/api/${path.join("/")}${search}`;
  const upstreamHeaders = (token: string) => ({
    Authorization: `Bearer ${token}`,
    "Content-Type": isMultipart ? requestContentType : "application/json",
  });

  let apiRes = await fetch(url, {
    method,
    headers: upstreamHeaders(session.accessToken),
    body: requestBody,
    cache: "no-store",
  });

  if (await isExpiredTokenResponse(apiRes)) {
    const refreshed: Session | null = await refreshSession(session);
    if (refreshed) {
      apiRes = await fetch(url, {
        method,
        headers: upstreamHeaders(refreshed.accessToken),
        body: requestBody,
        cache: "no-store",
      });
    }
  }

  const body = await apiRes.text();
  const headers = { "Content-Type": apiRes.headers.get("content-type") ?? "application/json" };
  // A 204/205/304 response must not carry a body -- the Response constructor
  // throws "Response with null body status cannot have body" even for an
  // empty string, which silently 500s every no-content response (e.g.
  // DELETE /support/tickets/{id}) despite the upstream call having already
  // succeeded. Confirmed live: a ticket delete removed the row but the
  // proxy call surfaced as a failure until this branch was added.
  if (apiRes.status === 204 || apiRes.status === 205 || apiRes.status === 304) {
    return new NextResponse(null, { status: apiRes.status, headers });
  }
  return new NextResponse(body, { status: apiRes.status, headers });
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
