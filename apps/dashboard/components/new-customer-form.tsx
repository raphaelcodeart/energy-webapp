"use client";

import { useState } from "react";
import { friendlyApiError } from "@/lib/api-error";
import type { CustomerRead } from "@/lib/types";

type AgentOption = { id: string; status: string; display_name: string; promoter_code: string };

export const CUSTOMER_KIND_LABELS: Record<string, string> = {
  PRIVATE: "Privato",
  SOLE_PROPRIETOR: "Partita IVA",
  COMPANY: "Azienda",
  CONDOMINIUM: "Condominio",
};
const PRIVATE_LIKE = new Set(["PRIVATE", "SOLE_PROPRIETOR"]);

const inputClass = "w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500";
const labelClass = "text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block";

/** Registering a new customer before opening their first pratica (Session
 *  67), the same form for a promoter and for the administration: both give
 *  the customer a real login and email them the invite to set a password,
 *  so the pratica filled in for them can be paid from their own account.
 *
 *  - promoter: `/network/customers`, the customer goes under the promoter;
 *  - admin: `/customers/with-account`, under the promoter chosen here, or
 *    none (a direct customer of the company).
 */
export function NewCustomerForm({
  mode,
  agents,
  submitLabel = "Registra e attiva i contratti",
  onCreated,
  onCancel,
}: {
  mode: "promoter" | "admin";
  /** Admin only: the active promoters to choose from. */
  agents?: AgentOption[];
  submitLabel?: string;
  onCreated: (customer: CustomerRead, promoterAgentId: string | null) => void;
  onCancel?: () => void;
}) {
  const [kind, setKind] = useState("PRIVATE");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [pec, setPec] = useState("");
  const [fiscalCode, setFiscalCode] = useState("");
  const [vatNumber, setVatNumber] = useState("");
  const [promoterAgentId, setPromoterAgentId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const privateLike = PRIVATE_LIKE.has(kind);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = {
        kind,
        email: email.trim(),
        phone: phone.trim() || null,
        pec: pec.trim() || null,
        fiscal_code: fiscalCode.trim().toUpperCase() || null,
        vat_number: vatNumber.trim() || null,
        first_name: privateLike ? firstName.trim() : null,
        last_name: privateLike ? lastName.trim() : null,
        company_name: privateLike ? null : companyName.trim(),
        ...(mode === "admin" ? { promoter_agent_id: promoterAgentId || null } : {}),
      };
      const res = await fetch(mode === "admin" ? "/api/proxy/customers/with-account" : "/api/proxy/network/customers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      onCreated((await res.json()) as CustomerRead, promoterAgentId || null);
    } catch (err: any) {
      setError(err.message || "Impossibile registrare il cliente.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {Object.entries(CUSTOMER_KIND_LABELS).map(([code, label]) => (
          <button
            key={code}
            type="button"
            onClick={() => setKind(code)}
            className={`px-3 py-2 rounded-xl text-xs font-semibold border transition cursor-pointer ${
              kind === code
                ? "bg-orange-600 border-orange-600 text-white"
                : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {privateLike ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className={labelClass}>Nome</label>
            <input required value={firstName} onChange={(e) => setFirstName(e.target.value)} className={inputClass} />
          </div>
          <div className="space-y-1">
            <label className={labelClass}>Cognome</label>
            <input required value={lastName} onChange={(e) => setLastName(e.target.value)} className={inputClass} />
          </div>
        </div>
      ) : (
        <div className="space-y-1">
          <label className={labelClass}>Ragione sociale</label>
          <input required value={companyName} onChange={(e) => setCompanyName(e.target.value)} className={inputClass} />
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1">
          <label className={labelClass}>Email</label>
          <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass} />
          <p className="text-[10px] text-slate-500">Qui il cliente riceve l&apos;invito a impostare la password e l&apos;avviso per pagare.</p>
        </div>
        <div className="space-y-1">
          <label className={labelClass}>Telefono</label>
          <input value={phone} onChange={(e) => setPhone(e.target.value)} className={inputClass} />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="space-y-1">
          <label className={labelClass}>Codice fiscale</label>
          <input value={fiscalCode} onChange={(e) => setFiscalCode(e.target.value.toUpperCase())} className={`${inputClass} font-mono`} />
        </div>
        <div className="space-y-1">
          <label className={labelClass}>Partita IVA</label>
          <input value={vatNumber} onChange={(e) => setVatNumber(e.target.value)} className={`${inputClass} font-mono`} />
        </div>
        <div className="space-y-1">
          <label className={labelClass}>
            PEC <span className="normal-case font-normal text-slate-500">(facoltativa)</span>
          </label>
          <input type="email" value={pec} onChange={(e) => setPec(e.target.value)} className={inputClass} />
        </div>
      </div>

      {mode === "admin" && (
        <div className="space-y-1">
          <label className={labelClass}>Promoter del cliente</label>
          <select
            value={promoterAgentId}
            onChange={(e) => setPromoterAgentId(e.target.value)}
            className="w-full rounded-xl glass-input px-3 py-2 text-sm bg-slate-900 light:bg-white focus:border-orange-500"
          >
            <option value="">Nessuno: cliente diretto di Lial Energy</option>
            {(agents ?? [])
              .filter((a) => a.status === "ACTIVE")
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.display_name} ({a.promoter_code})
                </option>
              ))}
          </select>
          <p className="text-[10px] text-slate-500">
            Il cliente entra nella rete di questo promoter, come se si fosse iscritto dal suo link: guadagna lui le provvigioni.
          </p>
        </div>
      )}

      {error && <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{error}</div>}

      <div className="flex flex-col sm:flex-row gap-2">
        <button
          type="submit"
          disabled={busy}
          className="flex-1 rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-orange-500/20 transition cursor-pointer disabled:opacity-50"
        >
          {busy ? "Registrazione..." : submitLabel}
        </button>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="rounded-xl bg-white/10 light:bg-slate-900/5 hover:bg-white/20 px-4 py-2.5 text-xs font-semibold text-white light:text-slate-700 transition cursor-pointer"
          >
            Annulla
          </button>
        )}
      </div>
    </form>
  );
}
