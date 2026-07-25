import { apiFetch } from "@/lib/api-client";
import { getSession } from "@/lib/session";
import { LogoutButton } from "@/components/logout-button";
import { BranchTable } from "@/components/branch-table";
import { MyCommissions } from "@/components/my-commissions";
import { QueryProvider } from "@/app/providers";
import type { AgentProfileRead, BranchMemberRead } from "@/lib/types";

export default async function PromoterDashboard() {
  const session = await getSession();
  const me = await apiFetch<AgentProfileRead | null>("/network/mine");

  const branch = me ? await apiFetch<BranchMemberRead[]>(`/network/agents/${me.id}/branch`) : [];

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Area promoter</h1>
          <p className="text-sm text-slate-500">{session?.email}</p>
        </div>
        <LogoutButton />
      </div>

      {!me ? (
        <p className="text-sm text-slate-500">Nessun profilo agente collegato a questo account.</p>
      ) : (
        <>
          <section className="mb-10 rounded border border-slate-200 p-4 dark:border-slate-800">
            <p className="text-sm text-slate-500">Codice promoter</p>
            <p className="font-mono text-lg">{me.promoter_code}</p>
          </section>

          <section className="mb-10">
            <h2 className="mb-3 text-lg font-medium">La mia rete (diretti e discendenti)</h2>
            <p className="mb-2 text-sm text-slate-500">
              {branch.length} agenti nel ramo, incluso te stesso (profondità 0).
            </p>
            <BranchTable members={branch} />
          </section>

          <section>
            <h2 className="mb-3 text-lg font-medium">Le mie provvigioni</h2>
            <QueryProvider>
              <MyCommissions />
            </QueryProvider>
          </section>
        </>
      )}
    </main>
  );
}
