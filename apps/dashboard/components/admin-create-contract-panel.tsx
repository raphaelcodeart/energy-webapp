"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type {
  AgentListItemRead,
  ContractRead,
  CustomerDetailRead,
  CustomerRead,
  ProductCatalogRead,
} from "@/lib/types";

const KIND_LABELS: Record<string, string> = {
  PRIVATE: "Privato",
  SOLE_PROPRIETOR: "Partita IVA",
  COMPANY: "Azienda",
  CONDOMINIUM: "Condominio",
};
const PRIVATE_LIKE = new Set(["PRIVATE", "SOLE_PROPRIETOR"]);

async function fetchCustomers(): Promise<CustomerRead[]> {
  const res = await fetch("/api/proxy/customers");
  if (!res.ok) throw new Error("Impossibile caricare i clienti.");
  return res.json();
}

async function fetchCustomerDetail(id: string): Promise<CustomerDetailRead> {
  const res = await fetch(`/api/proxy/customers/${id}`);
  if (!res.ok) throw new Error("Impossibile caricare il cliente.");
  return res.json();
}

async function fetchProducts(): Promise<ProductCatalogRead[]> {
  const res = await fetch("/api/proxy/products");
  if (!res.ok) throw new Error("Impossibile caricare i prodotti.");
  return res.json();
}

async function fetchAgents(): Promise<AgentListItemRead[]> {
  const res = await fetch("/api/proxy/network/agents");
  if (!res.ok) throw new Error("Impossibile caricare i promoter.");
  return res.json();
}

export function AdminCreateContractPanel({ onCreated }: { onCreated: (contract: ContractRead) => void }) {
  const { data: customers } = useQuery({ queryKey: ["admin", "customers"], queryFn: fetchCustomers });
  const { data: products } = useQuery({ queryKey: ["admin", "products"], queryFn: fetchProducts });
  const { data: agents } = useQuery({ queryKey: ["admin", "agents"], queryFn: fetchAgents });

  const [customerMode, setCustomerMode] = useState<"existing" | "new">("new");

  // Existing customer selection
  const [selectedCustomerId, setSelectedCustomerId] = useState("");
  const { data: selectedCustomerDetail } = useQuery({
    queryKey: ["admin", "customers", "detail", selectedCustomerId],
    queryFn: () => fetchCustomerDetail(selectedCustomerId),
    enabled: !!selectedCustomerId,
  });
  const [selectedSupplyPointId, setSelectedSupplyPointId] = useState("");

  // New customer fields
  const [kind, setKind] = useState("PRIVATE");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [pec, setPec] = useState("");
  const [fiscalCode, setFiscalCode] = useState("");
  const [vatNumber, setVatNumber] = useState("");

  // New supply point fields (required for a new customer -- a contract always
  // needs one; existing customers may already have one to pick instead)
  const [energyType, setEnergyType] = useState("ELECTRICITY");
  const [street, setStreet] = useState("");
  const [city, setCity] = useState("");
  const [province, setProvince] = useState("");
  const [postalCode, setPostalCode] = useState("");

  // Contract fields
  const [productVersionId, setProductVersionId] = useState("");
  const [producerAgentId, setProducerAgentId] = useState("");
  const [notes, setNotes] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const energyProducts = (products ?? []).filter((p) => p.status === "ACTIVE" && p.current_version);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitError(null);
    setSubmitting(true);
    try {
      let customerId = selectedCustomerId;
      let supplyPointId = selectedSupplyPointId;

      if (customerMode === "new") {
        const customerRes = await fetch("/api/proxy/customers", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            kind,
            email,
            phone: phone || null,
            pec: pec || null,
            fiscal_code: fiscalCode || null,
            vat_number: vatNumber || null,
            first_name: PRIVATE_LIKE.has(kind) ? firstName : null,
            last_name: PRIVATE_LIKE.has(kind) ? lastName : null,
            company_name: PRIVATE_LIKE.has(kind) ? null : companyName,
          }),
        });
        if (!customerRes.ok) throw new Error(await customerRes.text());
        const newCustomer = (await customerRes.json()) as CustomerRead;
        customerId = newCustomer.id;

        const supplyPointRes = await fetch(`/api/proxy/customers/${customerId}/supply-points`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            energy_type: energyType,
            street,
            city,
            province,
            postal_code: postalCode,
            country: "IT",
          }),
        });
        if (!supplyPointRes.ok) throw new Error(await supplyPointRes.text());
        const newSupplyPoint = await supplyPointRes.json();
        supplyPointId = newSupplyPoint.id;
      }

      if (!customerId || !supplyPointId) {
        throw new Error("Seleziona un cliente e un punto di fornitura.");
      }

      const contractRes = await fetch("/api/proxy/contracts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_id: customerId,
          supply_point_id: supplyPointId,
          product_version_id: productVersionId,
          producer_agent_id: producerAgentId,
          notes: notes || null,
        }),
      });
      if (!contractRes.ok) throw new Error(await contractRes.text());
      const newContract = (await contractRes.json()) as ContractRead;

      onCreated(newContract);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err: any) {
      setSubmitError(err.message || "Impossibile creare il contratto.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto glass-card rounded-2xl p-8 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
      <h3 className="text-lg font-semibold text-white light:text-slate-900 mb-2">Crea un Nuovo Contratto</h3>
      <p className="text-xs text-slate-400 light:text-slate-500 mb-6">
        Collega un cliente (nuovo o esistente), un&apos;offerta e il promoter/venditore che ha originato la vendita.
      </p>

      {success && (
        <div className="p-4 mb-6 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-center animate-scale-up">
          Contratto creato con successo.
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Customer mode */}
        <div className="flex gap-2">
          <button type="button" onClick={() => setCustomerMode("new")}
            className={`flex-1 px-4 py-2 rounded-xl text-xs font-semibold transition cursor-pointer border ${
              customerMode === "new"
                ? "bg-gradient-to-r from-orange-600 to-amber-500 text-white border-transparent"
                : "bg-white/5 light:bg-slate-900/5 text-slate-400 light:text-slate-500 border-white/5 light:border-slate-200"
            }`}>
            Nuovo Cliente
          </button>
          <button type="button" onClick={() => setCustomerMode("existing")}
            className={`flex-1 px-4 py-2 rounded-xl text-xs font-semibold transition cursor-pointer border ${
              customerMode === "existing"
                ? "bg-gradient-to-r from-orange-600 to-amber-500 text-white border-transparent"
                : "bg-white/5 light:bg-slate-900/5 text-slate-400 light:text-slate-500 border-white/5 light:border-slate-200"
            }`}>
            Cliente Esistente
          </button>
        </div>

        {customerMode === "existing" ? (
          <div className="space-y-4">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Cliente</label>
              <select required value={selectedCustomerId} onChange={(e) => { setSelectedCustomerId(e.target.value); setSelectedSupplyPointId(""); }}
                className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                <option value="">— Seleziona cliente —</option>
                {(customers ?? []).map((c) => (
                  <option key={c.id} value={c.id}>{c.display_name} ({c.email})</option>
                ))}
              </select>
            </div>
            {selectedCustomerId && (
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Punto di Fornitura</label>
                <select required value={selectedSupplyPointId} onChange={(e) => setSelectedSupplyPointId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                  <option value="">— Seleziona punto di fornitura —</option>
                  {(selectedCustomerDetail?.supply_points ?? []).map((sp) => (
                    <option key={sp.id} value={sp.id}>{sp.label ?? sp.energy_type} ({sp.pod_code ?? sp.pdr_code ?? "—"})</option>
                  ))}
                </select>
                {selectedCustomerDetail && selectedCustomerDetail.supply_points.length === 0 && (
                  <p className="text-[11px] text-amber-400">Questo cliente non ha punti di fornitura. Aggiungine uno dalla sua scheda in Anagrafiche Clienti.</p>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Tipologia Cliente</label>
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
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Nome Cliente</label>
                  <input required value={firstName} onChange={(e) => setFirstName(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Cognome Cliente</label>
                  <input required value={lastName} onChange={(e) => setLastName(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
              </div>
            ) : (
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Ragione Sociale</label>
                <input required value={companyName} onChange={(e) => setCompanyName(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
              </div>
            )}

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

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Email Cliente</label>
                <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Cellulare</label>
                <input value={phone} onChange={(e) => setPhone(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">PEC (opzionale)</label>
              <input type="email" value={pec} onChange={(e) => setPec(e.target.value)}
                placeholder="nome@pec.it"
                className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
            </div>

            <div className="pt-2 border-t border-white/5 light:border-slate-200">
              <p className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase mb-3">Punto di Fornitura</p>
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Tipo Energia</label>
                  <select value={energyType} onChange={(e) => setEnergyType(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                    <option value="ELECTRICITY">Luce</option>
                    <option value="GAS">Gas</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Indirizzo</label>
                  <input required value={street} onChange={(e) => setStreet(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Città</label>
                  <input required value={city} onChange={(e) => setCity(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Prov.</label>
                  <input required maxLength={2} value={province} onChange={(e) => setProvince(e.target.value.toUpperCase())}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">CAP</label>
                  <input required value={postalCode} onChange={(e) => setPostalCode(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="pt-2 border-t border-white/5 light:border-slate-200 space-y-4">
          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Offerta</label>
            <select required value={productVersionId} onChange={(e) => setProductVersionId(e.target.value)}
              className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
              <option value="">— Seleziona offerta —</option>
              {energyProducts.map((p) => (
                <option key={p.id} value={p.current_version!.id}>{p.current_version!.name} ({p.code})</option>
              ))}
            </select>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Promoter / Venditore</label>
            <select required value={producerAgentId} onChange={(e) => setProducerAgentId(e.target.value)}
              className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
              <option value="">— Seleziona promoter —</option>
              {(agents ?? []).map((a) => (
                <option key={a.id} value={a.id}>{a.display_name} ({a.promoter_code})</option>
              ))}
            </select>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Note (opzionale)</label>
            <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)}
              placeholder="Contesto utile per l'amministrazione: come è arrivato il cliente, promozione di riferimento, preferenze di contatto..."
              className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500 resize-none" />
          </div>
        </div>

        {submitError && (
          <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">
            {submitError}
          </div>
        )}

        <button type="submit" disabled={submitting}
          className="w-full rounded-xl bg-gradient-to-r from-orange-600 to-amber-500 hover:from-orange-500 hover:to-amber-400 py-3 text-sm font-semibold text-white shadow-lg transition duration-300 disabled:opacity-50 cursor-pointer mt-2">
          {submitting ? "Creazione in corso..." : "Genera Contratto"}
        </button>
      </form>
    </div>
  );
}
