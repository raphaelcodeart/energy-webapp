import { apiFetch } from "@/lib/api-client";
import { getSession } from "@/lib/session";
import { LogoutButton } from "@/components/logout-button";
import type { ContractRead } from "@/lib/types";

export default async function AdminDashboard() {
  const session = await getSession();
  const contracts = await apiFetch<ContractRead[]>("/contracts");

  const byStatus = contracts.reduce<Record<string, number>>((acc, c) => {
    acc[c.status] = (acc[c.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Area amministratore</h1>
          <p className="text-sm text-slate-500">{session?.email}</p>
        </div>
        <LogoutButton />
      </div>

      <section className="mb-10">
        <h2 className="mb-3 text-lg font-medium">Contratti per stato (organizzazione)</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Object.entries(byStatus).map(([status, count]) => (
            <div key={status} className="rounded border border-slate-200 p-3 dark:border-slate-800">
              <p className="text-xs text-slate-500">{status}</p>
              <p className="text-xl font-semibold">{count}</p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-medium">Tutti i contratti</h2>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left dark:border-slate-800">
              <th className="py-2 pr-4">Contratto</th>
              <th className="py-2 pr-4">Cliente</th>
              <th className="py-2 pr-4">Stato</th>
            </tr>
          </thead>
          <tbody>
            {contracts.map((c) => (
              <tr key={c.id} className="border-b border-slate-100 dark:border-slate-900">
                <td className="py-2 pr-4 font-mono text-xs">{c.id}</td>
                <td className="py-2 pr-4 font-mono text-xs">{c.customer_id}</td>
                <td className="py-2 pr-4">{c.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
