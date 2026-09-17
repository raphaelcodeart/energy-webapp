"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { Pagination, usePagination } from "@/components/pagination";
import { ProductThumbnail } from "@/components/product-thumbnail";
import type {
  CjCatalogPage,
  CjOrderRead,
  CjProductAdminRead,
  CjProductPreview,
  CjSettingsRead,
} from "@/lib/types";

type Tab = "orders" | "products" | "catalog" | "settings";

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function usd(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return `$${value}`;
}

/** Same formula as the server (cj_dropshipping/pricing.py), for showing a
 *  price while the administrator types; the server's figure is what counts. */
function salePriceCents(
  costUsd: number, rules: Pick<CjSettingsRead, "usd_eur_rate" | "markup_fixed_cents" | "price_rounding" | "shipping_mode">,
  markupPct: number, shippingUsd?: number | null,
): number {
  const rate = Number(rules.usd_eur_rate);
  let base = costUsd * rate * 100 * (1 + markupPct / 100) + Number(rules.markup_fixed_cents);
  if (rules.shipping_mode === "INCLUDED" && shippingUsd) base += shippingUsd * rate * 100;
  const cents = Math.ceil(Math.round(base * 1e6) / 1e6);
  if (rules.price_rounding === "NONE") return cents;
  const target = Number(rules.price_rounding);
  const euros = Math.floor(cents / 100);
  return cents % 100 <= target ? euros * 100 + target : (euros + 1) * 100 + target;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("it-IT", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

function postJson<T>(url: string, body?: unknown, method = "POST"): Promise<T> {
  return getJson<T>(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

const card = "glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70";
const input = "w-full rounded-lg glass-input px-3 py-2 text-sm focus:border-orange-500";
const label = "block text-[10px] font-semibold text-slate-400 light:text-slate-500 uppercase tracking-wide mb-1";
const btnPrimary = "px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50";
const btnGhost = "px-3 py-1.5 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-xs font-semibold text-slate-300 light:text-slate-600 transition cursor-pointer disabled:opacity-50";

function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{message}</div>;
}

/** Shop Lial Partner (CJ Dropshipping), Session 60.
 *
 *  Its own admin page, like "Acquisti LialEnergy": products come from CJ's
 *  catalog through the API, are re-priced in euro with the organization's
 *  markup, and sold in the customer Shop with the same checkout as every
 *  other shop. A paid order is sent to CJ (by hand or automatically), paid
 *  from the CJ balance, and followed until delivery.
 */
export function AdminCjPanel() {
  const { data: settings } = useQuery({
    queryKey: ["admin", "cj", "settings"],
    queryFn: () => getJson<CjSettingsRead>("/api/proxy/cj/settings"),
  });
  const [tab, setTab] = useState<Tab | null>(null);
  const activeTab: Tab = tab ?? (settings && !settings.api_key_configured ? "settings" : "orders");

  const tabs: { key: Tab; label: string }[] = [
    { key: "orders", label: "Ordini" },
    { key: "products", label: "Prodotti in vendita" },
    { key: "catalog", label: "Catalogo CJ" },
    { key: "settings", label: "Impostazioni" },
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-white light:text-slate-900">Shop Lial Partner</h2>
          <p className="text-xs text-slate-400 light:text-slate-500 mt-0.5">
            Prodotti CJ Dropshipping venduti nello Shop: importa, prezza, spedisci e segui gli ordini.
          </p>
        </div>
        {settings && (
          <div className="flex flex-wrap gap-2 text-[11px] font-semibold">
            <span className={`px-2.5 py-1 rounded-full border ${settings.enabled ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" : "bg-slate-500/10 border-slate-500/30 text-slate-400"}`}>
              {settings.enabled ? "Shop attivo" : "Shop spento"}
            </span>
            {settings.sandbox && (
              <span className="px-2.5 py-1 rounded-full border bg-amber-500/10 border-amber-500/30 text-amber-400">Modalità test (sandbox)</span>
            )}
            {settings.last_balance_usd !== null && (
              <span className="px-2.5 py-1 rounded-full border bg-white/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600">
                Saldo CJ {usd(settings.last_balance_usd.toFixed(2))}
              </span>
            )}
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-xl text-xs font-semibold border transition cursor-pointer ${
              activeTab === t.key
                ? "bg-orange-600 border-orange-600 text-white"
                : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === "settings" && <SettingsTab settings={settings} />}
      {activeTab === "catalog" && <CatalogTab settings={settings} onImported={() => setTab("products")} />}
      {activeTab === "products" && <ProductsTab />}
      {activeTab === "orders" && <OrdersTab />}
    </div>
  );
}

// --- Impostazioni -----------------------------------------------------------------------

function SettingsTab({ settings }: { settings: CjSettingsRead | undefined }) {
  if (!settings) return <div className={`${card} h-40 animate-pulse`} />;
  return <SettingsForm settings={settings} />;
}

function SettingsForm({ settings }: { settings: CjSettingsRead }) {
  const queryClient = useQueryClient();
  const [apiKey, setApiKey] = useState("");
  const [form, setForm] = useState<CjSettingsRead>(settings);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function save(extra: Partial<CjSettingsRead> & { api_key?: string } = {}) {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const body = {
        enabled: form.enabled,
        sandbox: form.sandbox,
        usd_eur_rate: Number(form.usd_eur_rate),
        markup_percentage: Number(form.markup_percentage),
        markup_fixed_cents: Number(form.markup_fixed_cents),
        price_rounding: form.price_rounding,
        shipping_mode: form.shipping_mode,
        default_credit_percentage: Number(form.default_credit_percentage),
        auto_forward: form.auto_forward,
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
        ...extra,
      };
      const saved = await postJson<CjSettingsRead>("/api/proxy/cj/settings", body, "PATCH");
      setForm(saved);
      setApiKey("");
      queryClient.setQueryData(["admin", "cj", "settings"], saved);
      queryClient.invalidateQueries({ queryKey: ["admin", "cj", "products"] });
      setNotice("Impostazioni salvate. Se hai cambiato i prezzi, tutti i prodotti sono già stati ricalcolati.");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function test() {
    setTesting(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await postJson<CjSettingsRead>("/api/proxy/cj/settings/test");
      setForm({ ...form, connected: saved.connected, last_balance_usd: saved.last_balance_usd, last_balance_at: saved.last_balance_at });
      queryClient.setQueryData(["admin", "cj", "settings"], saved);
      setNotice(`Connessione a CJ riuscita. Saldo disponibile: $${saved.last_balance_usd?.toFixed(2) ?? "0.00"}.`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setTesting(false);
    }
  }

  const sample = 10; // USD
  const sampleCents = salePriceCents(sample, { ...form, shipping_mode: "CUSTOMER_PAYS" }, Number(form.markup_percentage));

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
      <div className={`${card} p-5 space-y-4`}>
        <h3 className="text-sm font-bold text-white light:text-slate-900">Collegamento a CJ Dropshipping</h3>
        <div>
          <span className={label}>Chiave API</span>
          <input
            className={input}
            type="password"
            autoComplete="off"
            value={apiKey}
            placeholder={settings.api_key_configured ? `Salvata (${settings.api_key_hint}) — scrivi qui solo per cambiarla` : "CJxxxxxxx@api@xxxxxxxx"}
            onChange={(e) => setApiKey(e.target.value)}
          />
          <p className="text-[11px] text-slate-500 mt-1">
            La trovi su cjdropshipping.com → My CJ → Authorization → API. Resta salvata sul server e non viene mai mostrata.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className={btnPrimary} disabled={saving || !apiKey.trim()} onClick={() => save()}>Salva chiave</button>
          <button className={btnGhost} disabled={testing || !settings.api_key_configured} onClick={test}>
            {testing ? "Verifica..." : "Verifica connessione e saldo"}
          </button>
        </div>
        <div className="text-xs text-slate-400 light:text-slate-500 space-y-1">
          <p>Stato: {settings.connected ? <span className="text-emerald-400">collegato</span> : <span className="text-amber-400">non ancora verificato</span>}</p>
          {settings.last_balance_at && <p>Saldo CJ: <strong className="text-white light:text-slate-900">${settings.last_balance_usd?.toFixed(2)}</strong> (letto il {formatDate(settings.last_balance_at)})</p>}
          <p className="text-[11px]">Gli ordini inviati a CJ vengono pagati dal saldo del tuo account CJ: ricaricalo dal sito CJ quando serve.</p>
        </div>

        <div className="pt-4 border-t border-white/5 light:border-slate-200 space-y-3">
          <Switch checked={form.enabled} onChange={(v) => setForm({ ...form, enabled: v })}
            title="Shop visibile ai clienti" hint="Aggiunge la scheda “Shop Lial Partner” nello Shop del cliente." />
          <Switch checked={form.sandbox} onChange={(v) => setForm({ ...form, sandbox: v })}
            title="Modalità test (sandbox)" hint="Gli ordini inviati a CJ sono di prova: nessuna spedizione reale, nessun addebito. Spegnila quando sei pronto a vendere." />
          <Switch checked={form.auto_forward} onChange={(v) => setForm({ ...form, auto_forward: v })}
            title="Invia a CJ in automatico" hint="Appena il cliente ha pagato, l'ordine parte verso CJ. Se è spento lo invii tu da “Ordini”." />
        </div>
      </div>

      <div className={`${card} p-5 space-y-4`}>
        <h3 className="text-sm font-bold text-white light:text-slate-900">Prezzi e spedizione</h3>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <span className={label}>Cambio 1 USD = EUR</span>
            <input className={input} inputMode="decimal" value={form.usd_eur_rate}
              onChange={(e) => setForm({ ...form, usd_eur_rate: e.target.value as unknown as number })} />
          </div>
          <div>
            <span className={label}>Ricarico %</span>
            <input className={input} inputMode="numeric" value={form.markup_percentage}
              onChange={(e) => setForm({ ...form, markup_percentage: e.target.value as unknown as number })} />
          </div>
          <div>
            <span className={label}>Ricarico fisso (€)</span>
            <input className={input} inputMode="decimal" value={(Number(form.markup_fixed_cents) / 100).toString()}
              onChange={(e) => setForm({ ...form, markup_fixed_cents: Math.round((parseFloat(e.target.value.replace(",", ".")) || 0) * 100) })} />
          </div>
          <div>
            <span className={label}>Arrotondamento</span>
            <select className={input} value={form.price_rounding}
              onChange={(e) => setForm({ ...form, price_rounding: e.target.value as CjSettingsRead["price_rounding"] })}>
              <option value="90">a ,90 (es. 12,90)</option>
              <option value="99">a ,99 (es. 12,99)</option>
              <option value="NONE">al centesimo</option>
            </select>
          </div>
          <div>
            <span className={label}>Spedizione</span>
            <select className={input} value={form.shipping_mode}
              onChange={(e) => setForm({ ...form, shipping_mode: e.target.value as CjSettingsRead["shipping_mode"] })}>
              <option value="CUSTOMER_PAYS">la paga il cliente (costo reale)</option>
              <option value="INCLUDED">inclusa nel prezzo</option>
            </select>
          </div>
          <div>
            <span className={label}>LialCash usabili (default %)</span>
            <input className={input} inputMode="numeric" value={form.default_credit_percentage}
              onChange={(e) => setForm({ ...form, default_credit_percentage: e.target.value as unknown as number })} />
          </div>
        </div>
        <div className="p-3 rounded-xl bg-orange-500/5 border border-orange-500/20 text-xs text-slate-300 light:text-slate-600">
          Esempio: un prodotto che su CJ costa <strong>$10</strong> sarà in vendita a <strong className="text-orange-400">{euro(sampleCents)}</strong>
          {form.shipping_mode === "CUSTOMER_PAYS" ? " + spedizione." : " (più la stima di spedizione, inclusa)."}
          <p className="text-[11px] text-slate-500 mt-1">L&apos;arrotondamento è sempre per eccesso: il margine non scende mai sotto il ricarico impostato.</p>
        </div>
        <ErrorBox message={error} />
        {notice && <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">{notice}</div>}
        <button className={btnPrimary} disabled={saving} onClick={() => save()}>
          {saving ? "Salvataggio..." : "Salva impostazioni"}
        </button>
      </div>
    </div>
  );
}

function Switch({ checked, onChange, title, hint }: { checked: boolean; onChange: (v: boolean) => void; title: string; hint: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)} className="flex items-start gap-3 text-left cursor-pointer w-full">
      <span className={`relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${checked ? "bg-orange-600" : "bg-white/15 light:bg-slate-300"}`}>
        <span className={`inline-block rounded-full bg-white shadow transition-transform ${checked ? "translate-x-6" : "translate-x-1"}`} style={{ height: 18, width: 18 }} />
      </span>
      <span>
        <span className="block text-sm font-semibold text-white light:text-slate-900">{title}</span>
        <span className="block text-[11px] text-slate-500">{hint}</span>
      </span>
    </button>
  );
}

// --- Catalogo CJ ----------------------------------------------------------------------------

function CatalogTab({ settings, onImported }: { settings: CjSettingsRead | undefined; onImported: () => void }) {
  const [keyword, setKeyword] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [freeShipping, setFreeShipping] = useState(false);
  const [query, setQuery] = useState<{ keyword: string; categoryId: string; min: string; max: string; free: boolean; page: number } | null>(null);
  const [previewPid, setPreviewPid] = useState<string | null>(null);

  const { data: categories } = useQuery({
    queryKey: ["admin", "cj", "categories"],
    queryFn: () => getJson<{ id: string; name: string }[]>("/api/proxy/cj/catalog/categories"),
    enabled: !!settings?.api_key_configured,
    staleTime: 3600_000,
  });

  const { data: results, error, isFetching } = useQuery({
    queryKey: ["admin", "cj", "search", query],
    queryFn: () => {
      const q = query!;
      const params = new URLSearchParams({ page: String(q.page) });
      if (q.keyword) params.set("keyword", q.keyword);
      if (q.categoryId) params.set("category_id", q.categoryId);
      if (q.min) params.set("min_price", q.min);
      if (q.max) params.set("max_price", q.max);
      if (q.free) params.set("free_shipping", "true");
      return getJson<CjCatalogPage>(`/api/proxy/cj/catalog/search?${params}`);
    },
    enabled: !!query,
    staleTime: 300_000,
  });

  if (settings && !settings.api_key_configured) {
    return <p className={`${card} p-6 text-sm text-slate-400`}>Prima inserisci la chiave API di CJ in Impostazioni.</p>;
  }

  function search(page = 1) {
    setQuery({ keyword: keyword.trim(), categoryId, min: minPrice, max: maxPrice, free: freeShipping, page });
  }

  return (
    <div className="space-y-4">
      <form onSubmit={(e) => { e.preventDefault(); search(1); }} className={`${card} p-4 grid grid-cols-1 md:grid-cols-12 gap-3 items-end`}>
        <div className="md:col-span-4">
          <span className={label}>Cerca (in inglese)</span>
          <input className={input} value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="es. wireless earbuds, led lamp, yoga mat" />
        </div>
        <div className="md:col-span-3">
          <span className={label}>Categoria</span>
          <select className={input} value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">Tutte</option>
            {(categories ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="md:col-span-1">
          <span className={label}>Da $</span>
          <input className={input} inputMode="decimal" value={minPrice} onChange={(e) => setMinPrice(e.target.value)} />
        </div>
        <div className="md:col-span-1">
          <span className={label}>A $</span>
          <input className={input} inputMode="decimal" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} />
        </div>
        <label className="md:col-span-2 flex items-center gap-2 text-xs text-slate-300 light:text-slate-600 pb-2 cursor-pointer">
          <input type="checkbox" checked={freeShipping} onChange={(e) => setFreeShipping(e.target.checked)} />
          Spedizione gratuita
        </label>
        <button type="submit" className={`${btnPrimary} md:col-span-1`} disabled={isFetching}>{isFetching ? "..." : "Cerca"}</button>
      </form>

      <ErrorBox message={error ? (error as Error).message : null} />

      {!query && (
        <p className="text-sm text-slate-500 text-center py-10">
          Cerca nel catalogo CJ: vedi subito il prezzo a cui lo venderesti, poi apri un prodotto per importarlo.
        </p>
      )}

      {results && (
        <>
          <p className="text-xs text-slate-500">{results.total_records.toLocaleString("it-IT")} prodotti trovati · pagina {results.page} di {results.total_pages}</p>
          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-3">
            {results.items.map((item) => (
              <button key={item.pid} type="button" onClick={() => setPreviewPid(item.pid)}
                className={`${card} overflow-hidden text-left hover:border-orange-500/40 transition cursor-pointer`}>
                <div className="relative aspect-square bg-white">
                  <ProductThumbnail imageUrl={item.image_url} alt={item.name_en} className="w-full h-full object-cover" />
                  {item.already_imported && (
                    <span className="absolute top-1.5 left-1.5 px-2 py-0.5 rounded-full text-[9px] font-bold bg-emerald-500 text-white">Già importato</span>
                  )}
                  {item.free_shipping && (
                    <span className="absolute top-1.5 right-1.5 px-2 py-0.5 rounded-full text-[9px] font-bold bg-sky-500 text-white">Sped. gratis</span>
                  )}
                </div>
                <div className="p-2.5">
                  <p className="text-[11px] text-slate-300 light:text-slate-700 line-clamp-2 min-h-[2rem]">{item.name_en}</p>
                  <div className="flex items-end justify-between mt-1.5">
                    <span className="text-[10px] text-slate-500">CJ {usd(item.sell_price_usd)}</span>
                    {item.estimated_price_cents !== null && (
                      <span className="text-sm font-bold text-orange-400">{euro(item.estimated_price_cents)}</span>
                    )}
                  </div>
                  {item.inventory !== null && <p className="text-[10px] text-slate-500">Disponibili {item.inventory}</p>}
                </div>
              </button>
            ))}
          </div>
          <div className="flex items-center justify-center gap-2">
            <button className={btnGhost} disabled={results.page <= 1 || isFetching} onClick={() => search(results.page - 1)}>← Precedente</button>
            <button className={btnGhost} disabled={results.page >= results.total_pages || isFetching} onClick={() => search(results.page + 1)}>Successiva →</button>
          </div>
        </>
      )}

      {previewPid && (
        <ImportModal pid={previewPid} settings={settings} onClose={() => setPreviewPid(null)} onImported={() => { setPreviewPid(null); onImported(); }} />
      )}
    </div>
  );
}

function ImportModal({ pid, settings, onClose, onImported }: {
  pid: string; settings: CjSettingsRead | undefined; onClose: () => void; onImported: () => void;
}) {
  const queryClient = useQueryClient();
  const { data: preview, error } = useQuery({
    queryKey: ["admin", "cj", "preview", pid],
    queryFn: () => getJson<CjProductPreview>(`/api/proxy/cj/catalog/products/${pid}`),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-4xl max-h-[92vh] overflow-y-auto glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-white light:text-slate-900">Importa nello Shop Lial Partner</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-slate-400 cursor-pointer" aria-label="Chiudi">✕</button>
        </div>
        <ErrorBox message={error ? (error as Error).message : null} />
        {!preview && !error && <p className="py-12 text-center text-sm text-slate-500">Lettura del prodotto e della spedizione da CJ...</p>}
        {preview && (
          <ImportForm
            pid={pid}
            preview={preview}
            settings={settings}
            onImported={async () => {
              await queryClient.invalidateQueries({ queryKey: ["admin", "cj"] });
              onImported();
            }}
          />
        )}
      </div>
    </div>
  );
}

function ImportForm({ pid, preview, settings, onImported }: {
  pid: string; preview: CjProductPreview; settings: CjSettingsRead | undefined; onImported: () => void;
}) {
  const [name, setName] = useState(preview.name_en.slice(0, 255));
  const [description, setDescription] = useState(preview.description_text);
  const [creditPct, setCreditPct] = useState(String(settings?.default_credit_percentage ?? 100));
  const generalMarkup = settings?.markup_percentage ?? 100;
  const [markup, setMarkup] = useState(String(generalMarkup));
  const markupValue = markup.trim() === "" || Number.isNaN(Number(markup)) ? generalMarkup : Number(markup);
  const priceOf = (costUsd: number, serverPrice: number) =>
    settings ? salePriceCents(costUsd, settings, markupValue, preview.shipping_estimate_usd) : serverPrice;
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(preview.variants.filter((v) => v.inventory > 0).map((v) => v.vid))
  );
  const [activate, setActivate] = useState(true);
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  async function handleImport() {
    setLoading(true);
    setSubmitError(null);
    try {
      await postJson("/api/proxy/cj/products", {
        pid,
        name: name.trim(),
        description,
        credit_discount_percentage: Number(creditPct),
        // Same as the general markup: nothing saved on the product, so it
        // keeps following the general setting when that changes.
        markup_percentage: markupValue === generalMarkup ? null : markupValue,
        vids: Array.from(selected),
        activate,
      });
      onImported();
    } catch (err: any) {
      setSubmitError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
          <div className="grid grid-cols-1 md:grid-cols-5 gap-5">
            <div className="md:col-span-2 space-y-3">
              <div className="aspect-square rounded-xl overflow-hidden bg-white border border-white/10">
                <ProductThumbnail imageUrl={preview.images[0]} alt={preview.name_en} className="w-full h-full object-contain" />
              </div>
              <div className="flex gap-1.5 overflow-x-auto">
                {preview.images.slice(1, 8).map((src) => (
                  <div key={src} className="w-12 h-12 shrink-0 rounded-md overflow-hidden bg-white">
                    <ProductThumbnail imageUrl={src} alt="" className="w-full h-full object-cover" />
                  </div>
                ))}
              </div>
              <div className="text-xs space-y-1 text-slate-400 light:text-slate-500">
                <p>SKU CJ <span className="font-mono">{preview.sku}</span> · {preview.category_name}</p>
                <p>Parte da: <strong className="text-white light:text-slate-900">{preview.origin_country}</strong></p>
                {preview.ships_to_destination ? (
                  <p>Spedizione più economica: <strong className="text-white light:text-slate-900">{preview.shipping_carrier}</strong>,
                    {" "}{usd(preview.shipping_estimate_usd)} ≈ {euro(preview.shipping_estimate_cents ?? 0)}, {preview.shipping_days} giorni</p>
                ) : (
                  <p className="text-rose-400">CJ non spedisce questo prodotto in {settings?.destination_country ?? "Italia"}: non è importabile.</p>
                )}
              </div>
            </div>
            <div className="md:col-span-3 space-y-3">
              <div>
                <span className={label}>Nome in vendita (traducilo in italiano)</span>
                <input className={input} value={name} maxLength={255} onChange={(e) => setName(e.target.value)} />
                <p className="text-[10px] text-slate-500 mt-0.5">Originale: {preview.name_en}</p>
              </div>
              <div>
                <span className={label}>Descrizione</span>
                <textarea className={`${input} min-h-[110px]`} value={description} maxLength={8000} onChange={(e) => setDescription(e.target.value)} />
              </div>
              <div>
                <span className={label}>Varianti da vendere</span>
                <div className="max-h-56 overflow-y-auto rounded-xl border border-white/10 light:border-slate-200 divide-y divide-white/5 light:divide-slate-200">
                  {preview.variants.map((v) => (
                    <label key={v.vid} className={`flex items-center gap-3 px-3 py-2 text-xs cursor-pointer ${v.inventory === 0 ? "opacity-50" : ""}`}>
                      <input type="checkbox" checked={selected.has(v.vid)}
                        onChange={(e) => {
                          const next = new Set(selected);
                          if (e.target.checked) next.add(v.vid); else next.delete(v.vid);
                          setSelected(next);
                        }} />
                      <span className="w-8 h-8 rounded overflow-hidden bg-white shrink-0">
                        <ProductThumbnail imageUrl={v.image_url} alt="" className="w-full h-full object-cover" iconClassName="w-4 h-4 text-orange-400/40" />
                      </span>
                      <span className="flex-1 min-w-0 truncate text-slate-200 light:text-slate-800">{v.label}</span>
                      <span className="text-slate-500 shrink-0">{usd(v.cost_usd.toFixed(2))}</span>
                      <span className="font-bold text-orange-400 shrink-0 w-16 text-right">{euro(priceOf(v.cost_usd, v.price_cents))}</span>
                      <span className="text-slate-500 shrink-0 w-16 text-right">{v.inventory} pz</span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-3 gap-3 items-end">
                <div>
                  <span className={label}>Ricarico %</span>
                  <input className={input} inputMode="numeric" value={markup} onChange={(e) => setMarkup(e.target.value)} />
                </div>
                <div>
                  <span className={label}>LialCash usabili (%)</span>
                  <input className={input} inputMode="numeric" value={creditPct} onChange={(e) => setCreditPct(e.target.value)} />
                </div>
                <label className="flex items-center gap-2 text-xs text-slate-300 light:text-slate-600 pb-2 cursor-pointer">
                  <input type="checkbox" checked={activate} onChange={(e) => setActivate(e.target.checked)} />
                  Metti subito in vendita
                </label>
              </div>
              <p className="text-[11px] text-slate-500 -mt-1">
                {markupValue === generalMarkup
                  ? `Ricarico generale (${generalMarkup}%): se lo cambi in Impostazioni, questo prodotto si aggiorna.`
                  : `Ricarico solo per questo prodotto (${markupValue}%). Lo cambi quando vuoi da Prodotti in vendita → Modifica.`}
              </p>
              <ErrorBox message={submitError} />
              <button
                className={`${btnPrimary} w-full py-2.5`}
                disabled={loading || !preview.ships_to_destination || selected.size === 0 || !name.trim()}
                onClick={handleImport}
              >
                {loading ? "Importazione..." : `Importa ${selected.size} ${selected.size === 1 ? "variante" : "varianti"}`}
              </button>
            </div>
          </div>
  );
}

// --- Prodotti in vendita ----------------------------------------------------------------------

function ProductsTab() {
  const queryClient = useQueryClient();
  const { data: products, error } = useQuery({
    queryKey: ["admin", "cj", "products"],
    queryFn: () => getJson<CjProductAdminRead[]>("/api/proxy/cj/products"),
  });
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<CjProductAdminRead | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const filtered = (products ?? []).filter((p) =>
    !search.trim() || p.name.toLowerCase().includes(search.toLowerCase()) || (p.cj_sku ?? "").toLowerCase().includes(search.toLowerCase())
  );
  const pagination = usePagination(filtered);

  async function act(product: CjProductAdminRead, action: "sync" | "toggle") {
    setBusyId(product.id);
    setActionError(null);
    try {
      if (action === "sync") await postJson(`/api/proxy/cj/products/${product.id}/sync`);
      else await postJson(`/api/proxy/cj/products/${product.id}`, { status: product.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" }, "PATCH");
      await queryClient.invalidateQueries({ queryKey: ["admin", "cj", "products"] });
    } catch (err: any) {
      setActionError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  if (error) return <ErrorBox message={(error as Error).message} />;
  if (!products) return <div className={`${card} h-40 animate-pulse`} />;
  if (products.length === 0) {
    return <p className={`${card} p-8 text-center text-sm text-slate-400`}>Nessun prodotto ancora: importali da “Catalogo CJ”.</p>;
  }

  return (
    <div className="space-y-3">
      <input className={input} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cerca per nome o SKU..." />
      <ErrorBox message={actionError} />
      <div className={`${card} divide-y divide-white/5 light:divide-slate-200 overflow-hidden`}>
        {pagination.pageItems.map((p) => {
          const prices = p.variants.filter((v) => v.active && v.available_on_cj).map((v) => v.effective_price_cents);
          const stock = p.variants.reduce((sum, v) => sum + (v.active ? v.inventory : 0), 0);
          return (
            <div key={p.id} className="p-4 flex flex-wrap items-center gap-4">
              <div className="w-14 h-14 rounded-lg overflow-hidden bg-white shrink-0">
                <ProductThumbnail imageUrl={p.image_url} alt={p.name} className="w-full h-full object-cover" />
              </div>
              <div className="flex-1 min-w-[200px]">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-semibold text-white light:text-slate-900">{p.name}</p>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${p.status === "ACTIVE" ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" : "bg-slate-500/10 border-slate-500/30 text-slate-400"}`}>
                    {p.status === "ACTIVE" ? "In vendita" : "Nascosto"}
                  </span>
                  {stock === 0 && <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-rose-500/10 border-rose-500/30 text-rose-400">Esaurito</span>}
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  {prices.length ? (Math.min(...prices) === Math.max(...prices) ? euro(prices[0] ?? 0) : `${euro(Math.min(...prices))} – ${euro(Math.max(...prices))}`) : "—"}
                  {" "}· {p.variants.length} varianti · {stock} pz · LialCash {p.credit_discount_percentage}% · {p.paid_orders} venduti
                </p>
                <p className="text-[10px] text-slate-500">Aggiornato da CJ {formatDate(p.last_synced_at)}{p.markup_percentage !== null ? ` · ricarico ${p.markup_percentage}%` : ""}</p>
                {p.sync_error && <p className="text-[11px] text-amber-400 mt-0.5">{p.sync_error}</p>}
              </div>
              <div className="flex flex-wrap gap-2">
                <button className={btnGhost} onClick={() => setEditing(p)}>Modifica</button>
                <button className={btnGhost} disabled={busyId === p.id} onClick={() => act(p, "sync")}>{busyId === p.id ? "..." : "Aggiorna da CJ"}</button>
                <button className={btnGhost} disabled={busyId === p.id} onClick={() => act(p, "toggle")}>{p.status === "ACTIVE" ? "Nascondi" : "Metti in vendita"}</button>
              </div>
            </div>
          );
        })}
      </div>
      <Pagination {...pagination} label="prodotti" />
      {editing && <EditProductModal product={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function EditProductModal({ product, onClose }: { product: CjProductAdminRead; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(product.name);
  const [description, setDescription] = useState(product.description);
  const [creditPct, setCreditPct] = useState(String(product.credit_discount_percentage));
  const [markup, setMarkup] = useState(product.markup_percentage === null ? "" : String(product.markup_percentage));
  const [image, setImage] = useState(product.image_url);
  const [variants, setVariants] = useState(product.variants);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setLoading(true);
    setError(null);
    try {
      await postJson(`/api/proxy/cj/products/${product.id}`, {
        name: name.trim(),
        description,
        image_url: image,
        credit_discount_percentage: Number(creditPct),
        markup_percentage: markup.trim() === "" ? null : Number(markup),
      }, "PATCH");
      for (const v of variants) {
        const original = product.variants.find((o) => o.id === v.id);
        if (!original) continue;
        if (original.active !== v.active || original.price_override_cents !== v.price_override_cents || original.label !== v.label) {
          await postJson(`/api/proxy/cj/variants/${v.id}`, {
            active: v.active, label: v.label, price_override_cents: v.price_override_cents,
          }, "PATCH");
        }
      }
      await queryClient.invalidateQueries({ queryKey: ["admin", "cj", "products"] });
      onClose();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-3xl max-h-[92vh] overflow-y-auto glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-white light:text-slate-900">Modifica prodotto</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-slate-400 cursor-pointer" aria-label="Chiudi">✕</button>
        </div>
        <div>
          <span className={label}>Nome</span>
          <input className={input} value={name} maxLength={255} onChange={(e) => setName(e.target.value)} />
          {product.name_en && <p className="text-[10px] text-slate-500 mt-0.5">Originale CJ: {product.name_en}</p>}
        </div>
        <div>
          <span className={label}>Descrizione</span>
          <textarea className={`${input} min-h-[120px]`} value={description} maxLength={8000} onChange={(e) => setDescription(e.target.value)} />
        </div>
        {product.images.length > 1 && (
          <div>
            <span className={label}>Foto principale</span>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {product.images.map((src) => (
                <button key={src} type="button" onClick={() => setImage(src)}
                  className={`w-14 h-14 shrink-0 rounded-lg overflow-hidden bg-white border-2 cursor-pointer ${image === src ? "border-orange-500" : "border-transparent"}`}>
                  <ProductThumbnail imageUrl={src} alt="" className="w-full h-full object-cover" />
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <span className={label}>LialCash usabili (%)</span>
            <input className={input} inputMode="numeric" value={creditPct} onChange={(e) => setCreditPct(e.target.value)} />
          </div>
          <div>
            <span className={label}>Ricarico % solo per questo prodotto</span>
            <input className={input} inputMode="numeric" value={markup} placeholder="vuoto = quello generale" onChange={(e) => setMarkup(e.target.value)} />
          </div>
        </div>
        <div>
          <span className={label}>Varianti</span>
          <div className="rounded-xl border border-white/10 light:border-slate-200 divide-y divide-white/5 light:divide-slate-200">
            {variants.map((v, i) => (
              <div key={v.id} className={`flex flex-wrap items-center gap-3 px-3 py-2 text-xs ${!v.available_on_cj ? "opacity-50" : ""}`}>
                <input type="checkbox" checked={v.active} title="In vendita"
                  onChange={(e) => setVariants(variants.map((x, j) => (j === i ? { ...x, active: e.target.checked } : x)))} />
                <input className="flex-1 min-w-[120px] rounded-md glass-input px-2 py-1 text-xs" value={v.label}
                  onChange={(e) => setVariants(variants.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
                <span className="text-slate-500">CJ {usd(v.cost_usd.toFixed(2))}</span>
                <span className="text-slate-400">auto {euro(v.price_cents)}</span>
                <input className="w-24 rounded-md glass-input px-2 py-1 text-xs" inputMode="decimal"
                  placeholder="prezzo fisso €"
                  value={v.price_override_cents === null ? "" : (v.price_override_cents / 100).toFixed(2)}
                  onChange={(e) => {
                    const cents = e.target.value.trim() === "" ? null : Math.round((parseFloat(e.target.value.replace(",", ".")) || 0) * 100) || null;
                    setVariants(variants.map((x, j) => (j === i ? { ...x, price_override_cents: cents } : x)));
                  }} />
                <span className="text-slate-500 w-14 text-right">{v.inventory} pz</span>
                {!v.available_on_cj && <span className="text-rose-400">non più su CJ</span>}
              </div>
            ))}
          </div>
          <p className="text-[10px] text-slate-500 mt-1">Il prezzo fisso, se c&apos;è, sostituisce quello calcolato: non segue più il costo CJ.</p>
        </div>
        <ErrorBox message={error} />
        <div className="flex justify-end gap-2">
          <button className={btnGhost} onClick={onClose}>Annulla</button>
          <button className={btnPrimary} disabled={loading || !name.trim()} onClick={save}>{loading ? "Salvataggio..." : "Salva"}</button>
        </div>
      </div>
    </div>
  );
}

// --- Ordini ----------------------------------------------------------------------------------

const FULFILLMENT: Record<string, { label: string; className: string }> = {
  NOT_SENT: { label: "Da inviare a CJ", className: "bg-amber-500/10 border-amber-500/30 text-amber-400" },
  SENDING: { label: "Invio in corso", className: "bg-sky-500/10 border-sky-500/30 text-sky-400" },
  SENT: { label: "Su CJ, da pagare", className: "bg-amber-500/10 border-amber-500/30 text-amber-400" },
  PROCESSING: { label: "In lavorazione su CJ", className: "bg-sky-500/10 border-sky-500/30 text-sky-400" },
  SHIPPED: { label: "Spedito", className: "bg-indigo-500/10 border-indigo-500/30 text-indigo-400" },
  DELIVERED: { label: "Consegnato", className: "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" },
  ERROR: { label: "Errore invio", className: "bg-rose-500/10 border-rose-500/30 text-rose-400" },
  CJ_CANCELLED: { label: "Annullato da CJ", className: "bg-rose-500/10 border-rose-500/30 text-rose-400" },
};

const ORDER_FILTERS: { key: string; label: string; match: (o: CjOrderRead) => boolean }[] = [
  { key: "todo", label: "Da gestire", match: (o) => o.status === "PAID" && ["NOT_SENT", "ERROR", "SENT", "CJ_CANCELLED"].includes(o.fulfillment_status) },
  { key: "unpaid", label: "In attesa di pagamento", match: (o) => o.status === "AWAITING_PAYMENT" },
  { key: "moving", label: "In viaggio", match: (o) => o.status === "PAID" && ["SENDING", "PROCESSING", "SHIPPED"].includes(o.fulfillment_status) },
  { key: "delivered", label: "Consegnati", match: (o) => o.fulfillment_status === "DELIVERED" },
  { key: "all", label: "Tutti", match: () => true },
];

function OrdersTab() {
  const queryClient = useQueryClient();
  const { data: orders, error } = useQuery({
    queryKey: ["admin", "cj", "orders"],
    queryFn: () => getJson<CjOrderRead[]>("/api/proxy/cj/orders"),
    refetchInterval: 60_000,
  });
  const [filter, setFilter] = useState("todo");
  const [search, setSearch] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const active = ORDER_FILTERS.find((f) => f.key === filter) ?? ORDER_FILTERS[0]!;
  const needle = search.trim().toLowerCase();
  const filtered = (orders ?? []).filter(active.match).filter((o) =>
    !needle
    || o.id.slice(0, 8).toLowerCase().includes(needle)
    || o.product_name.toLowerCase().includes(needle)
    || o.customer_display_name.toLowerCase().includes(needle)
    || (o.tracking_number ?? "").toLowerCase().includes(needle)
  );
  const pagination = usePagination(filtered);

  async function act(order: CjOrderRead, action: "forward" | "sync") {
    setBusyId(order.id);
    setActionError(null);
    try {
      const updated = await postJson<CjOrderRead>(`/api/proxy/cj/orders/${order.id}/${action}`);
      if (action === "forward" && updated.forward_error) setActionError(updated.forward_error);
      await queryClient.invalidateQueries({ queryKey: ["admin", "cj", "orders"] });
      await queryClient.invalidateQueries({ queryKey: ["admin", "orders"] });
    } catch (err: any) {
      setActionError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  if (error) return <ErrorBox message={(error as Error).message} />;
  if (!orders) return <div className={`${card} h-40 animate-pulse`} />;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {ORDER_FILTERS.map((f) => {
          const count = orders.filter(f.match).length;
          return (
            <button key={f.key} onClick={() => setFilter(f.key)}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold border transition cursor-pointer ${
                filter === f.key ? "bg-orange-600 border-orange-600 text-white" : "bg-white/5 light:bg-slate-900/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 hover:bg-white/10"
              }`}>
              {f.label} <span className="opacity-70">({count})</span>
            </button>
          );
        })}
      </div>
      <input className={input} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cerca per ordine, cliente, prodotto o tracking..." />
      <p className="text-[11px] text-slate-500">
        Il pagamento dei clienti (bonifico da confermare, annullamenti) si gestisce anche da “Ordini”. Stato e tracking si aggiornano da CJ ogni 30 minuti.
      </p>
      <ErrorBox message={actionError} />

      {filtered.length === 0 ? (
        <p className={`${card} p-8 text-center text-sm text-slate-500`}>Nessun ordine qui.</p>
      ) : (
        <div className={`${card} divide-y divide-white/5 light:divide-slate-200 overflow-hidden`}>
          {pagination.pageItems.map((o) => {
            const f = FULFILLMENT[o.fulfillment_status];
            const canForward = o.status === "PAID" && ["NOT_SENT", "ERROR", "SENT"].includes(o.fulfillment_status);
            const open = openId === o.id;
            return (
              <div key={o.id} className="p-4">
                <div className="flex flex-wrap items-start gap-4">
                  <div className="w-12 h-12 rounded-lg overflow-hidden bg-white shrink-0">
                    <ProductThumbnail imageUrl={o.product_image_url} alt="" className="w-full h-full object-cover" />
                  </div>
                  <div className="flex-1 min-w-[220px]">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-white light:text-slate-900">{o.customer_display_name}</span>
                      <span className="text-xs text-slate-500 font-mono">#{o.id.slice(0, 8).toUpperCase()}</span>
                      {o.status === "AWAITING_PAYMENT" && <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-amber-500/10 border-amber-500/30 text-amber-400">Non pagato</span>}
                      {o.status === "CANCELLED" && <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-rose-500/10 border-rose-500/30 text-rose-400">Annullato</span>}
                      {o.status === "PAID" && f && <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${f.className}`}>{f.label}</span>}
                      {o.sandbox && <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-white/5 border-white/10 text-slate-400">sandbox</span>}
                    </div>
                    <p className="text-xs text-slate-400 light:text-slate-500 mt-0.5">
                      {o.product_name} · {o.variant_label} × {o.quantity} · {euro(o.amount_cents)}
                      {o.estimated_margin_cents !== undefined && (
                        <span className={o.estimated_margin_cents >= 0 ? "text-emerald-400" : "text-rose-400"}> · margine ≈ {euro(o.estimated_margin_cents)}</span>
                      )}
                    </p>
                    <p className="text-[11px] text-slate-500">
                      {formatDate(o.created_at)} · {o.city} ({o.province}) · {o.logistic_name}
                      {o.tracking_number && <> · tracking <span className="font-mono">{o.tracking_number}</span></>}
                    </p>
                    {o.forward_error && <p className="text-[11px] text-rose-400 mt-0.5">{o.forward_error}</p>}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {canForward && (
                      <button className={btnPrimary} disabled={busyId === o.id} onClick={() => act(o, "forward")}>
                        {busyId === o.id ? "Invio..." : o.fulfillment_status === "SENT" ? "Paga su CJ" : o.fulfillment_status === "ERROR" ? "Riprova invio" : "Invia a CJ"}
                      </button>
                    )}
                    {o.cj_order_id && (
                      <button className={btnGhost} disabled={busyId === o.id} onClick={() => act(o, "sync")}>Aggiorna stato</button>
                    )}
                    {o.tracking_url && (
                      <a className={btnGhost} href={o.tracking_url} target="_blank" rel="noopener noreferrer">Traccia</a>
                    )}
                    <button className={btnGhost} onClick={() => setOpenId(open ? null : o.id)}>{open ? "Chiudi" : "Dettagli"}</button>
                  </div>
                </div>
                {open && (
                  <div className="mt-3 pt-3 border-t border-white/5 light:border-slate-200 grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-slate-400 light:text-slate-500">
                    <div className="space-y-0.5">
                      <p className="font-semibold text-slate-300 light:text-slate-700">Consegna</p>
                      <p>{o.recipient_name} · {o.recipient_phone}</p>
                      <p>{o.address_line1}{o.address_line2 ? `, ${o.address_line2}` : ""}</p>
                      <p>{o.postal_code} {o.city} ({o.province}) {o.country_code}</p>
                    </div>
                    <div className="space-y-0.5">
                      <p className="font-semibold text-slate-300 light:text-slate-700">Importi</p>
                      <p>Prezzo {o.quantity} × {euro(o.unit_price_cents)} + spedizione {euro(o.shipping_cents)}</p>
                      <p>LialCash {euro(o.credit_applied_cents)} · in euro {euro(o.residual_amount_cents)} ({o.payment_method === "CARD" ? "carta" : "bonifico"})</p>
                      <p>Costo CJ {usd(((o.unit_cost_usd ?? 0) * o.quantity).toFixed(2))} + sped. {usd((o.shipping_cost_usd ?? 0).toFixed(2))} · cambio {o.usd_eur_rate}</p>
                      {o.cj_amount_usd != null && <p>Addebitato da CJ {usd(o.cj_amount_usd.toFixed(2))}</p>}
                    </div>
                    <div className="space-y-0.5">
                      <p className="font-semibold text-slate-300 light:text-slate-700">CJ</p>
                      <p>Ordine CJ <span className="font-mono">{o.cj_order_id ?? "—"}</span> · {o.cj_order_status ?? "—"}</p>
                      <p>Parte da {o.origin_country} · {o.shipping_days ?? "?"} giorni</p>
                      <p>Inviato {formatDate(o.forwarded_at)} · ultimo controllo {formatDate(o.last_cj_sync_at)}</p>
                      {o.shipped_at && <p>Spedito {formatDate(o.shipped_at)}</p>}
                      {o.delivered_at && <p>Consegnato {formatDate(o.delivered_at)}</p>}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      <Pagination {...pagination} label="ordini" />
    </div>
  );
}
