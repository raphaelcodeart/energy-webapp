"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ContractActivationWizard } from "@/components/contract-activation-wizard";
import { friendlyApiError } from "@/lib/api-error";
import type { CustomerRead, ProductCatalogRead } from "@/lib/types";

const KIND_LABELS: Record<string, string> = {
  PRIVATE: "Privato",
  SOLE_PROPRIETOR: "Partita IVA",
  COMPANY: "Azienda",
  CONDOMINIUM: "Condominio",
};
const PRIVATE_LIKE = new Set(["PRIVATE", "SOLE_PROPRIETOR"]);

async function fetchMyRecruitedCustomers(): Promise<CustomerRead[]> {
  const res = await fetch("/api/proxy/network/customers/mine");
  if (!res.ok) throw new Error("Impossibile caricare i tuoi clienti.");
  return res.json();
}

async function fetchInternalProducts(): Promise<ProductCatalogRead[]> {
  const res = await fetch("/api/proxy/products");
  if (!res.ok) throw new Error("Impossibile caricare i contratti disponibili.");
  const all: ProductCatalogRead[] = await res.json();
  return all.filter(
    (p) => p.category === "INTERNAL" && p.status === "ACTIVE" && p.current_version && p.current_version.status === "ACTIVE"
  );
}

/** "Miei Clienti": a promoter's own CRM tool -- registers a brand-new
    customer themselves (no self-registration/referral-link click needed,
    see network/service.py::create_recruited_customer) and can immediately
    activate one of the Lial Energy contracts for them, uploading the
    required documents on their behalf. The customer lands in the
    promoter's own network exactly as if they'd registered through their
    referral link, and gets an emailed invite to set their own password --
    their "primo accesso" is a normal click-a-link flow that finds
    everything the promoter already set up for them. */
export function NetworkCustomersPanel() {
  const queryClient = useQueryClient();
  const { data: customers, error: loadError } = useQuery({
    queryKey: ["network", "customers", "mine"],
    queryFn: fetchMyRecruitedCustomers,
  });
  const { data: products } = useQuery({
    queryKey: ["network", "internal-products"],
    queryFn: fetchInternalProducts,
  });

  const [showCreate, setShowCreate] = useState(false);
  const [kind, setKind] = useState("PRIVATE");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [fiscalCode, setFiscalCode] = useState("");
  const [vatNumber, setVatNumber] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [activationTarget, setActivationTarget] = useState<{ customer: CustomerRead; product: ProductCatalogRead } | null>(null);
  const [pickingProductFor, setPickingProductFor] = useState<CustomerRead | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateLoading(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/proxy/network/customers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind,
          email,
          phone: phone || null,
          pec: null,
          fiscal_code: fiscalCode || null,
          vat_number: vatNumber || null,
          first_name: PRIVATE_LIKE.has(kind) ? firstName : null,
          last_name: PRIVATE_LIKE.has(kind) ? lastName : null,
          company_name: PRIVATE_LIKE.has(kind) ? null : companyName,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setShowCreate(false);
      setEmail(""); setPhone(""); setFirstName(""); setLastName(""); setCompanyName(""); setFiscalCode(""); setVatNumber("");
      await queryClient.invalidateQueries({ queryKey: ["network", "customers", "mine"] });
    } catch (err: any) {
      setCreateError(err.message || "Impossibile registrare il cliente.");
    } finally {
      setCreateLoading(false);
    }
  }

  function accountStatusBadge(c: CustomerRead) {
    if (c.email_verified) {
      return <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-emerald-500/10 text-emerald-400 border-emerald-500/20">Account attivo</span>;
    }
    return <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-amber-500/10 text-amber-400 border-amber-500/20">In attesa di primo accesso</span>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-slate-400 light:text-slate-500">
          Registra un nuovo cliente e attivagli subito un contratto -- come un piccolo CRM personale. Il cliente entra
          in automatico nella tua rete, riceve un&apos;email per impostare la password, e trova già tutto pronto al primo accesso.
        </p>
        <button
          onClick={() => { setShowCreate(!showCreate); setCreateError(null); }}
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white shadow-lg shadow-orange-500/20 transition cursor-pointer shrink-0"
        >
          {showCreate ? "Annulla" : "+ Nuovo Cliente"}
        </button>
      </div>

      {showCreate && (
        <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Tipo cliente</label>
              <select value={kind} onChange={(e) => setKind(e.target.value)}
                className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                {Object.entries(KIND_LABELS).map(([code, label]) => (
                  <option key={code} value={code}>{label}</option>
                ))}
              </select>
            </div>

            {PRIVATE_LIKE.has(kind) ? (
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Nome</label>
                  <input required value={firstName} onChange={(e) => setFirstName(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Cognome</label>
                  <input required value={lastName} onChange={(e) => setLastName(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
              </div>
            ) : (
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Ragione sociale</label>
                <input required value={companyName} onChange={(e) => setCompanyName(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Email</label>
                <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                <p className="text-[10px] text-slate-500">Qui arriverà l&apos;invito per impostare la password.</p>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Telefono</label>
                <input value={phone} onChange={(e) => setPhone(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Codice Fiscale</label>
                <input value={fiscalCode} onChange={(e) => setFiscalCode(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Partita IVA</label>
                <input value={vatNumber} onChange={(e) => setVatNumber(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
              </div>
            </div>

            <button type="submit" disabled={createLoading}
              className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
              {createLoading ? "Registrazione..." : "Registra Cliente"}
            </button>
            {createError && (
              <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{createError}</div>
            )}
          </form>
        </div>
      )}

      {loadError && <p className="text-sm text-rose-400">Impossibile caricare i tuoi clienti.</p>}

      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 divide-y divide-white/5 light:divide-slate-200 overflow-hidden">
        {customers === undefined ? (
          <p className="text-center py-8 text-slate-500 text-sm">Caricamento...</p>
        ) : customers.length === 0 ? (
          <p className="text-center py-8 text-slate-500 text-sm">Non hai ancora registrato nessun cliente.</p>
        ) : (
          customers.map((c) => (
            <div key={c.id} className="p-5 flex flex-wrap items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-white light:text-slate-900">{c.display_name}</span>
                  {accountStatusBadge(c)}
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  {KIND_LABELS[c.kind] ?? c.kind} · {c.email}{c.phone ? ` · ${c.phone}` : ""}
                </p>
              </div>
              <button
                onClick={() => setPickingProductFor(c)}
                className="px-4 py-2 rounded-xl bg-orange-600/10 hover:bg-orange-600/20 border border-orange-500/20 text-orange-400 text-xs font-semibold transition cursor-pointer shrink-0"
              >
                Attiva Contratto
              </button>
            </div>
          ))
        )}
      </div>

      {pickingProductFor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white light:text-slate-900">
                Attiva contratto per {pickingProductFor.display_name}
              </h3>
              <button onClick={() => setPickingProductFor(null)} className="p-1.5 rounded-lg hover:bg-white/10 text-slate-400 hover:text-white transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            {products === undefined ? (
              <p className="text-sm text-slate-500 py-6 text-center">Caricamento contratti...</p>
            ) : products.length === 0 ? (
              <p className="text-sm text-slate-500 py-6 text-center">Nessun contratto Lial Energy disponibile al momento.</p>
            ) : (
              <div className="space-y-2">
                {products.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => { setActivationTarget({ customer: pickingProductFor, product: p }); setPickingProductFor(null); }}
                    className="w-full flex items-center justify-between gap-3 p-3 rounded-xl border border-white/10 light:border-slate-200 hover:border-orange-500/40 hover:bg-white/5 transition cursor-pointer text-left"
                  >
                    <span className="text-sm font-semibold text-white light:text-slate-900">{p.current_version!.name}</span>
                    <svg className="w-4 h-4 text-orange-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {activationTarget && (
        <ContractActivationWizard
          product={activationTarget.product}
          accountEmail={activationTarget.customer.email}
          customerId={activationTarget.customer.id}
          onClose={() => setActivationTarget(null)}
          onActivated={() => queryClient.invalidateQueries({ queryKey: ["network", "customers", "mine"] })}
        />
      )}
    </div>
  );
}
