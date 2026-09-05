import { apiFetchOrRedirectToLogin } from "@/lib/api-client";
import { decodeRolesFromAccessToken, getSession } from "@/lib/session";
import { AdminClientPage } from "@/components/admin-client-page";
import type { ContractRead } from "@/lib/types";

export default async function AdminDashboard() {
  const session = await getSession();
  const contracts = await apiFetchOrRedirectToLogin<ContractRead[]>("/contracts");
  const isSuperAdmin = session ? decodeRolesFromAccessToken(session.accessToken).includes("SUPER_ADMIN") : false;

  return (
    <AdminClientPage
      initialContracts={contracts}
      email={session?.email}
      organizationId={session?.organizationId}
      isSuperAdmin={isSuperAdmin}
    />
  );
}
