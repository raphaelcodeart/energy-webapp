"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ContractRequestsList, type WizardTarget } from "@/components/contract-requests-list";
import { ContractRequestWizard } from "@/components/contract-request-wizard";
import { friendlyApiError } from "@/lib/api-error";
import type { AgentProfileRead, CustomerRead } from "@/lib/types";

type WizardCustomer = {
  id: string;
  kind: string | null;
  email: string | null;
  firstName?: string | null;
  lastName?: string | null;
  pec?: string | null;
};

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

const KIND_LABELS: Record<string, string> = {
  PRIVATE: "Privato",
  SOLE_PROPRIETOR: "Ditta individuale",
  COMPANY: "Azienda",
};

/** Opening a pratica for somebody else: the customer is chosen here, and
 *  from there it is the very same wizard the customer uses on themselves
 *  (Session 66) -- holder data, "quanti POD hai?", documents, a package per
 *  POD -- minus the payment, which only the customer can do from their own
 *  account. An administrator can also say which promoter earns on it.
 */
export function PraticheForCustomersPanel({
  mode,
  title,
  description,
}: {
  mode: "promoter" | "admin";
  title: string;
  description: string;
}) {
  const customersPath = mode === "promoter" ? "/api/proxy/network/customers/mine" : "/api/proxy/customers";
  const { data: customers, error: customersError } = useQuery({
    queryKey: [mode, "pratiche", "customers"],
    queryFn: () => fetchJson<CustomerRead[]>(customersPath),
  });
  const { data: agents } = useQuery({
    queryKey: ["admin", "agents", "for-pratica"],
    queryFn: () => fetchJson<AgentProfileRead[]>("/api/proxy/network/agents"),
    enabled: mode === "admin",
  });

  const [picking, setPicking] = useState(false);
  const [search, setSearch] = useState("");
  const [producerAgentId, setProducerAgentId] = useState("");
  const [wizard, setWizard] = useState<{ customer: WizardCustomer; target: WizardTarget | "new" } | null>(null);

  const needle = search.trim().toLowerCase();
  const matches = (customers ?? []).filter(
    (c) =>
      !needle ||
      [c.display_name, c.email, c.phone, c.fiscal_code, c.vat_number]
        .filter(Boolean)
        .some((v) => v!.toLowerCase().includes(needle))
  );

  function startFor(customer: CustomerRead) {
    setPicking(false);
    setSearch("");
    setWizard({
      customer: {
        id: customer.id,
        kind: customer.kind,
        email: customer.email,
        firstName: customer.first_name,
        lastName: customer.last_name,
        pec: customer.pec,
      },
      target: "new",
    });
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-white light:text-slate-900">{title}</h3>
          <p className="text-xs text-slate-400 light:text-slate-500 mt-0.5 max-w-2xl">{description}</p>
        </div>
        <button
          onClick={() => setPicking((v) => !v)}
          className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-white text-xs font-bold shadow-lg shadow-orange-500/20 transition cursor-pointer shrink-0"
        >
          {picking ? "Annulla" : "Attiva nuovo contratto"}
        </button>
      </div>

      {picking && (
        <div className="glass-card rounded-2xl p-5 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 space-y-3">
          <p className="text-sm font-semibold text-white light:text-slate-900">Per quale cliente?</p>
          {mode === "admin" && (
            <label className="block">
              <span className="block text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1">
                Promoter a cui attribuire la pratica (facoltativo)
              </span>
              <select
                value={producerAgentId}
                onChange={(e) => setProducerAgentId(e.target.value)}
                className="w-full max-w-md rounded-lg glass-input px-3 py-2 text-sm focus:border-orange-500"
              >
                <option value="">Promoter del cliente (predefinito)</option>
                {(agents ?? [])
                  .filter((a) => a.status === "ACTIVE")
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.display_name} ({a.promoter_code})
                    </option>
                  ))}
              </select>
              <span className="block text-[10px] text-slate-500 mt-1">
                Decide chi guadagna le provvigioni. Lasciando il predefinito, guadagna il promoter che ha portato il cliente.
              </span>
            </label>
          )}
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cerca per nome, email, telefono, codice fiscale..."
            className="w-full rounded-lg glass-input px-3 py-2 text-sm focus:border-orange-500"
          />
          {customersError && <p className="text-xs text-rose-400">{(customersError as Error).message}</p>}
          <div className="max-h-72 overflow-y-auto rounded-xl border border-white/10 light:border-slate-200 divide-y divide-white/5 light:divide-slate-200">
            {matches.length === 0 ? (
              <p className="px-4 py-6 text-center text-xs text-slate-500">
                {customers === undefined ? "Caricamento..." : "Nessun cliente trovato."}
              </p>
            ) : (
              matches.slice(0, 60).map((c) => (
                <button
                  key={c.id}
                  onClick={() => startFor(c)}
                  className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-left hover:bg-white/5 light:hover:bg-slate-900/5 cursor-pointer"
                >
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-white light:text-slate-900 truncate">{c.display_name}</span>
                    <span className="block text-[11px] text-slate-500 truncate">
                      {KIND_LABELS[c.kind] ?? c.kind}
                      {c.email ? ` · ${c.email}` : ""}
                    </span>
                  </span>
                  <span className="text-[11px] font-semibold text-orange-400 shrink-0">Apri pratica →</span>
                </button>
              ))
            )}
          </div>
          {mode === "admin" && (
            <p className="text-[11px] text-slate-500">
              Il cliente non c&apos;è? Registralo in <strong>Clienti → Nuovo Cliente</strong>, poi torna qui.
            </p>
          )}
        </div>
      )}

      {mode === "promoter" ? (
        <ContractRequestsList
          mode="promoter"
          onOpenWizard={(target) => {
            if (!target.customer) return;
            setWizard({ customer: target.customer, target });
          }}
        />
      ) : (
        <p className="text-xs text-slate-500">
          Le pratiche aperte, con verifiche, approvazioni e bonifici da confermare, sono in <strong>Pratiche</strong>.
        </p>
      )}

      {wizard && (
        <ContractRequestWizard
          requestId={wizard.target === "new" ? undefined : wizard.target.requestId}
          initialStep={wizard.target === "new" ? undefined : wizard.target.step}
          customer={wizard.customer}
          producerAgentId={mode === "admin" ? producerAgentId || null : null}
          onClose={() => setWizard(null)}
        />
      )}
    </div>
  );
}
