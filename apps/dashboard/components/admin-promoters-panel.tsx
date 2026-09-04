"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PhotoUpload } from "@/components/photo-upload";
import { AdminPromoterNetworkModal } from "@/components/admin-promoter-network-modal";
import { friendlyApiError } from "@/lib/api-error";
import { DEFAULT_ORGANIZATION_ID } from "@/lib/config";
import { downloadCsv } from "@/lib/csv-export";
import type { AgentListItemRead, PromoterCodeRead, RankEvaluationChangeRead, RankRead, RootPromoterCreateResponse } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  ACTIVE: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  SUSPENDED: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  TERMINATED: "bg-rose-500/10 text-rose-400 border-rose-500/20",
  PENDING_APPROVAL: "bg-sky-500/10 text-sky-400 border-sky-500/20",
};
const STATUS_LABELS: Record<string, string> = {
  ACTIVE: "Attivo",
  SUSPENDED: "Sospeso",
  TERMINATED: "Cessato",
  PENDING_APPROVAL: "Da approvare",
};

async function fetchAgents(): Promise<AgentListItemRead[]> {
  const res = await fetch("/api/proxy/network/agents");
  if (!res.ok) throw new Error("Impossibile caricare la rete commerciale.");
  return res.json();
}

async function fetchRanks(): Promise<RankRead[]> {
  const res = await fetch("/api/proxy/commissions/ranks");
  if (!res.ok) throw new Error("Impossibile caricare le qualifiche.");
  return res.json();
}

function AgentAvatar({ url, size = 36 }: { url: string | null; size?: number }) {
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
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4" />
        </svg>
      )}
    </div>
  );
}

export function AdminPromotersPanel({ initialStatusFilter }: { initialStatusFilter?: string } = {}) {
  const queryClient = useQueryClient();
  const { data: agents, error: loadError } = useQuery({
    queryKey: ["admin", "agents"],
    queryFn: fetchAgents,
  });
  const { data: ranks = [] } = useQuery({
    queryKey: ["admin", "ranks"],
    queryFn: fetchRanks,
  });
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState(initialStatusFilter ?? "ALL");

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [promoterCode, setPromoterCode] = useState("");
  const [parentAgentId, setParentAgentId] = useState("");
  const [rankId, setRankId] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const nameById = new Map((agents ?? []).map((a) => [a.id, a.display_name]));

  // Approval workflow -- only network.approve holders (SUPER_ADMIN/
  // ORGANIZATION_ADMIN, the "amministratore principale") can actually
  // succeed here; a plain ADMIN sees the buttons too but the backend 403s,
  // surfaced as approvalError below. Not worth plumbing role info through
  // the session just to hide two buttons the server already guards.
  const [approvalActionId, setApprovalActionId] = useState<string | null>(null);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const [rejectingAgent, setRejectingAgent] = useState<AgentListItemRead | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  // Deactivate/blacklist/reactivate -- "Lavora con noi" auto-activates a
  // promoter immediately (see network/service.py apply_as_promoter), so this
  // is the only way an admin takes that capability back. Blacklist is a
  // stricter deactivation: a blacklisted agent who re-applies goes through
  // the old manual PENDING_APPROVAL/approve flow instead of auto-activating.
  const [agentActionId, setAgentActionId] = useState<string | null>(null);
  const [agentActionError, setAgentActionError] = useState<string | null>(null);

  async function handleSetAgentStatus(agentId: string, patch: { status?: string; is_blacklisted?: boolean }) {
    setAgentActionId(agentId);
    setAgentActionError(null);
    try {
      const res = await fetch(`/api/proxy/network/agents/${agentId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setAgentActionError(err.message || "Operazione non riuscita.");
    } finally {
      setAgentActionId(null);
    }
  }

  // Opens an agent's personal referral link in a new tab -- lazily
  // get-or-created server-side (an agent may never have visited their own
  // dashboard yet, e.g. right after admin approval). The tab is opened
  // BEFORE the fetch resolves so it stays a direct result of the click
  // (popup blockers kill a window.open() that happens after an await).
  const [referralLinkLoadingId, setReferralLinkLoadingId] = useState<string | null>(null);

  async function handleOpenReferralLink(agentId: string) {
    setReferralLinkLoadingId(agentId);
    setAgentActionError(null);
    const newTab = window.open("", "_blank");
    try {
      const res = await fetch(`/api/proxy/network/agents/${agentId}/referral-link`);
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile recuperare il link del promoter."));
      const data: PromoterCodeRead = await res.json();
      const url = new URL(`/r/${data.code}`, window.location.origin);
      url.searchParams.set("org", DEFAULT_ORGANIZATION_ID);
      if (newTab) newTab.location.href = url.toString();
    } catch (err: any) {
      newTab?.close();
      setAgentActionError(err.message || "Impossibile recuperare il link del promoter.");
    } finally {
      setReferralLinkLoadingId(null);
    }
  }

  // Monthly rank evaluation -- same job Celery Beat runs automatically at
  // month-end (see celery_app.py::run_monthly_rank_evaluation_task), triggered
  // here on demand. commissions.evaluate_ranks-gated on the backend (SUPER_ADMIN/
  // ORGANIZATION_ADMIN only); a plain ADMIN sees the button but the backend 403s.
  const [evaluatingRanks, setEvaluatingRanks] = useState(false);
  const [evaluationError, setEvaluationError] = useState<string | null>(null);
  const [evaluationResult, setEvaluationResult] = useState<RankEvaluationChangeRead[] | null>(null);

  async function handleEvaluateRanks() {
    setEvaluatingRanks(true);
    setEvaluationError(null);
    try {
      const res = await fetch("/api/proxy/commissions/rank-evaluation/run", { method: "POST" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const changes: RankEvaluationChangeRead[] = await res.json();
      setEvaluationResult(changes);
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setEvaluationError(err.message || "Impossibile eseguire la valutazione -- solo l'amministratore principale può farlo.");
    } finally {
      setEvaluatingRanks(false);
    }
  }

  async function handleApprove(agentId: string) {
    setApprovalActionId(agentId);
    setApprovalError(null);
    try {
      const res = await fetch(`/api/proxy/network/agents/${agentId}/approve`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: "{}" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setApprovalError(err.message || "Impossibile approvare -- solo l'amministratore principale può farlo.");
    } finally {
      setApprovalActionId(null);
    }
  }

  async function handleReject() {
    if (!rejectingAgent) return;
    setApprovalActionId(rejectingAgent.id);
    setApprovalError(null);
    try {
      const res = await fetch(`/api/proxy/network/agents/${rejectingAgent.id}/reject`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: rejectReason || null }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
      setRejectingAgent(null);
      setRejectReason("");
    } catch (err: any) {
      setApprovalError(err.message || "Impossibile rifiutare -- solo l'amministratore principale può farlo.");
    } finally {
      setApprovalActionId(null);
    }
  }

  // Edit
  const [editingAgent, setEditingAgent] = useState<AgentListItemRead | null>(null);
  const [networkAgent, setNetworkAgent] = useState<AgentListItemRead | null>(null);
  const [editFirstName, setEditFirstName] = useState("");
  const [editLastName, setEditLastName] = useState("");
  const [editStatus, setEditStatus] = useState("ACTIVE");
  const [editRankId, setEditRankId] = useState("");
  const [editPhotoUrl, setEditPhotoUrl] = useState<string | null>(null);
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  function openEdit(a: AgentListItemRead) {
    setEditFirstName(a.first_name ?? "");
    setEditLastName(a.last_name ?? "");
    setEditStatus(a.status);
    setEditRankId(a.current_rank_id ?? "");
    setEditPhotoUrl(a.photo_url);
    setEditError(null);
    setEditingAgent(a);
  }

  async function handleEditSave(e: React.FormEvent) {
    e.preventDefault();
    if (!editingAgent) return;
    setEditLoading(true);
    setEditError(null);
    try {
      const res = await fetch(`/api/proxy/network/agents/${editingAgent.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: editFirstName,
          last_name: editLastName,
          status: editStatus,
          current_rank_id: editRankId || null,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setEditingAgent(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setEditError(err.message || "Impossibile salvare le modifiche.");
    } finally {
      setEditLoading(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateLoading(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/proxy/network/agents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: firstName,
          last_name: lastName,
          promoter_code: promoterCode,
          parent_agent_id: parentAgentId || null,
          current_rank_id: rankId || null,
          customer_email: customerEmail || null,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setShowCreate(false);
      setFirstName("");
      setLastName("");
      setPromoterCode("");
      setParentAgentId("");
      setRankId("");
      setCustomerEmail("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setCreateError(err.message || "Impossibile creare l'agente.");
    } finally {
      setCreateLoading(false);
    }
  }

  // Root promoter bootstrap -- gated on network.approve (SUPER_ADMIN/
  // ORGANIZATION_ADMIN) on the backend, same "not worth hiding it" convention
  // as the approve/reject/evaluate-ranks buttons above. Unlike "+ Nuovo
  // Promoter" (which only ever suggests, PENDING_APPROVAL, no login), this
  // creates a ready-to-use login + ACTIVE parentless agent in one step --
  // the only way to start a brand-new independent branch, since every other
  // signup path requires an existing promoter's referral code.
  const [showCreateRoot, setShowCreateRoot] = useState(false);
  const [rootFirstName, setRootFirstName] = useState("");
  const [rootLastName, setRootLastName] = useState("");
  const [rootEmail, setRootEmail] = useState("");
  const [rootPromoterCode, setRootPromoterCode] = useState("");
  const [rootCreateLoading, setRootCreateLoading] = useState(false);
  const [rootCreateError, setRootCreateError] = useState<string | null>(null);
  const [rootCreateResult, setRootCreateResult] = useState<RootPromoterCreateResponse | null>(null);
  const [rootLinkCopied, setRootLinkCopied] = useState(false);
  const [rootPasswordCopied, setRootPasswordCopied] = useState(false);

  async function handleCreateRoot(e: React.FormEvent) {
    e.preventDefault();
    setRootCreateLoading(true);
    setRootCreateError(null);
    try {
      const res = await fetch("/api/proxy/network/agents/root", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: rootFirstName,
          last_name: rootLastName,
          email: rootEmail,
          promoter_code: rootPromoterCode || null,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const result: RootPromoterCreateResponse = await res.json();
      setShowCreateRoot(false);
      setRootFirstName("");
      setRootLastName("");
      setRootEmail("");
      setRootPromoterCode("");
      setRootCreateResult(result);
      await queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
    } catch (err: any) {
      setRootCreateError(err.message || "Impossibile creare il promoter radice -- solo l'amministratore principale può farlo.");
    } finally {
      setRootCreateLoading(false);
    }
  }

  const filtered = (agents ?? []).filter(
    (a) =>
      (statusFilter === "ALL" || a.status === statusFilter) &&
      (a.display_name.toLowerCase().includes(search.toLowerCase()) ||
        a.promoter_code.toLowerCase().includes(search.toLowerCase()))
  );

  const handleExportCsv = () => {
    downloadCsv(
      `promoter_${new Date().toISOString().slice(0, 10)}`,
      ["ID", "Nome", "Codice Promoter", "Qualifica", "Sponsor", "Stato", "Iscritto il"],
      filtered.map((a) => [
        a.id, a.display_name, a.promoter_code, a.rank_code ?? "",
        a.direct_parent_agent_id ? nameById.get(a.direct_parent_agent_id) ?? a.direct_parent_agent_id : "Radice",
        a.status, a.joined_at,
      ])
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row gap-4 items-center justify-between">
        <div className="w-full sm:max-w-xs relative">
          <input
            type="text"
            placeholder="Cerca promoter o codice..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded-xl glass-input pl-10 pr-4 py-2 text-xs focus:border-orange-500"
          />
          <svg className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-xl glass-input px-3 py-2 text-xs bg-slate-900 light:bg-white focus:border-orange-500"
          >
            <option value="ALL">Tutti gli stati</option>
            <option value="ACTIVE">Solo attivi</option>
            <option value="SUSPENDED">Solo sospesi</option>
            <option value="TERMINATED">Solo cessati</option>
          </select>
          <button
            onClick={handleEvaluateRanks}
            disabled={evaluatingRanks}
            title="Rivaluta il grado di ogni promoter attivo in base al fatturato del mese scorso, come farebbe il job automatico di fine mese"
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
            {evaluatingRanks ? "Valutazione..." : "Valuta gradi ora"}
          </button>
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
            onClick={() => setShowCreateRoot(true)}
            title="Crea un promoter senza sponsor, con accesso già attivo -- l'unico modo di avviare un nuovo ramo indipendente, dato che ogni altra iscrizione richiede il link di un promoter già esistente"
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0H5a2 2 0 01-2-2v-4m6 6h10a2 2 0 002-2v-4" />
            </svg>
            + Promoter Radice
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white shadow-lg shadow-orange-500/20 transition cursor-pointer"
          >
            + Nuovo Promoter
          </button>
        </div>
      </div>

      {loadError && <p className="text-sm text-rose-400">Impossibile caricare la rete commerciale.</p>}
      {approvalError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{approvalError}</div>
      )}
      {agentActionError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{agentActionError}</div>
      )}
      {evaluationError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{evaluationError}</div>
      )}
      {evaluationResult && (
        <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-xs">
          <div className="flex items-center justify-between mb-2">
            <span className="font-semibold text-emerald-400">
              {evaluationResult.length === 0
                ? "Valutazione completata: nessun grado da aggiornare."
                : `Valutazione completata: ${evaluationResult.length} grad${evaluationResult.length === 1 ? "o" : "i"} aggiornat${evaluationResult.length === 1 ? "o" : "i"}.`}
            </span>
            <button
              onClick={() => setEvaluationResult(null)}
              className="text-slate-400 hover:text-white cursor-pointer"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          {evaluationResult.length > 0 && (
            <ul className="space-y-1 text-slate-300 light:text-slate-600">
              {evaluationResult.map((c) => (
                <li key={c.agent_id}>
                  <span className={c.direction === "PROMOTED" ? "text-emerald-400" : "text-amber-400"}>
                    {c.direction === "PROMOTED" ? "▲" : "▼"}
                  </span>{" "}
                  {c.display_name}: {c.previous_rank_code ?? "—"} → {c.new_rank_code}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-white/5 light:border-slate-200 text-slate-400 light:text-slate-500 font-semibold">
                <th className="py-3 px-6"></th>
                <th className="py-3 px-6">Nome</th>
                <th className="py-3 px-6">Codice</th>
                <th className="py-3 px-6">Qualifica</th>
                <th className="py-3 px-6">Sponsor</th>
                <th className="py-3 px-6">Stato</th>
                <th className="py-3 px-6 text-right">Azioni</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 light:divide-slate-200">
              {agents === undefined ? (
                <tr><td colSpan={7} className="text-center py-8 text-slate-500">Caricamento...</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={7} className="text-center py-8 text-slate-500">Nessun promoter trovato.</td></tr>
              ) : (
                filtered.map((a) => (
                  <tr key={a.id} className="text-slate-300 light:text-slate-600 hover:bg-white/5 transition-colors">
                    <td className="py-4 px-6"><AgentAvatar url={a.photo_url} /></td>
                    <td className="py-4 px-6">
                      <div className="flex items-center gap-1.5">
                        <p className="font-medium text-white light:text-slate-900">{a.display_name}</p>
                        <button
                          onClick={() => handleOpenReferralLink(a.id)}
                          disabled={referralLinkLoadingId === a.id}
                          title="Apri il link personale di invito di questo promoter"
                          className="p-1 rounded-md hover:bg-white/10 light:hover:bg-slate-900/10 text-slate-400 hover:text-orange-400 transition cursor-pointer disabled:opacity-40"
                        >
                          {referralLinkLoadingId === a.id ? (
                            <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                            </svg>
                          ) : (
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                            </svg>
                          )}
                        </button>
                      </div>
                      <p className="text-[10px] text-slate-500">{a.email ?? "Nessun account collegato"}</p>
                      <p className="text-[10px] text-slate-500">Iscritto: {new Date(a.joined_at).toLocaleDateString("it-IT")}</p>
                    </td>
                    <td className="py-4 px-6 font-mono text-xs">{a.promoter_code}</td>
                    <td className="py-4 px-6">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-orange-500/10 text-orange-400 border-orange-500/20">
                        {a.rank_code ?? "—"}
                      </span>
                    </td>
                    <td className="py-4 px-6 text-xs">
                      {a.direct_parent_agent_id ? nameById.get(a.direct_parent_agent_id) ?? "—" : "Radice"}
                    </td>
                    <td className="py-4 px-6">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_COLORS[a.status] ?? STATUS_COLORS.ACTIVE}`}>
                        {STATUS_LABELS[a.status] ?? a.status}
                      </span>
                      {a.is_blacklisted && (
                        <span className="ml-1 px-2 py-0.5 rounded-full text-[10px] font-bold border bg-rose-500/10 text-rose-400 border-rose-500/20">
                          In blacklist
                        </span>
                      )}
                      {a.status === "TERMINATED" && a.rejection_reason && (
                        <p className="text-[10px] text-rose-400 mt-1 max-w-[160px]">{a.rejection_reason}</p>
                      )}
                    </td>
                    <td className="py-4 px-6 text-right">
                      {a.status === "PENDING_APPROVAL" ? (
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => handleApprove(a.id)}
                            disabled={approvalActionId === a.id}
                            className="px-2.5 py-1.5 rounded-lg bg-emerald-600/10 hover:bg-emerald-600/20 border border-emerald-500/20 text-emerald-400 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                          >
                            Approva
                          </button>
                          <button
                            onClick={() => setRejectingAgent(a)}
                            disabled={approvalActionId === a.id}
                            className="px-2.5 py-1.5 rounded-lg bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 text-rose-400 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                          >
                            Rifiuta
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center justify-end gap-2 flex-wrap">
                          <button
                            onClick={() => setNetworkAgent(a)}
                            title="Apri la rete di questo promoter"
                            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0H5a2 2 0 01-2-2v-4m6 6h10a2 2 0 002-2v-4m0-6h-6m6 0v6m0-6l-8 8" />
                            </svg>
                            Apri Rete
                          </button>
                          <button
                            onClick={() => openEdit(a)}
                            title="Modifica promoter"
                            className="p-1.5 rounded-lg bg-orange-600/10 hover:bg-orange-600/20 border border-orange-500/20 text-orange-400 transition cursor-pointer"
                          >
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                            </svg>
                          </button>
                          {a.status === "ACTIVE" && (
                            <>
                              <button
                                onClick={() => handleSetAgentStatus(a.id, { status: "TERMINATED" })}
                                disabled={agentActionId === a.id}
                                title="Toglie la qualifica di promoter: torna un semplice cliente. Può ricandidarsi in autonomia con 'Lavora con noi'."
                                className="px-2.5 py-1.5 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                              >
                                Disattiva
                              </button>
                              <button
                                onClick={() => handleSetAgentStatus(a.id, { status: "TERMINATED", is_blacklisted: true })}
                                disabled={agentActionId === a.id}
                                title="Disattiva e blocca: se si ricandida, resta in attesa di approvazione invece di attivarsi da solo."
                                className="px-2.5 py-1.5 rounded-lg bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 text-rose-400 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                              >
                                Blacklist
                              </button>
                            </>
                          )}
                          {(a.status === "TERMINATED" || a.status === "SUSPENDED") && (
                            <>
                              <button
                                onClick={() => handleSetAgentStatus(a.id, { status: "ACTIVE" })}
                                disabled={agentActionId === a.id}
                                className="px-2.5 py-1.5 rounded-lg bg-emerald-600/10 hover:bg-emerald-600/20 border border-emerald-500/20 text-emerald-400 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                              >
                                Riattiva
                              </button>
                              {a.is_blacklisted && (
                                <button
                                  onClick={() => handleSetAgentStatus(a.id, { is_blacklisted: false })}
                                  disabled={agentActionId === a.id}
                                  title="Toglie il blocco: da ora una nuova candidatura 'Lavora con noi' torna ad attivarsi da sola."
                                  className="px-2.5 py-1.5 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                                >
                                  Rimuovi blacklist
                                </button>
                              )}
                            </>
                          )}
                        </div>
                      )}
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
              <h3 className="text-lg font-bold text-white light:text-slate-900">Nuovo Promoter</h3>
              <button onClick={() => setShowCreate(false)}
                className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <form onSubmit={handleCreate} className="space-y-4">
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

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Codice Promoter</label>
                <input required value={promoterCode} onChange={(e) => setPromoterCode(e.target.value)}
                  placeholder="Es: S1-MARIO-ROSSI"
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono focus:border-orange-500" />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Sponsor (ramo di appartenenza)</label>
                <select
                  value={parentAgentId}
                  onChange={(e) => setParentAgentId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500"
                >
                  <option value="">— Nessuno (nuova radice di rete) —</option>
                  {(agents ?? []).map((a) => (
                    <option key={a.id} value={a.id}>{a.display_name} ({a.promoter_code})</option>
                  ))}
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Cliente già registrato (opzionale)</label>
                <input type="email" value={customerEmail} onChange={(e) => setCustomerEmail(e.target.value)}
                  placeholder="Email del cliente da promuovere a promoter"
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                <p className="text-[11px] text-slate-500">Se indicata, il login esistente del cliente diventerà anche promoter una volta approvato — invece di crearne uno nuovo senza accesso.</p>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Qualifica iniziale</label>
                <select
                  value={rankId}
                  onChange={(e) => setRankId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500"
                >
                  <option value="">— Nessuna —</option>
                  {ranks.map((r) => (
                    <option key={r.id} value={r.id}>{r.code} — {r.name}</option>
                  ))}
                </select>
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
                  {createLoading ? "Creazione..." : "Crea Promoter"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showCreateRoot && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white light:text-slate-900">Nuovo Promoter Radice</h3>
              <button onClick={() => setShowCreateRoot(false)}
                className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <p className="text-xs text-slate-400 light:text-slate-500 mb-4">
              Crea un account già attivo, senza sponsor sopra di lui. Genero password temporanea e link personale pronti da consegnare.
            </p>

            <form onSubmit={handleCreateRoot} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Nome</label>
                  <input required value={rootFirstName} onChange={(e) => setRootFirstName(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Cognome</label>
                  <input required value={rootLastName} onChange={(e) => setRootLastName(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Email</label>
                <input required type="email" value={rootEmail} onChange={(e) => setRootEmail(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Codice Promoter (opzionale)</label>
                <input value={rootPromoterCode} onChange={(e) => setRootPromoterCode(e.target.value)}
                  placeholder="Vuoto = generato automaticamente"
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono focus:border-orange-500" />
              </div>

              {rootCreateError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{rootCreateError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setShowCreateRoot(false)}
                  className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer">
                  Annulla
                </button>
                <button type="submit" disabled={rootCreateLoading}
                  className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                  {rootCreateLoading ? "Creazione..." : "Crea Promoter Radice"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {rootCreateResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up">
            <h3 className="text-lg font-bold text-white light:text-slate-900 mb-1">
              {rootCreateResult.display_name} è attivo
            </h3>
            <p className="text-xs text-slate-400 light:text-slate-500 mb-4">
              Consegna queste credenziali fuori da questa schermata (non restano salvate da nessuna parte): questa è l&apos;unica volta in cui la password viene mostrata. Digli di cambiarla al primo accesso.
            </p>

            <div className="space-y-3 mb-4">
              <div>
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block mb-1">Email</label>
                <div className="rounded-xl glass-input px-3 py-2 text-sm font-mono">{rootCreateResult.email}</div>
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block mb-1">Password temporanea</label>
                <div className="flex gap-2">
                  <div className="flex-1 rounded-xl glass-input px-3 py-2 text-sm font-mono">{rootCreateResult.temporary_password}</div>
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText(rootCreateResult.temporary_password);
                      setRootPasswordCopied(true);
                      setTimeout(() => setRootPasswordCopied(false), 2000);
                    }}
                    className="px-3 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-xs font-semibold text-slate-300 light:text-slate-600 transition cursor-pointer"
                  >
                    {rootPasswordCopied ? "Copiata!" : "Copia"}
                  </button>
                </div>
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block mb-1">Link personale (da condividere con i suoi invitati)</label>
                <div className="flex gap-2">
                  <div className="flex-1 rounded-xl glass-input px-3 py-2 text-xs font-mono truncate">{rootCreateResult.personal_link}</div>
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText(rootCreateResult.personal_link);
                      setRootLinkCopied(true);
                      setTimeout(() => setRootLinkCopied(false), 2000);
                    }}
                    className="px-3 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-xs font-semibold text-slate-300 light:text-slate-600 transition cursor-pointer"
                  >
                    {rootLinkCopied ? "Copiato!" : "Copia"}
                  </button>
                </div>
              </div>
            </div>

            <div className="flex justify-end">
              <button
                onClick={() => setRootCreateResult(null)}
                className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer"
              >
                Fatto
              </button>
            </div>
          </div>
        </div>
      )}

      {editingAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white light:text-slate-900">Modifica Promoter</h3>
              <button onClick={() => setEditingAgent(null)}
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
                uploadPath={`network/agents/${editingAgent.id}/photo`}
                onUploaded={(url) => {
                  setEditPhotoUrl(url);
                  queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
                }}
                alt={editingAgent.display_name}
              />
            </div>

            <form onSubmit={handleEditSave} className="space-y-4">
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

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Codice Promoter</label>
                <input disabled value={editingAgent.promoter_code}
                  title="Il codice promoter non è modificabile: è incorporato nei link di invito già condivisi"
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono opacity-60 cursor-not-allowed" />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Qualifica</label>
                <select
                  value={editRankId}
                  onChange={(e) => setEditRankId(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500"
                >
                  <option value="">— Nessuna —</option>
                  {ranks.map((r) => (
                    <option key={r.id} value={r.id}>{r.code} — {r.name}</option>
                  ))}
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Stato</label>
                <select
                  value={editStatus}
                  onChange={(e) => setEditStatus(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500"
                >
                  <option value="ACTIVE">Attivo</option>
                  <option value="SUSPENDED">Sospeso</option>
                  <option value="TERMINATED">Cessato</option>
                </select>
              </div>

              {editError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{editError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setEditingAgent(null)}
                  className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer">
                  Annulla
                </button>
                <button type="submit" disabled={editLoading}
                  className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                  {editLoading ? "Salvataggio..." : "Salva Modifiche"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {networkAgent && (
        <AdminPromoterNetworkModal
          agentId={networkAgent.id}
          displayName={networkAgent.display_name}
          onClose={() => setNetworkAgent(null)}
        />
      )}

      {rejectingAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-md glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up">
            <h3 className="text-lg font-bold text-white light:text-slate-900 mb-2">Rifiuta {rejectingAgent.display_name}</h3>
            <p className="text-xs text-slate-400 light:text-slate-500 mb-4">
              Il profilo suggerito viene segnato come cessato. Il codice promoter {rejectingAgent.promoter_code} non sarà più utilizzabile.
            </p>
            <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block mb-1">Motivazione (opzionale)</label>
            <textarea
              rows={3}
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Es: codice duplicato, dati incompleti..."
              className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500 resize-none mb-4"
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={() => { setRejectingAgent(null); setRejectReason(""); }}
                className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer"
              >
                Annulla
              </button>
              <button
                onClick={handleReject}
                disabled={approvalActionId === rejectingAgent.id}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
              >
                {approvalActionId === rejectingAgent.id ? "Salvataggio..." : "Conferma Rifiuto"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
