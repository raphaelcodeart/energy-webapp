"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
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

async function fetchMyTickets(): Promise<TicketRead[]> {
  const res = await fetch("/api/proxy/support/tickets/mine");
  if (!res.ok) throw new Error("Impossibile caricare i ticket.");
  return res.json();
}

async function fetchTicketDetail(id: string): Promise<TicketDetailRead> {
  const res = await fetch(`/api/proxy/support/tickets/${id}`);
  if (!res.ok) throw new Error("Impossibile caricare il ticket.");
  return res.json();
}

export function SupportTicketsPanel({ title, subtitle }: { title: string; subtitle: string }) {
  const queryClient = useQueryClient();
  const { data: tickets, error: listError } = useQuery({ queryKey: ["support", "tickets", "mine"], queryFn: fetchMyTickets });

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: detail } = useQuery({
    queryKey: ["support", "tickets", "detail", selectedId],
    queryFn: () => fetchTicketDetail(selectedId as string),
    enabled: !!selectedId,
  });

  const [showCreate, setShowCreate] = useState(false);
  const [subject, setSubject] = useState("");
  const [category, setCategory] = useState("ASSISTENZA_TECNICA");
  const [message, setMessage] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [reply, setReply] = useState("");
  const [replyLoading, setReplyLoading] = useState(false);
  const [replyError, setReplyError] = useState<string | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateLoading(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/proxy/support/tickets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject, category, message }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const newTicket = (await res.json()) as TicketRead;
      setSubject("");
      setMessage("");
      setShowCreate(false);
      await queryClient.invalidateQueries({ queryKey: ["support", "tickets", "mine"] });
      setSelectedId(newTicket.id);
    } catch (err: any) {
      setCreateError(err.message || "Impossibile aprire il ticket.");
    } finally {
      setCreateLoading(false);
    }
  }

  async function handleReply(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedId) return;
    setReplyLoading(true);
    setReplyError(null);
    try {
      const res = await fetch(`/api/proxy/support/tickets/${selectedId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: reply }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setReply("");
      await queryClient.invalidateQueries({ queryKey: ["support", "tickets", "detail", selectedId] });
      await queryClient.invalidateQueries({ queryKey: ["support", "tickets", "mine"] });
    } catch (err: any) {
      setReplyError(err.message || "Impossibile inviare la risposta.");
    } finally {
      setReplyLoading(false);
    }
  }

  if (selectedId && detail) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => setSelectedId(null)}
          className="text-xs text-slate-400 hover:text-white light:hover:text-slate-900 transition cursor-pointer flex items-center gap-1"
        >
          ← Torna ai ticket
        </button>

        <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div>
              <h3 className="text-lg font-semibold text-white light:text-slate-900">{detail.subject}</h3>
              <p className="text-xs text-slate-500 mt-1">{CATEGORY_LABELS[detail.category] ?? detail.category}</p>
            </div>
            <span className={`px-3 py-1 rounded-full text-xs font-bold border shrink-0 ${statusColor(detail.status)}`}>
              {STATUS_LABELS[detail.status] ?? detail.status}
            </span>
          </div>

          <div className="space-y-3 mb-6">
            {detail.messages.map((m) => {
              const isStaff = m.author_role === "ADMIN";
              return (
                <div key={m.id} className={`flex ${isStaff ? "justify-start" : "justify-end"}`}>
                  <div
                    className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm ${
                      isStaff
                        ? "bg-orange-600/10 border border-orange-500/20 text-slate-200 light:text-slate-700"
                        : "bg-white/5 light:bg-slate-900/5 border border-white/5 light:border-slate-200 text-slate-200 light:text-slate-700"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        {isStaff ? "Assistenza" : m.author_name ?? "Tu"}
                      </span>
                      <span className="text-[10px] text-slate-500">{formatDateTime(m.created_at)}</span>
                    </div>
                    <p className="whitespace-pre-wrap">{m.body}</p>
                  </div>
                </div>
              );
            })}
          </div>

          {detail.status !== "CLOSED" && (
            <form onSubmit={handleReply} className="flex gap-2">
              <input
                required
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                placeholder="Scrivi una risposta..."
                className="flex-1 rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500"
              />
              <button
                type="submit"
                disabled={replyLoading}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white transition cursor-pointer disabled:opacity-50"
              >
                {replyLoading ? "Invio..." : "Invia"}
              </button>
            </form>
          )}
          {replyError && <p className="text-xs text-rose-400 mt-2">{replyError}</p>}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-white light:text-slate-900">{title}</h2>
          <p className="text-sm text-slate-400 light:text-slate-500 mt-1">{subtitle}</p>
        </div>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white shadow-lg shadow-orange-500/20 transition cursor-pointer shrink-0"
        >
          + Nuovo Ticket
        </button>
      </div>

      {showCreate && (
        <form onSubmit={handleCreate} className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 space-y-4">
          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Oggetto</label>
            <input required value={subject} onChange={(e) => setSubject(e.target.value)}
              className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Categoria</label>
            <select value={category} onChange={(e) => setCategory(e.target.value)}
              className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
              {Object.entries(CATEGORY_LABELS).map(([code, label]) => (
                <option key={code} value={code}>{label}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Messaggio</label>
            <textarea required rows={4} value={message} onChange={(e) => setMessage(e.target.value)}
              className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500 resize-none" />
          </div>
          {createError && <p className="text-xs text-rose-400">{createError}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setShowCreate(false)}
              className="px-4 py-2 rounded-xl text-xs font-semibold bg-white/5 hover:bg-white/10 text-slate-300 transition cursor-pointer">
              Annulla
            </button>
            <button type="submit" disabled={createLoading}
              className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white transition cursor-pointer disabled:opacity-50">
              {createLoading ? "Invio..." : "Apri Ticket"}
            </button>
          </div>
        </form>
      )}

      {listError && <p className="text-sm text-rose-400">Impossibile caricare i ticket.</p>}

      <div className="space-y-3">
        {tickets === undefined ? (
          <p className="text-sm text-slate-500 text-center py-8">Caricamento...</p>
        ) : tickets.length === 0 ? (
          <div className="glass-card rounded-2xl p-12 text-center border-white/5 light:border-slate-200">
            <p className="text-sm text-slate-500">Nessun ticket aperto. Usa &quot;+ Nuovo Ticket&quot; se hai bisogno di assistenza.</p>
          </div>
        ) : (
          tickets.map((t) => (
            <button
              key={t.id}
              onClick={() => setSelectedId(t.id)}
              className="w-full text-left glass-card rounded-2xl p-4 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 hover:bg-white/5 transition flex items-center justify-between gap-4 cursor-pointer"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold text-white light:text-slate-900 truncate">{t.subject}</p>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border shrink-0 ${statusColor(t.status)}`}>
                    {STATUS_LABELS[t.status] ?? t.status}
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  {CATEGORY_LABELS[t.category] ?? t.category} · {t.message_count} messaggi
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
