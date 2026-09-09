"use client";

import { useState } from "react";
import { ContractDocumentsPanel } from "@/components/contract-documents-panel";
import { friendlyApiError } from "@/lib/api-error";
import type { ContractRead, ProductCatalogRead } from "@/lib/types";

const PROVINCES = [
  "AG", "AL", "AN", "AO", "AR", "AP", "AT", "AV", "BA", "BT", "BL", "BN", "BG", "BI", "BO", "BZ", "BS", "BR",
  "CA", "CL", "CB", "CI", "CE", "CT", "CZ", "CH", "CO", "CS", "CR", "KR", "CN", "EN", "FM", "FE", "FI", "FG",
  "FC", "FR", "GE", "GO", "GR", "IM", "IS", "SP", "LT", "LE", "LC", "LI", "LO", "LU", "MC", "MN", "MS", "MT",
  "VS", "ME", "MI", "MO", "MB", "NA", "NO", "NU", "OG", "OT", "OR", "PD", "PA", "PR", "PC", "PE", "PG", "PU",
  "PV", "PZ", "PN", "PO", "RG", "RA", "RC", "RE", "RI", "RN", "RM", "RO", "SA", "SS", "SV", "SI", "SR", "SO",
  "TA", "TE", "TR", "TO", "TP", "UD", "VA", "VE", "VB", "VC", "VR", "VV", "VI", "VT",
];

const ENERGY_LABELS: Record<string, string> = { ELECTRICITY: "Luce", GAS: "Gas", DUAL_FUEL: "Luce e Gas" };

/** "Attiva Contratto": self-service wizard for a Lial Energy (INTERNAL)
    product -- collects the supply point (address + POD/PDR), creates the
    contract (already submitted, already DOCUMENTS_PENDING by the time this
    call returns -- see contracts/service.py::create_contract_self_service),
    then hands straight into the same ContractDocumentsPanel the "I miei
    Contratti" tab uses, so uploading here or later from that tab is the
    exact same thing. From here on an admin needs exactly two clicks
    (Approva, Conferma pagamento) to reach ACTIVE -- see
    business-rules.md#contract-self-service. */
export function ContractActivationWizard({
  product,
  accountEmail,
  onClose,
  onActivated,
}: {
  product: ProductCatalogRead;
  /** Pre-fills the editable Email field below -- never forced: the customer
      can freely change it to any address, this contract's email need not
      match the account's login email (see contracts/models.py::Contract.email). */
  accountEmail?: string;
  onClose: () => void;
  onActivated: () => void;
}) {
  const v = product.current_version!;
  const needsPod = product.energy_type === "ELECTRICITY" || product.energy_type === "DUAL_FUEL";
  const needsPdr = product.energy_type === "GAS" || product.energy_type === "DUAL_FUEL";

  const [step, setStep] = useState<"supply_point" | "documents">("supply_point");
  const [street, setStreet] = useState("");
  const [city, setCity] = useState("");
  const [province, setProvince] = useState("");
  const [postalCode, setPostalCode] = useState("");
  const [podCode, setPodCode] = useState("");
  const [pdrCode, setPdrCode] = useState("");
  const [meterNumber, setMeterNumber] = useState("");
  const [email, setEmail] = useState(accountEmail ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [contract, setContract] = useState<ContractRead | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/proxy/contracts/mine", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product_version_id: v.id,
          email: email.trim(),
          supply_point: {
            energy_type: product.energy_type,
            pod_code: needsPod ? podCode.toUpperCase() : null,
            pdr_code: needsPdr ? pdrCode.toUpperCase() : null,
            meter_number: meterNumber || null,
            street,
            city,
            province: province.toUpperCase(),
            postal_code: postalCode,
            country: "IT",
          },
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const created: ContractRead = await res.json();
      setContract(created);
      setStep("documents");
      onActivated();
    } catch (err: any) {
      setError(err.message || "Impossibile attivare il contratto.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-lg glass-card rounded-2xl border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 pt-6">
          <div>
            <p className="text-[10px] font-semibold text-orange-400 uppercase tracking-wide">Attiva Contratto</p>
            <h3 className="text-lg font-bold text-white light:text-slate-900">{v.name}</h3>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-slate-400 hover:text-white transition cursor-pointer">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Step indicator */}
        <div className="flex items-center gap-2 px-6 mt-4">
          {(["supply_point", "documents"] as const).map((s, i) => (
            <div key={s} className="flex items-center gap-2 flex-1">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold shrink-0 ${
                step === s ? "bg-orange-600 text-white" : i === 0 && step === "documents" ? "bg-emerald-500/80 text-white" : "bg-white/10 text-slate-400"
              }`}>
                {i === 0 && step === "documents" ? "✓" : i + 1}
              </div>
              <span className={`text-[11px] font-semibold ${step === s ? "text-white light:text-slate-900" : "text-slate-500"}`}>
                {s === "supply_point" ? "Dati fornitura" : "Documenti"}
              </span>
              {i === 0 && <div className="flex-1 h-px bg-white/10" />}
            </div>
          ))}
        </div>

        <div className="p-6">
          {step === "supply_point" && (
            <form onSubmit={handleSubmit} className="space-y-4">
              <p className="text-xs text-slate-400 light:text-slate-500">
                Inserisci i dati del punto di fornitura ({ENERGY_LABELS[product.energy_type ?? ""] ?? "energia"}) da attivare.
              </p>

              <div className="space-y-1">
                <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Email</label>
                <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                  placeholder="nome@esempio.it"
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500" />
                <p className="text-[10px] text-slate-500">
                  Email di riferimento per questo contratto -- puoi usarne una diversa da quella del tuo account.
                </p>
              </div>
              <div className="space-y-1">
                <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Indirizzo</label>
                <input required value={street} onChange={(e) => setStreet(e.target.value)}
                  placeholder="Via/Piazza e numero civico"
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500" />
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2 space-y-1">
                  <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Città</label>
                  <input required value={city} onChange={(e) => setCity(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Prov.</label>
                  <select required value={province} onChange={(e) => setProvince(e.target.value)}
                    className="w-full rounded-xl glass-input px-2 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                    <option value="" disabled>--</option>
                    {PROVINCES.map((p) => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>
              </div>
              <div className="space-y-1">
                <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">CAP</label>
                <input required minLength={5} maxLength={5} value={postalCode}
                  onChange={(e) => setPostalCode(e.target.value.replace(/\D/g, ""))}
                  className="w-full max-w-[140px] rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500" />
              </div>

              <div className="grid grid-cols-2 gap-3 pt-2 border-t border-white/5 light:border-slate-200">
                {needsPod && (
                  <div className="space-y-1">
                    <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Codice POD</label>
                    <input required value={podCode} onChange={(e) => setPodCode(e.target.value)}
                      placeholder="IT001E..."
                      className="w-full rounded-xl glass-input px-3 py-2.5 text-sm uppercase focus:border-orange-500" />
                  </div>
                )}
                {needsPdr && (
                  <div className="space-y-1">
                    <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Codice PDR</label>
                    <input required value={pdrCode} onChange={(e) => setPdrCode(e.target.value)}
                      placeholder="00000000000000"
                      className="w-full rounded-xl glass-input px-3 py-2.5 text-sm uppercase focus:border-orange-500" />
                  </div>
                )}
              </div>
              <div className="space-y-1">
                <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Numero contatore (opzionale)</label>
                <input value={meterNumber} onChange={(e) => setMeterNumber(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500" />
              </div>

              {error && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{error}</div>
              )}

              <button type="submit" disabled={submitting}
                className="w-full rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 py-3 text-sm font-bold text-white shadow-lg shadow-orange-500/20 transition-all duration-200 cursor-pointer disabled:opacity-50">
                {submitting ? "Attivazione in corso..." : "Continua e carica i documenti"}
              </button>
            </form>
          )}

          {step === "documents" && contract && (
            <div className="space-y-4">
              <div className="flex gap-3 p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm">
                <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span>Richiesta creata! Carica i documenti richiesti per completare l&apos;attivazione.</span>
              </div>
              <ContractDocumentsPanel contractId={contract.id} />
              <button onClick={onClose}
                className="w-full rounded-xl bg-white/10 hover:bg-white/20 py-2.5 text-xs font-semibold text-white transition cursor-pointer">
                Continua più tardi -- trovi la richiesta in &ldquo;I miei Contratti&rdquo;
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
