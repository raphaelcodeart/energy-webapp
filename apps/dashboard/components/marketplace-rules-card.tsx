"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { MarketplaceConfigRead } from "@/lib/types";

export const MARKETPLACE_SOURCES: { key: "aliexpress" | "cj" | "shopify"; source: string }[] = [
  { key: "aliexpress", source: "AliExpress" },
  { key: "cj", source: "CJ Dropshipping" },
  { key: "shopify", source: "Shopify" },
];

async function fetchConfig(): Promise<MarketplaceConfigRead> {
  const res = await fetch("/api/proxy/marketplaces/config");
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

/** The names of the three Marketplace tabs and the card surcharge, used by
 *  the customer Shop and every checkout of imported products. */
export function useMarketplaceConfig() {
  return useQuery({ queryKey: ["marketplaces", "config"], queryFn: fetchConfig, staleTime: 60_000 });
}

/** "Regole dei Marketplace" (Session 68): what the three shops of imported
 *  products (AliExpress, CJ Dropshipping, Shopify) have in common, set once:
 *  the name each one has in the customer's Shop, and how much more a card
 *  payment costs than a bank transfer. The LialCash rules are shown, not
 *  editable here: 30% on a new product, never 100%. */
export function MarketplaceRulesCard({ highlight }: { highlight?: "aliexpress" | "cj" | "shopify" }) {
  const queryClient = useQueryClient();
  const { data: config, error } = useMarketplaceConfig();
  const [open, setOpen] = useState(false);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [surcharge, setSurcharge] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (!config) return;
    // Syncing the form with the server copy once it arrives.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLabels(config.labels);
    setSurcharge(String(config.card_surcharge_percentage));
  }, [config]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch("/api/proxy/marketplaces/config", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ labels, card_surcharge_percentage: Number(surcharge) || 0 }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      queryClient.setQueryData(["marketplaces", "config"], await res.json());
      setMessage({ ok: true, text: "Salvato." });
    } catch (err: any) {
      setMessage({ ok: false, text: err.message || "Salvataggio non riuscito." });
    } finally {
      setBusy(false);
    }
  }

  const pct = Number(surcharge) || 0;
  const label = highlight && config ? config.labels[highlight] : null;

  return (
    <div className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex flex-wrap items-center justify-between gap-2 px-5 py-4 text-left cursor-pointer">
        <span>
          <span className="block text-sm font-bold text-white light:text-slate-900">
            Regole dei Marketplace{label ? ` · per i clienti si chiama “${label}”` : ""}
          </span>
          <span className="block text-xs text-slate-400 light:text-slate-500 mt-0.5">
            {config
              ? `Carta +${config.card_surcharge_percentage}% · LialCash ${config.default_credit_percentage}% sui nuovi prodotti, mai 100% (max ${config.max_credit_percentage}%) · nessun cashback`
              : "Caricamento..."}
          </span>
        </span>
        <span className="text-xs font-semibold text-orange-400">{open ? "Chiudi" : "Modifica"}</span>
      </button>
      {error && <p className="px-5 pb-4 text-xs text-rose-400">{(error as Error).message}</p>}
      {open && config && (
        <form onSubmit={save} className="px-5 pb-5 space-y-4 border-t border-white/5 light:border-slate-200 pt-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {MARKETPLACE_SOURCES.map((m) => (
              <label key={m.key} className="block">
                <span className="block text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1">
                  Nome nello Shop · {m.source}
                </span>
                <input
                  value={labels[m.key] ?? ""}
                  maxLength={40}
                  onChange={(e) => setLabels({ ...labels, [m.key]: e.target.value })}
                  className="w-full rounded-lg glass-input px-3 py-2 text-sm focus:border-orange-500"
                />
              </label>
            ))}
          </div>
          <label className="block max-w-xs">
            <span className="block text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1">
              Aumento se si paga con carta (%)
            </span>
            <input
              inputMode="numeric"
              value={surcharge}
              onChange={(e) => setSurcharge(e.target.value.replace(/\D/g, ""))}
              className="w-full rounded-lg glass-input px-3 py-2 text-sm focus:border-orange-500"
            />
            <span className="block text-[10px] text-slate-500 mt-1">
              {pct > 0
                ? `Esempio: 20,00 € con bonifico istantaneo = ${((2000 + Math.floor((2000 * pct + 50) / 100)) / 100).toFixed(2).replace(".", ",")} € con carta. Vale per tutti e tre i Marketplace.`
                : "0 = stesso prezzo con carta e bonifico."}
            </span>
          </label>
          <p className="text-[11px] text-slate-500">
            Il cliente non vede mai la fonte (AliExpress, CJ, Shopify): solo il nome scelto qui. I prodotti dei
            Marketplace non danno cashback: permettono solo di spendere il LialCash, al massimo per la percentuale di
            ogni prodotto (30% quando entra, modificabile fino al {config.max_credit_percentage}%).
          </p>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={busy}
              className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-bold text-white cursor-pointer disabled:opacity-50"
            >
              {busy ? "Salvataggio..." : "Salva"}
            </button>
            {message && <span className={`text-xs ${message.ok ? "text-emerald-400" : "text-rose-400"}`}>{message.text}</span>}
          </div>
        </form>
      )}
    </div>
  );
}
