"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";

async function fetchMyRoles(): Promise<string[]> {
  const res = await fetch("/api/proxy/auth/me");
  if (!res.ok) return [];
  const data = await res.json();
  return data.roles ?? [];
}

/** Shared by AreaSwitcher and the UserMenu dropdown entry so both read the
 * same live roles/area without duplicating the gating logic. Reads LIVE
 * roles (not the access token's own, which are only as fresh as the last
 * login/refresh -- see auth/router.py get_me) so it reacts the moment
 * someone auto-activates or is deactivated, without a re-login. */
export function useDualRoleAreas() {
  const pathname = usePathname();
  const { data: roles = [] } = useQuery({
    queryKey: ["auth", "me", "roles"],
    queryFn: fetchMyRoles,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });

  return {
    hasBothRoles: roles.includes("CUSTOMER") && roles.includes("PROMOTER"),
    isCustomerArea: pathname?.startsWith("/customer") ?? false,
  };
}

/** Always-visible customer/promoter toggle for anyone who holds BOTH roles --
 * e.g. a customer who "lavora con noi"-activated into a promoter, or a
 * promoter who was also invited as a customer. Renders nothing for anyone
 * who holds only one of the two roles. */
export function AreaSwitcher() {
  const { hasBothRoles, isCustomerArea } = useDualRoleAreas();

  if (!hasBothRoles) return null;

  return (
    <div className="hidden sm:inline-flex items-center rounded-xl border border-white/10 light:border-slate-300 bg-white/5 light:bg-slate-900/5 p-1 gap-1">
      <Link
        href="/customer"
        className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
          isCustomerArea
            ? "bg-orange-600 text-white"
            : "text-slate-300 light:text-slate-600 hover:bg-white/10 light:hover:bg-slate-900/10"
        }`}
      >
        Area Cliente
      </Link>
      <Link
        href="/promoter"
        className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
          !isCustomerArea
            ? "bg-orange-600 text-white"
            : "text-slate-300 light:text-slate-600 hover:bg-white/10 light:hover:bg-slate-900/10"
        }`}
      >
        Area Promoter
      </Link>
    </div>
  );
}
