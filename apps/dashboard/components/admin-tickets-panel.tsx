"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { TicketDetailRead, TicketRead } from "@/lib/types";

const CATEGORY_LABELS: Record<string, string> = {
  ASSISTENZA_TECNICA: "Assistenza tecnica",
  FATTURAZIONE: "Fatturazione",
  CONTRATTO: "Contratto",
  COMMISSIONI: "Commissioni",
  ALTRO: "Altro",
};

const STATUS_LABELS: Record<string, string> = {
  OPEN: "Aperto",
  IN_PROGRESS: "In lavorazione",
  RESOLVED: "Risolto",
  CLOSED: "Chiuso",
};

const OPENER_LABELS: Record<string, string> = {
  CUSTOMER: "Cliente",
  PROMOTER: "Promoter",
};

function statusColor(status: string): string {
  switch (status) {
    case "OPEN":
      return "bg-amber-500/10 text-amber-400 border-amber-500/20";
    case "IN_PROGRESS":
      return "bg-sky-500/10 text-sky-400 border-sky-500/20";
    case "RESOLVED":
      return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
    default:
      return "bg-slate-500/10 text-slate-400 border-slate-500/20";
  }
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" });
}

async function fetchAllTickets(): Promise<TicketRead[]> {
  const res = await fetch("/api/proxy/support/tickets");
  if (!res.ok) throw new Error("Impossibile caricare i ticket.");
  return res.json();
}

async function fetchTicketDetailAsStaff(id: string): Promise<TicketDetailRead> {
  const res = await fetch(`/api/proxy/support/tickets/${id}/staff`);
  if (!res.ok) throw new Error("Impossibile caricare il ticket.");
  return res.json();
}

function TrashIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  );
}

export function AdminTicketsPanel() {
  const queryClient = useQueryClient();
  const { data: tickets, error: listError } = useQuery({ queryKey: ["admin", "tickets"], queryFn: fetchAllTickets });

  const [openerFilter, setOpenerFilter] = useState<string>("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [categoryFilter, setCategoryFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [deletingTicket, setDeletingTicket] = useState<TicketRead | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const { data: detail } = useQuery({
    queryKey: ["admin", "tickets", "detail", selectedId],
    queryFn: () => fetchTicketDetailAsStaff(selectedId as string),
    enabled: !!selectedId,
  });

  const [reply, setReply] = useState("");
  const [replyLoading, setReplyLoading] = useState(false);
  const [replyError, setReplyError] = useState<string | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);

  const filteredTickets = (tickets ?? []).filter((t) => {
    const matchesOpener = openerFilter === "ALL" || t.opened_by_role === openerFilter;
    const matchesStatus = statusFilter === "ALL" || t.status === statusFilter;
    const matchesCategory = categoryFilter === "ALL" || t.category === categoryFilter;
    const q = searchQuery.trim().toLowerCase();
    const matchesSearch =
      q === "" ||
      t.subject.toLowerCase().includes(q) ||
      (t.opened_by_name ?? "").toLowerCase().includes(q);
    return matchesOpener && matchesStatus && matchesCategory && matchesSearch;
  });

  const openCount = (tickets ?? []).filter((t) => t.status === "OPEN").length;

  async function refreshDetail() {
    await queryClient.invalidateQueries({ queryKey: ["admin", "tickets", "detail", selectedId] });
    await queryClient.invalidateQueries({ queryKey: ["admin", "tickets"] });
  }

  async function handleReply(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedId) return;
    setReplyLoading(true);
    setReplyError(null);
    try {
      const res = await fetch(`/api/proxy/support/tickets/${selectedId}/staff-messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: reply }),
      });
      if (!res.ok) throw new Error(await res.text());
      setReply("");
      await refreshDetail();
    } catch (err: any) {
      setReplyError(err.message || "Impossibile inviare la risposta.");
    } finally {
      setReplyLoading(false);
    }
  }

  async function handleStatusChange(newStatus: string) {
    if (!selectedId) return;
    setStatusLoading(true);
    try {
      const res = await fetch(`/api/proxy/support/tickets/${selectedId}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      if (!res.ok) throw new Error(await res.text());
      await refreshDetail();
    } finally {
      setStatusLoading(false);
    }
  }

  async function handleDeleteTicket() {
    if (!deletingTicket) return;
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      const res = await fetch(`/api/proxy/support/tickets/${deletingTicket.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error((await res.text()) || "Impossibile eliminare il ticket.");
      if (selectedId === deletingTicket.id) setSelectedId(null);
      setDeletingTicket(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "tickets"] });
    } catch (err: any) {
      setDeleteError(err.message || "Impossibile eliminare il ticket.");
    } finally {
      setDeleteLoading(false);
    }
  }

  const deleteConfirmModal = deletingTicket && (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up">
        <h3 className="text-lg font-bold text-white light:text-slate-900 mb-2">Elimina ticket</h3>
        <p className="text-xs text-slate-400 light:text-slate-500 mb-4">
          Stai per eliminare definitivamente il ticket{" "}
          <span className="font-semibold text-slate-300 light:text-slate-700">&quot;{deletingTicket.subject}&quot;</span> e
          tutti i suoi messaggi. L&apos;operazione non può essere annullata.
        </p>
        {deleteError && <p className="text-xs text-rose-400 mb-3">{deleteError}</p>}
        <div className="flex justify-end gap-3">
          <button
            onClick={() => { setDeletingTicket(null); setDeleteError(null); }}
            className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer"
          >
            Annulla
          </button>
          <button
            onClick={handleDeleteTicket}
            disabled={deleteLoading}
            className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
          >
            {deleteLoading ? "Eliminazione..." : "Elimina definitivamente"}
          </button>
        </div>
      </div>
    </div>
  );

  if (selectedId && detail) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => setSelectedId(null)}
          className="text-xs text-slate-400 hover:text-white light:hover:text-slate-900 transition cursor-pointer flex items-center gap-1"
        >
          ← Torna a tutti i ticket
        </button>

        <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div>
              <h3 className="text-lg font-semibold text-white light:text-slate-900">{detail.subject}</h3>
              <p className="text-xs text-slate-500 mt-1">
                {OPENER_LABELS[detail.opened_by_role] ?? detail.opened_by_role} · {detail.opened_by_name ?? "—"} ·{" "}
                {CATEGORY_LABELS[detail.category] ?? detail.category}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <select
                value={detail.status}
                onChange={(e) => handleStatusChange(e.target.value)}
                disabled={statusLoading}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold border bg-slate-900 light:bg-white cursor-pointer ${statusColor(detail.status)}`}
              >
                {Object.entries(STATUS_LABELS).map(([code, label]) => (
                  <option key={code} value={code}>{label}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => { if (detail.status === "RESOLVED") setDeletingTicket(detail); }}
                disabled={detail.status !== "RESOLVED"}
                title={detail.status === "RESOLVED" ? "Elimina ticket" : "Solo i ticket risolti possono essere eliminati"}
                className="p-2 rounded-xl border border-white/10 light:border-slate-300 text-slate-400 hover:text-rose-400 hover:border-rose-500/30 hover:bg-rose-500/10 transition cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:text-slate-400 disabled:hover:border-white/10 disabled:hover:bg-transparent"
              >
                <TrashIcon className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="space-y-3 mb-6">
            {detail.messages.map((m) => {
              const isStaff = m.author_role === "ADMIN";
              return (
                <div key={m.id} className={`flex ${isStaff ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm ${
                      isStaff
                        ? "bg-orange-600/10 border border-orange-500/20 text-slate-200 light:text-slate-700"
                        : "bg-white/5 light:bg-slate-900/5 border border-white/5 light:border-slate-200 text-slate-200 light:text-slate-700"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        {isStaff ? "Tu (Assistenza)" : m.author_name ?? OPENER_LABELS[m.author_role] ?? m.author_role}
                      </span>
                      <span className="text-[10px] text-slate-500">{formatDateTime(m.created_at)}</span>
                    </div>
                    <p className="whitespace-pre-wrap">{m.body}</p>
                  </div>
                </div>
              );
            })}
          </div>

          <form onSubmit={handleReply} className="flex gap-2">
            <input
              required
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              placeholder="Rispondi..."
              className="flex-1 rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500"
            />
            <button
              type="submit"
              disabled={replyLoading}
              className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white transition cursor-pointer disabled:opacity-50"
            >
              {replyLoading ? "Invio..." : "Rispondi"}
            </button>
          </form>
          {replyError && <p className="text-xs text-rose-400 mt-2">{replyError}</p>}
        </div>
        {deleteConfirmModal}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3">
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <p className="text-sm text-slate-400 light:text-slate-500 flex-1">
            Ticket aperti da clienti e promoter. {openCount} in attesa di risposta.
          </p>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Cerca per oggetto o nome..."
            className="rounded-xl glass-input px-3 py-2 text-xs bg-slate-900 light:bg-white focus:border-orange-500 w-full sm:w-64"
          />
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <select
            value={openerFilter}
            onChange={(e) => setOpenerFilter(e.target.value)}
            className="rounded-xl glass-input px-3 py-2 text-xs bg-slate-900 light:bg-white focus:border-orange-500"
          >
            <option value="ALL">Cliente e Promoter</option>
            <option value="CUSTOMER">Solo Clienti</option>
            <option value="PROMOTER">Solo Promoter</option>
          </select>
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="rounded-xl glass-input px-3 py-2 text-xs bg-slate-900 light:bg-white focus:border-orange-500"
          >
            <option value="ALL">Tutte le categorie</option>
            {Object.entries(CATEGORY_LABELS).map(([code, label]) => (
              <option key={code} value={code}>{label}</option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-xl glass-input px-3 py-2 text-xs bg-slate-900 light:bg-white focus:border-orange-500"
          >
            <option value="ALL">Tutti gli stati</option>
            {Object.entries(STATUS_LABELS).map(([code, label]) => (
              <option key={code} value={code}>{label}</option>
            ))}
          </select>
        </div>
      </div>

      {listError && <p className="text-sm text-rose-400">Impossibile caricare i ticket.</p>}

      <div className="space-y-3">
        {tickets === undefined ? (
          <p className="text-sm text-slate-500 text-center py-8">Caricamento...</p>
        ) : filteredTickets.length === 0 ? (
          <div className="glass-card rounded-2xl p-12 text-center border-white/5 light:border-slate-200">
            <p className="text-sm text-slate-500">Nessun ticket corrisponde ai filtri impostati.</p>
          </div>
        ) : (
          filteredTickets.map((t) => (
            <div
              key={t.id}
              className="glass-card rounded-2xl p-4 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 hover:bg-white/5 transition flex items-center justify-between gap-4"
            >
              <button
                onClick={() => setSelectedId(t.id)}
                className="min-w-0 flex-1 text-left cursor-pointer"
              >
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-orange-400 shrink-0">
                    {OPENER_LABELS[t.opened_by_role] ?? t.opened_by_role}
                  </span>
                  <p className="text-sm font-semibold text-white light:text-slate-900 truncate">{t.subject}</p>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border shrink-0 ${statusColor(t.status)}`}>
                    {STATUS_LABELS[t.status] ?? t.status}
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  {t.opened_by_name ?? "—"} · {CATEGORY_LABELS[t.category] ?? t.category} · {t.message_count} messaggi
                  {t.last_message_at ? ` · ultimo aggiornamento ${formatDateTime(t.last_message_at)}` : ""}
                </p>
              </button>
              <button
                type="button"
                onClick={() => { if (t.status === "RESOLVED") setDeletingTicket(t); }}
                disabled={t.status !== "RESOLVED"}
                title={t.status === "RESOLVED" ? "Elimina ticket" : "Solo i ticket risolti possono essere eliminati"}
                className="shrink-0 p-2 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:text-slate-500 disabled:hover:bg-transparent"
              >
                <TrashIcon className="w-4 h-4" />
              </button>
            </div>
          ))
        )}
      </div>
      {deleteConfirmModal}
    </div>
  );
}
