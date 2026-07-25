import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "lial_session";
const PROTECTED_PREFIXES = ["/customer", "/promoter", "/admin"];

export function proxy(request: NextRequest) {
  const isProtected = PROTECTED_PREFIXES.some((p) => request.nextUrl.pathname.startsWith(p));
  if (!isProtected) return NextResponse.next();

  const hasSession = request.cookies.has(SESSION_COOKIE);
  if (!hasSession) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/customer/:path*", "/promoter/:path*", "/admin/:path*"],
};
