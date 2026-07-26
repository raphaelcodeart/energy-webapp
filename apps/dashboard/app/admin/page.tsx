import { apiFetch } from "@/lib/api-client";
import { getSession } from "@/lib/session";
import { AdminClientPage } from "@/components/admin-client-page";
import type { ContractRead } from "@/lib/types";

export default async function AdminDashboard() {
  const session = await getSession();
  const contracts = await apiFetch<ContractRead[]>("/contracts");

  return (
    <AdminClientPage 
      initialContracts={contracts} 
      email={session?.email} 
      organizationId={session?.organizationId} 
    />
  );
}
