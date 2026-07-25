import { apiFetch } from "@/lib/api-client";
import { getSession } from "@/lib/session";
import { LogoutButton } from "@/components/logout-button";
import type { ContractRead } from "@/lib/types";

const STATUS_LABELS: Record<string, string> = {
  DRAFT: "Bozza",
  SUBMITTED: "Inviata",
  DOCUMENTS_PENDING: "Documenti mancanti",
  UNDER_REVIEW: "In revisione",
  APPROVED: "Approvata",
  PAYMENT_PENDING: "In attesa di pagamento",
  PAID: "Pagata",
  ACTIVATION_PENDING: "In attivazione",
  ACTIVE: "Attiva",
  SUSPENDED: "Sospesa",
  CANCELLED: "Cessata",
  EXPIRED: "Scaduta",
  RENEWED: "Rinnovata",
  REJECTED: "Respinta",
};

export default async function CustomerDashboard() {
  const session = await getSession();
  const contracts = await apiFetch<ContractRead[]>("/contracts/mine");

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">La mia area cliente</h1>
          <p className="text-sm text-slate-500">{session?.email}</p>
        </div>
        <LogoutButton />
      </div>

      <section>
        <h2 className="mb-3 text-lg font-medium">I miei contratti</h2>
        {contracts.length === 0 ? (
          <p className="text-sm text-slate-500">Nessun contratto trovato.</p>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left dark:border-slate-800">
                <th className="py-2 pr-4">Contratto</th>
                <th className="py-2 pr-4">Stato</th>
              </tr>
            </thead>
            <tbody>
              {contracts.map((c) => (
                <tr key={c.id} className="border-b border-slate-100 dark:border-slate-900">
                  <td className="py-2 pr-4 font-mono text-xs">{c.id}</td>
                  <td className="py-2 pr-4">{STATUS_LABELS[c.status] ?? c.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
