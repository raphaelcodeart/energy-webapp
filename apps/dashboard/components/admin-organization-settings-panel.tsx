"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { OrganizationSettingsRead } from "@/lib/types";

async function fetchSettings(): Promise<OrganizationSettingsRead> {
  const res = await fetch("/api/proxy/organizations/me/settings");
  if (!res.ok) throw new Error("Impossibile caricare le impostazioni aziendali.");
  return res.json();
}

/** Company-wide configuration, starting with the bank account customers
    wire bonifico payments to (invoice redemptions' 3% payment today, order
    residuals tomorrow) -- see docs/cashback-partner-invoices-plan.md. Was
    previously only settable by editing .env on the server; this is the
    dashboard-editable version any ADMIN can use. */
export function AdminOrganizationSettingsPanel() {
  const queryClient = useQueryClient();
  const { data: settings, error: loadError } = useQuery({
    queryKey: ["admin", "organization-settings"],
    queryFn: fetchSettings,
  });

  const [iban, setIban] = useState("");
  const [holder, setHolder] = useState("");
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    if (settings) {
      setIban(settings.bank_iban ?? "");
      setHolder(settings.bank_account_holder ?? "");
    }
  }, [settings]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaveLoading(true);
    setSaveError(null);
    try {
      const res = await fetch("/api/proxy/organizations/me/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          bank_iban: iban.trim() || null,
          bank_account_holder: holder.trim() || null,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "organization-settings"] });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err: any) {
      setSaveError(err.message || "Impossibile salvare le impostazioni.");
    } finally {
      setSaveLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
        <h3 className="text-sm font-semibold text-white light:text-slate-900 mb-1">Coordinate bancarie aziendali</h3>
        <p className="text-xs text-slate-500 mb-4">
          Mostrate al cliente quando deve pagare tramite bonifico (es. il 3% per riscattare una fattura partner).
          Finché l'IBAN non è impostato, il cliente vede "contatta l'amministrazione" invece di un campo vuoto.
        </p>
        {loadError && <p className="text-sm text-rose-400 mb-3">Impossibile caricare le impostazioni.</p>}
        <form onSubmit={handleSave} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">IBAN</label>
              <input
                value={iban}
                onChange={(e) => setIban(e.target.value)}
                placeholder="IT00 A000 0000 0000 0000 0000 000"
                className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono focus:border-orange-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Intestatario</label>
              <input
                value={holder}
                onChange={(e) => setHolder(e.target.value)}
                placeholder="Lial Energy"
                className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={saveLoading}
            className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
          >
            {saveLoading ? "Salvataggio..." : "Salva"}
          </button>
          {saveError && (
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{saveError}</div>
          )}
          {saveSuccess && (
            <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">Impostazioni salvate.</div>
          )}
        </form>
      </div>
    </div>
  );
}
