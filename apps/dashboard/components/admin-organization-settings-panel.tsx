"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import type { OrganizationSettingsRead, PaymentSettingsRead } from "@/lib/types";

async function fetchSettings(): Promise<OrganizationSettingsRead> {
  const res = await fetch("/api/proxy/organizations/me/settings");
  if (!res.ok) throw new Error("Impossibile caricare le impostazioni aziendali.");
  return res.json();
}

async function fetchPaymentSettings(): Promise<PaymentSettingsRead> {
  const res = await fetch("/api/proxy/organizations/me/payment-settings");
  if (!res.ok) throw new Error("Impossibile caricare le impostazioni di pagamento.");
  return res.json();
}

/** Company-wide configuration: the bank account customers wire bonifico
    payments to (invoice-redemption 3% payments, order residuals), plus --
    SUPER_ADMIN only -- Stripe card-payment keys. Was previously only
    settable by editing .env on the server; this is the dashboard-editable
    version. `isSuperAdmin` is a UX nicety only (hides a section this user's
    token couldn't call anyway) -- the backend's own
    organization.manage_payments permission is the real enforcement, see
    docs/cashback-partner-invoices-plan.md. */
export function AdminOrganizationSettingsPanel(
  { isSuperAdmin = false, organizationId }: { isSuperAdmin?: boolean; organizationId?: string } = {}
) {
  const queryClient = useQueryClient();
  const { data: settings, error: loadError } = useQuery({
    queryKey: ["admin", "organization-settings"],
    queryFn: fetchSettings,
  });

  const [iban, setIban] = useState("");
  const [holder, setHolder] = useState("");
  const [instructions, setInstructions] = useState("");
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    if (settings) {
      setIban(settings.bank_iban ?? "");
      setHolder(settings.bank_account_holder ?? "");
      setInstructions(settings.bank_transfer_instructions ?? "");
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
          bank_transfer_instructions: instructions.trim() || null,
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
          Mostrate al cliente quando deve pagare tramite bonifico (riscatto fatture, ordini). Finché l'IBAN non è
          impostato, il bottone "Paga con bonifico" non compare -- il cliente non può scegliere un metodo non
          configurato.
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
                placeholder="Lial Energy Srl"
                className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500"
              />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">
              Istruzioni aggiuntive per il bonifico
            </label>
            <textarea
              rows={3}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder="Es. Includi il codice ordine/riscatto nella causale del bonifico."
              className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500 resize-none"
            />
            <p className="text-[10px] text-slate-500">Mostrato insieme a IBAN e intestatario ovunque un cliente veda le istruzioni di pagamento.</p>
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

      {isSuperAdmin && <AdminStripeSettingsCard organizationId={organizationId} />}
    </div>
  );
}

function AdminStripeSettingsCard({ organizationId }: { organizationId?: string }) {
  const queryClient = useQueryClient();
  const { data: payment, error: loadError } = useQuery({
    queryKey: ["admin", "payment-settings"],
    queryFn: fetchPaymentSettings,
  });

  const [publishableKey, setPublishableKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    if (payment) setPublishableKey(payment.stripe_publishable_key ?? "");
  }, [payment]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaveLoading(true);
    setSaveError(null);
    try {
      // Secret fields are only sent if the admin actually typed something --
      // an untouched field must never overwrite an already-saved secret
      // with an empty string (see PaymentSettingsUpdate's exclude_unset).
      const body: Record<string, string> = { stripe_publishable_key: publishableKey.trim() };
      if (secretKey.trim()) body.stripe_secret_key = secretKey.trim();
      if (webhookSecret.trim()) body.stripe_webhook_secret = webhookSecret.trim();

      const res = await fetch("/api/proxy/organizations/me/payment-settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setSecretKey("");
      setWebhookSecret("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "payment-settings"] });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err: any) {
      setSaveError(err.message || "Impossibile salvare le impostazioni di pagamento.");
    } finally {
      setSaveLoading(false);
    }
  }

  const cardReady = payment?.stripe_secret_key_configured && !!payment?.stripe_publishable_key;

  return (
    <div className="glass-card rounded-2xl p-6 border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
      <div className="flex items-center gap-2 mb-1">
        <h3 className="text-sm font-semibold text-white light:text-slate-900">Pagamenti con carta (Stripe)</h3>
        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-violet-500/10 text-violet-400 border-violet-500/20">
          Solo Super Admin
        </span>
      </div>
      <p className="text-xs text-slate-500 mb-4">
        Finché queste chiavi non sono entrambe configurate, il bottone "Paga con carta" non compare da nessuna parte
        nel sistema -- si offre solo il bonifico. Le chiavi possono essere preparate ora e attivate in un secondo momento.
      </p>
      {loadError && <p className="text-sm text-rose-400 mb-3">Impossibile caricare le impostazioni.</p>}

      <div className="mb-4 p-3 rounded-lg bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-200">
        <p className="text-xs text-slate-300 light:text-slate-600">
          Stato: {cardReady ? (
            <span className="text-emerald-400 font-semibold">Attivo -- i clienti possono pagare con carta</span>
          ) : (
            <span className="text-amber-400 font-semibold">Non configurato</span>
          )}
        </p>
        {payment?.stripe_secret_key_configured && (
          <p className="text-[10px] text-slate-500 mt-1 font-mono">Chiave segreta salvata: •••• {payment.stripe_secret_key_last4}</p>
        )}
        <p className="text-[10px] text-slate-500 mt-1">
          Webhook: {payment?.stripe_webhook_secret_configured ? "configurato" : "non configurato"}
        </p>
      </div>

      <form onSubmit={handleSave} className="space-y-4">
        <div className="space-y-1">
          <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Chiave pubblicabile (publishable key)</label>
          <input
            value={publishableKey}
            onChange={(e) => setPublishableKey(e.target.value)}
            placeholder="pk_live_... oppure pk_test_..."
            className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono focus:border-orange-500"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Chiave segreta (secret key)</label>
          <input
            type="password"
            value={secretKey}
            onChange={(e) => setSecretKey(e.target.value)}
            placeholder={payment?.stripe_secret_key_configured ? "Già impostata -- lascia vuoto per non cambiarla" : "sk_live_... oppure sk_test_..."}
            className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono focus:border-orange-500"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Chiave segreta del webhook</label>
          <input
            type="password"
            value={webhookSecret}
            onChange={(e) => setWebhookSecret(e.target.value)}
            placeholder={payment?.stripe_webhook_secret_configured ? "Già impostata -- lascia vuoto per non cambiarla" : "whsec_..."}
            className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono focus:border-orange-500"
          />
          <p className="text-[10px] text-slate-500">
            Configura su Stripe un endpoint webhook per l'evento <code>checkout.session.completed</code> puntato a:{" "}
            <code className="text-slate-400 break-all">
              https://app.lialenergy.it/api/payments/stripe/webhook/{organizationId ?? "<ID-organizzazione>"}
            </code>
          </p>
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
  );
}
