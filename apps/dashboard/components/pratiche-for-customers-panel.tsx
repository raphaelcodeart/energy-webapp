"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ContractRequestsList, type WizardTarget } from "@/components/contract-requests-list";
import { ContractRequestWizard } from "@/components/contract-request-wizard";
import { CUSTOMER_KIND_LABELS, NewCustomerForm } from "@/components/new-customer-form";
import { Pagination, usePagination } from "@/components/pagination";
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

type Mode = "promoter" | "admin";
type Action = "new" | "existing" | null;

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

function toWizardCustomer(c: CustomerRead): WizardCustomer {
  return { id: c.id, kind: c.kind, email: c.email, firstName: c.first_name, lastName: c.last_name, pec: c.pec };
}

const FLOW = ["Cliente", "Dati e POD", "Documenti", "Contratto per ogni POD", "Il cliente paga"];

/** Activating contracts for somebody else (Sessions 66-67): the promoter's
 *  "Miei Clienti" and the administration's "Nuovo Contratto" are the same
 *  screen. Two ways in -- a brand-new customer, registered here with their
 *  own login, or one already registered -- and from there the very wizard
 *  the customer uses on themselves (holder, "quanti POD hai?", documents, a
 *  contract per POD), minus the payment: when the pratica is sent the
 *  customer gets an email and pays from their own area.
 *
 *  An administrator also says which promoter the pratica is attributed to,
 *  and can give a login to a customer registered without one (they could
 *  never pay otherwise).
 */
export function PraticheForCustomersPanel({ mode }: { mode: Mode }) {
  const queryClient = useQueryClient();
  const customersKey = mode === "promoter" ? ["network", "customers", "mine"] : ["admin", "customers"];
  const { data: customers, error: customersError } = useQuery({
    queryKey: customersKey,
    queryFn: () => fetchJson<CustomerRead[]>(mode === "promoter" ? "/api/proxy/network/customers/mine" : "/api/proxy/customers"),
  });
  const { data: agents } = useQuery({
    queryKey: ["admin", "agents", "for-pratica"],
    queryFn: () => fetchJson<AgentProfileRead[]>("/api/proxy/network/agents"),
    enabled: mode === "admin",
  });

  const [action, setAction] = useState<Action>(null);
  const [producerAgentId, setProducerAgentId] = useState("");
  const [wizard, setWizard] = useState<{ customer: WizardCustomer; target: WizardTarget | "new"; producer: string | null } | null>(null);
  const [listTab, setListTab] = useState<"customers" | "pratiche">("customers");
  const [expandedCustomerId, setExpandedCustomerId] = useState<string | null>(null);

  function openFor(customer: CustomerRead, producer: string | null) {
    setAction(null);
    setWizard({ customer: toWizardCustomer(customer), target: "new", producer });
  }

  return (
    <div className="space-y-6">
      {/* The two ways in, always in sight. */}
      <div className="glass-card rounded-2xl p-5 sm:p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 space-y-5">
        <div>
          <h3 className="text-lg font-bold text-white light:text-slate-900">Attiva contratti per un cliente</h3>
          <p className="text-xs text-slate-400 light:text-slate-500 mt-1 max-w-3xl">
            Gli stessi passaggi che fa il cliente quando attiva da solo, senza il pagamento: quando invii la pratica il
            cliente riceve un&apos;email e paga dalla sua area.
            {mode === "promoter"
              ? " Resta scritto che l'hai compilata tu e le provvigioni sono tue."
              : " Scegli tu a quale promoter attribuirla."}
          </p>
          <ol className="mt-3 flex flex-wrap items-center gap-1.5">
            {FLOW.map((label, i) => (
              <li key={label} className="flex items-center gap-1.5">
                <span
                  className={`flex items-center gap-1.5 px-2 py-1 rounded-lg text-[11px] font-semibold border ${
                    i === FLOW.length - 1
                      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                      : "bg-white/5 light:bg-slate-900/5 text-slate-300 light:text-slate-600 border-white/10 light:border-slate-200"
                  }`}
                >
                  <span className="w-4 h-4 rounded-full bg-orange-600 text-white text-[9px] font-bold flex items-center justify-center">
                    {i + 1}
                  </span>
                  {label}
                </span>
                {i < FLOW.length - 1 && <span className="text-slate-600 text-xs">→</span>}
              </li>
            ))}
          </ol>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <ActionCard
            active={action === "new"}
            title="Nuovo cliente"
            text="Registralo adesso e attiva subito i suoi contratti. Riceve l'invito a impostare la password."
            icon="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"
            onClick={() => setAction(action === "new" ? null : "new")}
          />
          <ActionCard
            active={action === "existing"}
            title="Cliente già registrato"
            text="Aggiungi uno o più contratti a un cliente che hai già: cercalo per nome, email o codice fiscale."
            icon="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            onClick={() => setAction(action === "existing" ? null : "existing")}
          />
        </div>

        {action === "new" && (
          <div className="p-4 sm:p-5 rounded-2xl border border-orange-500/25 bg-orange-500/5">
            <p className="text-sm font-bold text-white light:text-slate-900 mb-3">1 · Dati del nuovo cliente</p>
            <NewCustomerForm
              mode={mode}
              agents={agents}
              onCancel={() => setAction(null)}
              onCreated={async (customer, promoterAgentId) => {
                await queryClient.invalidateQueries({ queryKey: customersKey });
                openFor(customer, promoterAgentId);
              }}
            />
          </div>
        )}

        {action === "existing" && (
          <div className="p-4 sm:p-5 rounded-2xl border border-orange-500/25 bg-orange-500/5 space-y-3">
            <p className="text-sm font-bold text-white light:text-slate-900">1 · Per quale cliente?</p>
            {mode === "admin" && <ProducerSelect agents={agents} value={producerAgentId} onChange={setProducerAgentId} />}
            <CustomerPicker
              mode={mode}
              customers={customers}
              error={customersError as Error | null}
              onPick={(c) => openFor(c, producerAgentId || null)}
              onLoginCreated={() => queryClient.invalidateQueries({ queryKey: customersKey })}
            />
          </div>
        )}
      </div>

      {mode === "promoter" ? (
        <div className="space-y-4">
          <div className="flex gap-2">
            {(
              [
                ["customers", `I miei clienti${customers ? ` (${customers.length})` : ""}`],
                ["pratiche", "Tutte le pratiche"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setListTab(key)}
                className={`px-4 py-2 rounded-xl text-xs font-semibold border transition cursor-pointer ${
                  listTab === key
                    ? "bg-orange-600 border-orange-600 text-white"
                    : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {listTab === "customers" ? (
            <MyCustomersList
              customers={customers}
              error={customersError as Error | null}
              expandedCustomerId={expandedCustomerId}
              onToggle={(id) => setExpandedCustomerId(expandedCustomerId === id ? null : id)}
              onActivate={(c) => openFor(c, null)}
              onOpenWizard={(c, target) => setWizard({ customer: toWizardCustomer(c), target, producer: null })}
            />
          ) : (
            <ContractRequestsList
              mode="promoter"
              onOpenWizard={(target) => {
                if (!target.customer) return;
                setWizard({ customer: target.customer, target, producer: null });
              }}
            />
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <div>
            <h3 className="text-sm font-bold text-white light:text-slate-900">Pratiche aperte dall&apos;amministrazione</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Riprendi le bozze da qui. Verifiche, approvazioni e bonifici da confermare di tutte le pratiche sono in{" "}
              <strong>Pratiche</strong>.
            </p>
          </div>
          <ContractRequestsList
            mode="admin"
            onOpenWizard={(target) => {
              if (!target.customer) return;
              setWizard({ customer: target.customer, target, producer: null });
            }}
          />
        </div>
      )}

      {wizard && (
        <ContractRequestWizard
          requestId={wizard.target === "new" ? undefined : wizard.target.requestId}
          initialStep={wizard.target === "new" ? undefined : wizard.target.step}
          customer={wizard.customer}
          producerAgentId={mode === "admin" ? wizard.producer : null}
          onClose={() => {
            if (mode === "promoter") setExpandedCustomerId(wizard.customer.id);
            setWizard(null);
          }}
        />
      )}
    </div>
  );
}

function ActionCard({
  active,
  title,
  text,
  icon,
  onClick,
}: {
  active: boolean;
  title: string;
  text: string;
  icon: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`group flex items-start gap-3 p-4 rounded-2xl border text-left transition cursor-pointer ${
        active
          ? "border-orange-500 bg-orange-500/10 shadow-lg shadow-orange-500/10"
          : "border-white/10 light:border-slate-200 bg-white/5 light:bg-white hover:border-orange-500/50"
      }`}
    >
      <span
        className={`p-2.5 rounded-xl shrink-0 transition-colors ${
          active ? "bg-orange-500 text-white" : "bg-orange-500/10 text-orange-400 group-hover:bg-orange-500 group-hover:text-white"
        }`}
      >
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={icon} />
        </svg>
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-bold text-white light:text-slate-900">{title}</span>
        <span className="block text-xs text-slate-400 light:text-slate-500 mt-0.5">{text}</span>
      </span>
    </button>
  );
}

function ProducerSelect({
  agents,
  value,
  onChange,
}: {
  agents: AgentProfileRead[] | undefined;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="block text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1">
        Promoter a cui attribuire la pratica
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full max-w-md rounded-lg glass-input px-3 py-2 text-sm bg-slate-900 light:bg-white focus:border-orange-500"
      >
        <option value="">Il promoter del cliente (predefinito)</option>
        {(agents ?? [])
          .filter((a) => a.status === "ACTIVE")
          .map((a) => (
            <option key={a.id} value={a.id}>
              {a.display_name} ({a.promoter_code})
            </option>
          ))}
      </select>
      <span className="block text-[10px] text-slate-500 mt-1">Decide chi guadagna le provvigioni di questa pratica.</span>
    </label>
  );
}

function CustomerPicker({
  mode,
  customers,
  error,
  onPick,
  onLoginCreated,
}: {
  mode: Mode;
  customers: CustomerRead[] | undefined;
  error: Error | null;
  onPick: (customer: CustomerRead) => void;
  onLoginCreated: () => void;
}) {
  const [search, setSearch] = useState("");
  const [needsLogin, setNeedsLogin] = useState<CustomerRead | null>(null);
  const [busy, setBusy] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  const needle = search.trim().toLowerCase();
  const matches = (customers ?? []).filter(
    (c) =>
      !needle ||
      [c.display_name, c.email, c.phone, c.fiscal_code, c.vat_number]
        .filter(Boolean)
        .some((v) => v!.toLowerCase().includes(needle))
  );

  async function createLoginAndContinue(customer: CustomerRead) {
    setBusy(true);
    setLoginError(null);
    try {
      const res = await fetch(`/api/proxy/customers/${customer.id}/account`, { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const updated = (await res.json()) as CustomerRead;
      onLoginCreated();
      setNeedsLogin(null);
      onPick(updated);
    } catch (err: any) {
      setLoginError(err.message || "Impossibile creare l'accesso.");
    } finally {
      setBusy(false);
    }
  }

  if (needsLogin) {
    return (
      <div className="p-4 rounded-xl border border-amber-500/30 bg-amber-500/10 space-y-3">
        <p className="text-sm font-semibold text-amber-300 light:text-amber-700">
          {needsLogin.display_name} non ha ancora un accesso alla sua area
        </p>
        <p className="text-xs text-slate-300 light:text-slate-600">
          Senza accesso non potrebbe pagare la pratica.
          {mode === "admin" ? (
            <>
              {" "}Creiamo l&apos;account su <strong>{needsLogin.email}</strong> e gli mandiamo l&apos;email per impostare la
              password, poi apri la pratica.
            </>
          ) : (
            " Per creargli l'accesso scrivi al Supporto."
          )}
        </p>
        {loginError && <p className="text-xs text-rose-400">{loginError}</p>}
        <div className="flex flex-wrap gap-2">
          {mode === "admin" && (
            <button
              onClick={() => createLoginAndContinue(needsLogin)}
              disabled={busy}
              className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-bold text-white cursor-pointer disabled:opacity-50"
            >
              {busy ? "Creazione..." : "Crea l'accesso e continua"}
            </button>
          )}
          <button
            onClick={() => onPick(needsLogin)}
            className="px-4 py-2 rounded-xl bg-white/10 light:bg-slate-900/5 text-xs font-semibold text-slate-200 light:text-slate-700 cursor-pointer"
          >
            Continua comunque
          </button>
          <button onClick={() => setNeedsLogin(null)} className="px-3 py-2 text-xs text-slate-400 cursor-pointer">
            Indietro
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <input
        autoFocus
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Cerca per nome, email, telefono, codice fiscale, partita IVA..."
        className="w-full rounded-lg glass-input px-3 py-2 text-sm focus:border-orange-500"
      />
      {error && <p className="text-xs text-rose-400">{error.message}</p>}
      <div className="max-h-72 overflow-y-auto rounded-xl border border-white/10 light:border-slate-200 divide-y divide-white/5 light:divide-slate-200">
        {matches.length === 0 ? (
          <p className="px-4 py-6 text-center text-xs text-slate-500">
            {customers === undefined ? "Caricamento..." : "Nessun cliente trovato. È nuovo? Usa “Nuovo cliente”."}
          </p>
        ) : (
          matches.slice(0, 60).map((c) => (
            <button
              key={c.id}
              onClick={() => (c.user_id ? onPick(c) : setNeedsLogin(c))}
              className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-left hover:bg-white/5 light:hover:bg-slate-900/5 cursor-pointer"
            >
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-white light:text-slate-900 truncate">{c.display_name}</span>
                <span className="block text-[11px] text-slate-500 truncate">
                  {CUSTOMER_KIND_LABELS[c.kind] ?? c.kind}
                  {c.email ? ` · ${c.email}` : ""}
                  {c.fiscal_code ? ` · ${c.fiscal_code}` : ""}
                  {!c.user_id && <span className="text-amber-400"> · senza accesso</span>}
                </span>
              </span>
              <span className="text-[11px] font-semibold text-orange-400 shrink-0">Attiva contratti →</span>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

function MyCustomersList({
  customers,
  error,
  expandedCustomerId,
  onToggle,
  onActivate,
  onOpenWizard,
}: {
  customers: CustomerRead[] | undefined;
  error: Error | null;
  expandedCustomerId: string | null;
  onToggle: (id: string) => void;
  onActivate: (customer: CustomerRead) => void;
  onOpenWizard: (customer: CustomerRead, target: WizardTarget) => void;
}) {
  const [search, setSearch] = useState("");
  const needle = search.trim().toLowerCase();
  const filtered = (customers ?? []).filter(
    (c) =>
      !needle ||
      [c.display_name, c.email, c.phone, c.fiscal_code].filter(Boolean).some((v) => v!.toLowerCase().includes(needle))
  );
  const pagination = usePagination(filtered);

  if (error) return <p className="text-sm text-rose-400">{error.message}</p>;

  return (
    <div className="space-y-3">
      {(customers?.length ?? 0) > 5 && (
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Cerca tra i tuoi clienti..."
          className="w-full max-w-md rounded-lg glass-input px-3 py-2 text-sm focus:border-orange-500"
        />
      )}
      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 divide-y divide-white/5 light:divide-slate-200 overflow-hidden">
        {customers === undefined ? (
          <p className="text-center py-8 text-slate-500 text-sm">Caricamento...</p>
        ) : filtered.length === 0 ? (
          <p className="text-center py-8 text-slate-500 text-sm">
            {customers.length === 0 ? "Non hai ancora nessun cliente: inizia da “Nuovo cliente”." : "Nessun cliente trovato."}
          </p>
        ) : (
          pagination.pageItems.map((c) => (
            <div key={c.id}>
              <div className="p-4 sm:p-5 flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-white light:text-slate-900">{c.display_name}</span>
                    {c.email_verified ? (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
                        Account attivo
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-amber-500/10 text-amber-400 border-amber-500/20">
                        In attesa di primo accesso
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    {CUSTOMER_KIND_LABELS[c.kind] ?? c.kind} · {c.email}
                    {c.phone ? ` · ${c.phone}` : ""}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => onToggle(c.id)}
                    className="px-3 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer"
                  >
                    {expandedCustomerId === c.id ? "Nascondi pratiche" : "Pratiche"}
                  </button>
                  <button
                    onClick={() => onActivate(c)}
                    className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-white text-xs font-bold shadow-lg shadow-orange-500/20 transition cursor-pointer"
                  >
                    + Attiva contratti
                  </button>
                </div>
              </div>
              {expandedCustomerId === c.id && (
                <div className="px-4 sm:px-5 pb-5">
                  <ContractRequestsList mode="promoter" customerId={c.id} onOpenWizard={(target) => onOpenWizard(c, target)} />
                </div>
              )}
            </div>
          ))
        )}
      </div>
      <Pagination {...pagination} label="clienti" />
    </div>
  );
}
