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

export function AdminTicketsPanel() {
  const queryClient = useQueryClient();
  const { data: tickets, error: listError } = useQuery({ queryKey: ["admin", "tickets"], queryFn: fetchAllTickets });

  const [openerFilter, setOpenerFilter] = useState<string>("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [selectedId, setSelectedId] = useState<string | null>(null);

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
    return matchesOpener && matchesStatus;
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
            <select
              value={detail.status}
              onChange={(e) => handleStatusChange(e.target.value)}
              disabled={statusLoading}
              className={`px-3 py-1.5 rounded-xl text-xs font-bold border shrink-0 bg-slate-900 light:bg-white cursor-pointer ${statusColor(detail.status)}`}
            >
              {Object.entries(STATUS_LABELS).map(([code, label]) => (
                <option key={code} value={code}>{label}</option>
              ))}
            </select>
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
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <p className="text-sm text-slate-400 light:text-slate-500 flex-1">
          Ticket aperti da clienti e promoter. {openCount} in attesa di risposta.
        </p>
        <div className="flex items-center gap-2">
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
            <button
              key={t.id}
              onClick={() => setSelectedId(t.id)}
              className="w-full text-left glass-card rounded-2xl p-4 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 hover:bg-white/5 transition flex items-center justify-between gap-4 cursor-pointer"
            >
              <div className="min-w-0">
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
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
