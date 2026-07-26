import { apiFetch } from "@/lib/api-client";
import { getSession } from "@/lib/session";
import { PromoterClientPage } from "@/components/promoter-client-page";
import type { AgentProfileRead, BranchMemberRead } from "@/lib/types";

export default async function PromoterDashboard() {
  const session = await getSession();
  const me = await apiFetch<AgentProfileRead | null>("/network/mine");

  const branch = me ? await apiFetch<BranchMemberRead[]>(`/network/agents/${me.id}/branch`) : [];

  return (
    <PromoterClientPage 
      me={me} 
      branch={branch} 
      email={session?.email} 
    />
  );
}
