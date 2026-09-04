"use client";

import { Fragment, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PhotoUpload } from "@/components/photo-upload";
import { friendlyApiError } from "@/lib/api-error";
import { downloadCsv } from "@/lib/csv-export";
import type { AgentListItemRead, ContractRead, CustomerDetailRead, CustomerRead } from "@/lib/types";

const CONTRACT_STATUS_LABELS: Record<string, string> = {
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

function contractStatusColor(status: string): string {
  if (status === "ACTIVE" || status === "RENEWED") return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
  if (status === "REJECTED" || status === "CANCELLED") return "bg-rose-500/10 text-rose-400 border-rose-500/20";
  if (status === "DRAFT") return "bg-slate-500/10 text-slate-400 border-slate-500/20";
  return "bg-amber-500/10 text-amber-400 border-amber-500/20";
}

async function fetchAllContracts(): Promise<ContractRead[]> {
  const res = await fetch("/api/proxy/contracts");
  if (!res.ok) throw new Error("Impossibile caricare i contratti.");
  return res.json();
}

async function fetchCustomers(): Promise<CustomerRead[]> {
  const res = await fetch("/api/proxy/customers");
  if (!res.ok) throw new Error("Impossibile caricare i clienti.");
  return res.json();
}

async function fetchCustomerDetail(id: string): Promise<CustomerDetailRead> {
  const res = await fetch(`/api/proxy/customers/${id}`);
  if (!res.ok) throw new Error("Impossibile caricare i dettagli del cliente.");
  return res.json();
}

async function fetchAgentsForReassign(): Promise<AgentListItemRead[]> {
  const res = await fetch("/api/proxy/network/agents");
  if (!res.ok) throw new Error("Impossibile caricare i promoter.");
  return res.json();
}

function CustomerAvatar({ url, size = 36 }: { url: string | null; size?: number }) {
  return (
    <div
      className="rounded-full overflow-hidden border border-white/10 light:border-slate-200 bg-slate-800 light:bg-slate-100 flex items-center justify-center shrink-0"
      style={{ width: size, height: size }}
    >
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element -- externally-hosted, variable-source uploaded photo
        <img src={url} alt="" className="w-full h-full object-cover" />
      ) : (
        <svg className="w-1/2 h-1/2 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
        </svg>
      )}
    </div>
  );
}

const KIND_LABELS: Record<string, string> = {
  PRIVATE: "Privato",
  SOLE_PROPRIETOR: "Partita IVA",
  COMPANY: "Azienda",
  CONDOMINIUM: "Condominio",
};

const PRIVATE_LIKE = new Set(["PRIVATE", "SOLE_PROPRIETOR"]);

export function AdminCustomersPanel({ initialActiveOnly = false }: { initialActiveOnly?: boolean } = {}) {
  const queryClient = useQueryClient();
  const { data: customers, error: loadError } = useQuery({
    queryKey: ["admin", "customers"],
    queryFn: fetchCustomers,
  });
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState("");
  const [activeOnly, setActiveOnly] = useState(initialActiveOnly);

  // View popup
  const [viewingId, setViewingId] = useState<string | null>(null);
  const { data: viewingDetail, error: viewError } = useQuery({
    queryKey: ["admin", "customers", "detail", viewingId],
    queryFn: () => fetchCustomerDetail(viewingId!),
    enabled: viewingId !== null,
  });
  const { data: allContracts } = useQuery({
    queryKey: ["admin", "contracts", "all"],
    queryFn: fetchAllContracts,
  });
  const customerIdsWithActiveContract = new Set(
    (allContracts ?? []).filter((c) => c.status === "ACTIVE" || c.status === "RENEWED").map((c) => c.customer_id)
  );
  const [expandedContractId, setExpandedContractId] = useState<string | null>(null);
  const customerContracts = (allContracts ?? []).filter((c) => c.customer_id === viewingId);

  // Edit form
  const [editingCustomer, setEditingCustomer] = useState<CustomerRead | null>(null);
  const [editEmail, setEditEmail] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editPec, setEditPec] = useState("");
  const [editFirstName, setEditFirstName] = useState("");
  const [editLastName, setEditLastName] = useState("");
  const [editCompanyName, setEditCompanyName] = useState("");
  const [editFiscalCode, setEditFiscalCode] = useState("");
  const [editVatNumber, setEditVatNumber] = useState("");
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editPhotoUrl, setEditPhotoUrl] = useState<string | null>(null);

  const { data: editingDetail } = useQuery({
    queryKey: ["admin", "customers", "detail", editingCustomer?.id],
    queryFn: () => fetchCustomerDetail(editingCustomer!.id),
    enabled: !!editingCustomer,
  });
  const { data: agentsForReassign } = useQuery({
    queryKey: ["admin", "agents", "for-reassign"],
    queryFn: fetchAgentsForReassign,
  });

  // Reassign promoter
  const [reassignAgentId, setReassignAgentId] = useState("");
  const [reassignReason, setReassignReason] = useState("");
  const [reassignLoading, setReassignLoading] = useState(false);
  const [reassignError, setReassignError] = useState<string | null>(null);
  const [reassignSuccess, setReassignSuccess] = useState(false);

  async function handleReassign(e: React.FormEvent) {
    e.preventDefault();
    if (!editingCustomer || !reassignAgentId) return;
    setReassignLoading(true);
    setReassignError(null);
    try {
      const res = await fetch(`/api/proxy/customers/${editingCustomer.id}/reassign-promoter`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_agent_id: reassignAgentId, reason: reassignReason }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setReassignSuccess(true);
      setReassignAgentId("");
      setReassignReason("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "customers", "detail", editingCustomer.id] });
      setTimeout(() => setReassignSuccess(false), 3000);
    } catch (err: any) {
      setReassignError(err.message || "Impossibile riassegnare il promoter.");
    } finally {
      setReassignLoading(false);
    }
  }

  function openEdit(c: CustomerRead) {
    setEditEmail(c.email);
    setEditPhone(c.phone ?? "");
    setEditPec(c.pec ?? "");
    setEditFiscalCode(c.fiscal_code ?? "");
    setEditVatNumber(c.vat_number ?? "");
    const parts = c.display_name.trim().split(/\s+/);
    if (PRIVATE_LIKE.has(c.kind)) {
      setEditFirstName(parts.slice(0, -1).join(" ") || parts[0] || "");
      setEditLastName(parts.length > 1 ? parts[parts.length - 1]! : "");
      setEditCompanyName("");
    } else {
      setEditFirstName("");
      setEditLastName("");
      setEditCompanyName(c.display_name);
    }
    setEditError(null);
    setEditPhotoUrl(c.photo_url);
    setReassignAgentId("");
    setReassignReason("");
    setReassignError(null);
    setEditingCustomer(c);
  }

  async function handleEditSave(e: React.FormEvent) {
    e.preventDefault();
    if (!editingCustomer) return;
    setEditLoading(true);
    setEditError(null);
    try {
      const res = await fetch(`/api/proxy/customers/${editingCustomer.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: editEmail,
          phone: editPhone || null,
          pec: editPec || null,
          fiscal_code: editFiscalCode || null,
          vat_number: editVatNumber || null,
          first_name: PRIVATE_LIKE.has(editingCustomer.kind) ? editFirstName : null,
          last_name: PRIVATE_LIKE.has(editingCustomer.kind) ? editLastName : null,
          company_name: PRIVATE_LIKE.has(editingCustomer.kind) ? null : editCompanyName,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setEditingCustomer(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "customers"] });
    } catch (err: any) {
      setEditError(err.message || "Impossibile salvare le modifiche.");
    } finally {
      setEditLoading(false);
    }
  }

  // Create form state
  const [kind, setKind] = useState("PRIVATE");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [pec, setPec] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [fiscalCode, setFiscalCode] = useState("");
  const [vatNumber, setVatNumber] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateLoading(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/proxy/customers", {
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
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setShowCreate(false);
      setEmail("");
      setPhone("");
      setPec("");
      setFirstName("");
      setLastName("");
      setCompanyName("");
      setFiscalCode("");
      setVatNumber("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "customers"] });
    } catch (err: any) {
      setCreateError(err.message || "Impossibile creare il cliente.");
    } finally {
      setCreateLoading(false);
    }
  }

  const filtered = (customers ?? []).filter(
    (c) =>
      (!activeOnly || customerIdsWithActiveContract.has(c.id)) &&
      (c.display_name.toLowerCase().includes(search.toLowerCase()) ||
        c.email.toLowerCase().includes(search.toLowerCase()))
  );

  const handleExportCsv = () => {
    downloadCsv(
      `clienti_${new Date().toISOString().slice(0, 10)}`,
      ["ID", "Nome", "Tipologia", "Email", "Telefono", "Codice Fiscale", "Partita IVA", "Ha un contratto attivo"],
      filtered.map((c) => [
        c.id, c.display_name, c.kind, c.email, c.phone ?? "", c.fiscal_code ?? "", c.vat_number ?? "",
        customerIdsWithActiveContract.has(c.id) ? "Sì" : "No",
      ])
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row gap-4 items-center justify-between">
        <div className="w-full sm:max-w-xs relative">
          <input
            type="text"
            placeholder="Cerca cliente..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-xl glass-input pl-10 pr-4 py-2 text-xs focus:border-orange-500"
          />
          <svg className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <label className="flex items-center gap-1.5 text-xs text-slate-400 light:text-slate-500 cursor-pointer whitespace-nowrap">
            <input type="checkbox" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} className="cursor-pointer" />
            Solo con contratto attivo
          </label>
          <button
            onClick={handleExportCsv}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            CSV
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white shadow-lg shadow-orange-500/20 transition cursor-pointer"
          >
            + Nuovo Cliente
          </button>
        </div>
      </div>

      {loadError && <p className="text-sm text-rose-400">Impossibile caricare i clienti.</p>}

      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold">
                <th className="py-3 px-6"></th>
                <th className="py-3 px-6">Nominativo</th>
                <th className="py-3 px-6">Tipo</th>
                <th className="py-3 px-6">Email</th>
                <th className="py-3 px-6">Telefono</th>
                <th className="py-3 px-6 text-right">Azioni</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {customers === undefined ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-slate-500">Caricamento...</td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-slate-500">Nessun cliente trovato.</td>
                </tr>
              ) : (
                filtered.map((c) => (
                  <tr key={c.id} className="text-slate-300 light:text-slate-600 hover:bg-white/5 transition-colors">
                    <td className="py-4 px-6"><CustomerAvatar url={c.photo_url} /></td>
                    <td className="py-4 px-6">
                      <p className="font-medium text-white light:text-slate-900">{c.display_name}</p>
                      <p className="text-[10px] text-slate-500">{c.email}</p>
                      <p className="text-[10px] text-slate-500">Iscritto: {new Date(c.created_at).toLocaleDateString("it-IT")}</p>
                    </td>
                    <td className="py-4 px-6">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-amber-500/10 text-amber-400 border-amber-500/20">
                        {KIND_LABELS[c.kind] ?? c.kind}
                      </span>
                    </td>
                    <td className="py-4 px-6">{c.email}</td>
                    <td className="py-4 px-6">{c.phone ?? "—"}</td>
                    <td className="py-4 px-6">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => setViewingId(c.id)}
                          title="Mostra dettagli"
                          className="p-1.5 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer"
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                          </svg>
                        </button>
                        <button
                          onClick={() => openEdit(c)}
                          title="Modifica cliente"
                          className="p-1.5 rounded-lg bg-orange-600/10 hover:bg-orange-600/20 border border-orange-500/20 text-orange-400 transition cursor-pointer"
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                          </svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white light:text-slate-900">Nuovo Cliente</h3>
              <button
                onClick={() => setShowCreate(false)}
                className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <form onSubmit={handleCreate} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Tipo cliente</label>
                <select
                  value={kind}
                  onChange={(e) => setKind(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500"
                >
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
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Telefono</label>
                  <input value={phone} onChange={(e) => setPhone(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">PEC</label>
                <input type="email" value={pec} onChange={(e) => setPec(e.target.value)}
                  placeholder="nome@pec.it"
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
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

              {createError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{createError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setShowCreate(false)}
                  className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer">
                  Annulla
                </button>
                <button type="submit" disabled={createLoading}
                  className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                  {createLoading ? "Creazione..." : "Crea Cliente"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {viewingId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white light:text-slate-900">Dettagli Cliente</h3>
              <button onClick={() => setViewingId(null)}
                className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {viewError && <p className="text-sm text-rose-400">Impossibile caricare i dettagli.</p>}
            {!viewingDetail && !viewError && <p className="text-sm text-slate-500 text-center py-8">Caricamento...</p>}

            {viewingDetail && (
              <div className="space-y-4 text-sm">
                <div>
                  <p className="text-lg font-semibold text-white light:text-slate-900">{viewingDetail.display_name}</p>
                  <span className="inline-block mt-1 px-2 py-0.5 rounded-full text-[10px] font-bold border bg-amber-500/10 text-amber-400 border-amber-500/20">
                    {KIND_LABELS[viewingDetail.kind] ?? viewingDetail.kind}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-4 p-4 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/5 light:border-slate-200">
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-semibold">Email</span>
                    <p className="text-slate-200 light:text-slate-700">{viewingDetail.email}</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-semibold">Telefono</span>
                    <p className="text-slate-200 light:text-slate-700">{viewingDetail.phone ?? "—"}</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-semibold">PEC</span>
                    <p className="text-slate-200 light:text-slate-700">{viewingDetail.pec ?? "—"}</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-semibold">Codice Fiscale</span>
                    <p className="font-mono text-xs text-slate-200 light:text-slate-700">{viewingDetail.fiscal_code ?? "—"}</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase font-semibold">Partita IVA</span>
                    <p className="font-mono text-xs text-slate-200 light:text-slate-700">{viewingDetail.vat_number ?? "—"}</p>
                  </div>
                </div>

                <div>
                  <p className="text-[10px] text-slate-500 uppercase font-semibold mb-2">Contratti</p>
                  {customerContracts.length === 0 ? (
                    <p className="text-xs text-slate-500">Nessun contratto per questo cliente.</p>
                  ) : (
                    <div className="rounded-xl border border-white/5 light:border-slate-200 overflow-hidden">
                      <table className="w-full text-left text-xs">
                        <thead>
                          <tr className="bg-white/5 light:bg-slate-900/5 text-slate-400 light:text-slate-500">
                            <th className="py-2 px-3 font-semibold">Prodotto</th>
                            <th className="py-2 px-3 font-semibold">Stato</th>
                            <th className="py-2 px-3 font-semibold">Scadenza</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5 light:divide-slate-200">
                          {customerContracts.map((c) => (
                            <Fragment key={c.id}>
                              <tr
                                onClick={() => setExpandedContractId(expandedContractId === c.id ? null : c.id)}
                                className="cursor-pointer hover:bg-white/5 transition-colors text-slate-300 light:text-slate-600"
                              >
                                <td className="py-2 px-3">
                                  <div className="font-medium text-white light:text-slate-900">{c.product_name ?? "Prodotto"}</div>
                                  <div className="text-slate-500">{c.supply_point_label ?? ""}</div>
                                </td>
                                <td className="py-2 px-3">
                                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${contractStatusColor(c.status)}`}>
                                    {CONTRACT_STATUS_LABELS[c.status] ?? c.status}
                                  </span>
                                </td>
                                <td className="py-2 px-3">
                                  {c.expires_at ? new Date(c.expires_at).toLocaleDateString("it-IT") : "—"}
                                </td>
                              </tr>
                              {expandedContractId === c.id && (
                                <tr className="bg-white/5 light:bg-slate-900/5">
                                  <td colSpan={3} className="py-3 px-3 text-slate-300 light:text-slate-600 space-y-1">
                                    <div><span className="text-slate-500">Creato:</span> {new Date(c.created_at).toLocaleDateString("it-IT")}</div>
                                    {c.activated_at && (
                                      <div><span className="text-slate-500">Attivato:</span> {new Date(c.activated_at).toLocaleDateString("it-IT")}</div>
                                    )}
                                    {c.notes && <div><span className="text-slate-500">Note:</span> {c.notes}</div>}
                                    <div className="font-mono text-[10px] text-slate-500">{c.id}</div>
                                  </td>
                                </tr>
                              )}
                            </Fragment>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {viewingDetail.addresses.length > 0 && (
                  <div>
                    <p className="text-[10px] text-slate-500 uppercase font-semibold mb-2">Indirizzi</p>
                    <div className="space-y-2">
                      {viewingDetail.addresses.map((a) => (
                        <div key={a.id} className="p-3 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/5 light:border-slate-200 text-xs text-slate-300 light:text-slate-600">
                          {a.street}, {a.postal_code} {a.city} ({a.province}) — {a.country}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {viewingDetail.supply_points.length > 0 && (
                  <div>
                    <p className="text-[10px] text-slate-500 uppercase font-semibold mb-2">Punti di Fornitura</p>
                    <div className="space-y-2">
                      {viewingDetail.supply_points.map((sp) => (
                        <div key={sp.id} className="p-3 rounded-xl bg-white/5 light:bg-slate-900/5 border border-white/5 light:border-slate-200 text-xs text-slate-300 light:text-slate-600">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-white light:text-slate-900">{sp.label ?? sp.energy_type}</span>
                            <span className="font-mono text-[10px] text-slate-500">{sp.pod_code ?? sp.pdr_code ?? "—"}</span>
                          </div>
                          <div className="text-[10px] text-slate-500 mt-0.5">{sp.energy_type}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <p className="font-mono text-[10px] text-slate-500 pt-2 border-t border-white/5 light:border-slate-200">{viewingDetail.id}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {editingCustomer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white light:text-slate-900">Modifica Cliente</h3>
              <button onClick={() => setEditingCustomer(null)}
                className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="mb-5 pb-5 border-b border-white/5 light:border-slate-200">
              <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block mb-2">Foto profilo</label>
              <PhotoUpload
                currentUrl={editPhotoUrl}
                uploadPath={`customers/${editingCustomer.id}/photo`}
                onUploaded={(url) => {
                  setEditPhotoUrl(url);
                  queryClient.invalidateQueries({ queryKey: ["admin", "customers"] });
                }}
                alt={editingCustomer.display_name}
              />
            </div>

            <form onSubmit={handleEditSave} className="space-y-4">
              {PRIVATE_LIKE.has(editingCustomer.kind) ? (
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Nome</label>
                    <input required value={editFirstName} onChange={(e) => setEditFirstName(e.target.value)}
                      className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Cognome</label>
                    <input required value={editLastName} onChange={(e) => setEditLastName(e.target.value)}
                      className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                  </div>
                </div>
              ) : (
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Ragione sociale</label>
                  <input required value={editCompanyName} onChange={(e) => setEditCompanyName(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Email</label>
                  <input required type="email" value={editEmail} onChange={(e) => setEditEmail(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Telefono</label>
                  <input value={editPhone} onChange={(e) => setEditPhone(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">PEC</label>
                <input type="email" value={editPec} onChange={(e) => setEditPec(e.target.value)}
                  placeholder="nome@pec.it"
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Codice Fiscale</label>
                  <input value={editFiscalCode} onChange={(e) => setEditFiscalCode(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Partita IVA</label>
                  <input value={editVatNumber} onChange={(e) => setEditVatNumber(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
              </div>

              {editError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{editError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setEditingCustomer(null)}
                  className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer">
                  Annulla
                </button>
                <button type="submit" disabled={editLoading}
                  className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                  {editLoading ? "Salvataggio..." : "Salva Modifiche"}
                </button>
              </div>
            </form>

            <div className="mt-6 pt-5 border-t border-white/5 light:border-slate-200">
              <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block mb-2">Promoter di riferimento</label>
              <p className="text-xs text-slate-400 light:text-slate-500 mb-3">
                Attualmente attribuito a: <span className="font-semibold text-white light:text-slate-900">{editingDetail?.current_promoter_name ?? "—"}</span>
              </p>
              <form onSubmit={handleReassign} className="space-y-3">
                <select
                  required
                  value={reassignAgentId}
                  onChange={(e) => setReassignAgentId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500"
                >
                  <option value="">— Seleziona nuovo promoter —</option>
                  {(agentsForReassign ?? [])
                    .filter((a) => a.id !== editingDetail?.current_promoter_agent_id)
                    .map((a) => (
                      <option key={a.id} value={a.id}>{a.display_name} ({a.promoter_code})</option>
                    ))}
                </select>
                <input
                  required
                  value={reassignReason}
                  onChange={(e) => setReassignReason(e.target.value)}
                  placeholder="Motivo della riassegnazione..."
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
                />
                {reassignError && (
                  <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{reassignError}</div>
                )}
                {reassignSuccess && (
                  <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">Promoter riassegnato con successo.</div>
                )}
                <button type="submit" disabled={reassignLoading}
                  className="w-full px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/10 light:border-slate-300 transition cursor-pointer disabled:opacity-50">
                  {reassignLoading ? "Riassegnazione..." : "Riassegna Promoter"}
                </button>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
