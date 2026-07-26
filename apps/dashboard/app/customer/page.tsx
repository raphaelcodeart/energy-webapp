import { apiFetch } from "@/lib/api-client";
import { getSession } from "@/lib/session";
import { CustomerClientPage } from "@/components/customer-client-page";
import type { ContractRead } from "@/lib/types";

export default async function CustomerDashboard() {
  const session = await getSession();
  const contracts = await apiFetch<ContractRead[]>("/contracts/mine");

  return (
    <CustomerClientPage 
      contracts={contracts} 
      email={session?.email} 
    />
  );
}
