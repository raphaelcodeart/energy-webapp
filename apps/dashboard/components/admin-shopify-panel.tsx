"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { friendlyApiError } from "@/lib/api-error";
import { Pagination, usePagination } from "@/components/pagination";
import { ProductThumbnail } from "@/components/product-thumbnail";
import type {
  ShopifyCatalogPage,
  ShopifyCatalogProduct,
  ShopifyOrderRead,
  ShopifyProductAdminRead,
  ShopifySettingsRead,
} from "@/lib/types";

type Tab = "orders" | "products" | "catalog" | "settings";

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function money(amount: number | null | undefined, currency: string | null | undefined): string {
  if (amount === null || amount === undefined) return "—";
  return `${amount.toFixed(2)} ${currency ?? ""}`.trim();
}

/** Same formula as the server (shopify_dropshipping/pricing.py), to show a
 *  price while the administrator types; the server's figure is what counts. */
function salePriceCents(
  cost: number | null, price: number,
  rules: Pick<ShopifySettingsRead, "currency_rate" | "price_basis" | "markup_fixed_cents" | "price_rounding" | "shipping_mode" | "shipping_flat_cents">,
  markupPct: number,
): number {
  const base = rules.price_basis === "COST" && cost !== null && cost > 0 ? cost : price;
  let cents = base * Number(rules.currency_rate) * 100 * (1 + markupPct / 100) + Number(rules.markup_fixed_cents);
  if (rules.shipping_mode === "INCLUDED") cents += Number(rules.shipping_flat_cents);
  const rounded = Math.ceil(Math.round(cents * 1e6) / 1e6);
  if (rules.price_rounding === "NONE") return rounded;
  const target = Number(rules.price_rounding);
  const euros = Math.floor(rounded / 100);
  return rounded % 100 <= target ? euros * 100 + target : (euros + 1) * 100 + target;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("it-IT", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** gid://shopify/Order/123 -> the order's page in the store admin. */
function storeAdminUrl(domain: string | null | undefined, gid: string | null | undefined, kind: "orders" | "products"): string | null {
  if (!domain || !gid) return null;
  const id = gid.split("/").pop();
  return id ? `https://${domain}/admin/${kind}/${id}` : null;
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

/** Marketplace 3 -- Shopify dropshipping (Session 68).
 *
 *  Same page as "Prodotti CJ Dropshipping": products come from the
 *  organization's Shopify store (where a dropshipping app keeps the
 *  catalog), are re-priced in euro with our markup and sold in the customer
 *  Shop with the checkout of every other Marketplace. A paid order is created
 *  in the Shopify store (by hand or automatically) and followed until
 *  delivery. Confirming bank transfers stays in the unified "Ordini".
 */
export function AdminShopifyPanel() {
  const { data: settings } = useQuery({
    queryKey: ["admin", "shopify", "settings"],
    queryFn: () => getJson<ShopifySettingsRead>("/api/proxy/shopify/settings"),
  });
  const [tab, setTab] = useState<Tab | null>(null);
  const configured = !!settings?.shop_domain && !!settings?.access_token_configured;
  const activeTab: Tab = tab ?? (settings && !configured ? "settings" : "orders");

  const tabs: { key: Tab; label: string }[] = [
    { key: "orders", label: "Ordini" },
    { key: "products", label: "Prodotti in vendita" },
    { key: "catalog", label: "Catalogo Shopify" },
    { key: "settings", label: "Impostazioni" },
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-white light:text-slate-900">Prodotti Shopify Dropshipping</h2>
          <p className="text-xs text-slate-400 light:text-slate-500 mt-0.5">
            Prodotti del tuo negozio Shopify venduti nello Shop: importa, prezza, invia gli ordini al negozio e seguili fino alla consegna.
          </p>
        </div>
        {settings && (
          <div className="flex flex-wrap gap-2 text-[11px] font-semibold">
            <span className={`px-2.5 py-1 rounded-full border ${settings.enabled ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" : "bg-slate-500/10 border-slate-500/30 text-slate-400"}`}>
              {settings.enabled ? "Shop attivo" : "Shop spento"}
            </span>
            {settings.shop_name && (
              <span className="px-2.5 py-1 rounded-full border bg-white/5 border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600">
                {settings.shop_name} · {settings.shop_currency}
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

      {activeTab === "settings" && (settings ? <SettingsForm settings={settings} /> : <div className={`${card} h-40 animate-pulse`} />)}
      {activeTab === "catalog" && <CatalogTab settings={settings} configured={configured} onImported={() => setTab("products")} />}
      {activeTab === "products" && <ProductsTab settings={settings} />}
      {activeTab === "orders" && <OrdersTab settings={settings} />}
    </div>
  );
}

// --- Impostazioni -----------------------------------------------------------------------

function SettingsForm({ settings }: { settings: ShopifySettingsRead }) {
  const queryClient = useQueryClient();
  const [token, setToken] = useState("");
  const [form, setForm] = useState<ShopifySettingsRead>(settings);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const body = {
        shop_domain: form.shop_domain ?? "",
        api_version: form.api_version,
        enabled: form.enabled,
        currency_rate: Number(form.currency_rate),
        price_basis: form.price_basis,
        markup_percentage: Number(form.markup_percentage),
        markup_fixed_cents: Number(form.markup_fixed_cents),
        price_rounding: form.price_rounding,
        shipping_mode: form.shipping_mode,
        shipping_flat_cents: Number(form.shipping_flat_cents),
        shipping_days: form.shipping_days || null,
        default_credit_percentage: Number(form.default_credit_percentage),
        auto_forward: form.auto_forward,
        ...(token.trim() ? { access_token: token.trim() } : {}),
      };
      const saved = await postJson<ShopifySettingsRead>("/api/proxy/shopify/settings", body, "PATCH");
      setForm(saved);
      setToken("");
      queryClient.setQueryData(["admin", "shopify", "settings"], saved);
      queryClient.invalidateQueries({ queryKey: ["admin", "shopify", "products"] });
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
      const saved = await postJson<ShopifySettingsRead>("/api/proxy/shopify/settings/test");
      setForm({ ...form, shop_name: saved.shop_name, shop_currency: saved.shop_currency, shop_domain: saved.shop_domain, last_connected_at: saved.last_connected_at });
      queryClient.setQueryData(["admin", "shopify", "settings"], saved);
      setNotice(
        `Connessione riuscita: negozio "${saved.shop_name}", valuta ${saved.shop_currency}.` +
          (saved.shop_currency && saved.shop_currency !== "EUR" ? " Imposta il cambio verso l'euro qui a destra." : "")
      );
    } catch (err: any) {
      setError(err.message);
    } finally {
      setTesting(false);
    }
  }

  const sampleCents = salePriceCents(10, 10, form, Number(form.markup_percentage));
  const setNum = (key: keyof ShopifySettingsRead) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [key]: e.target.value as unknown as number });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
      <div className={`${card} p-5 space-y-4`}>
        <h3 className="text-sm font-bold text-white light:text-slate-900">Collegamento al negozio Shopify</h3>
        <details className="rounded-xl border border-orange-500/20 bg-orange-500/5 p-3 text-xs text-slate-300 light:text-slate-600" open={!settings.access_token_configured}>
          <summary className="font-semibold cursor-pointer text-orange-400">Come ottenere dominio e token (una volta sola)</summary>
          <ol className="list-decimal pl-5 mt-2 space-y-1">
            <li>Nel pannello Shopify: <strong>Impostazioni → App e canali di vendita → Sviluppa app</strong> (abilita lo sviluppo di app se richiesto).</li>
            <li><strong>Crea un&apos;app</strong> (es. &ldquo;Lial Energy&rdquo;) → <strong>Configura gli ambiti dell&apos;API Admin</strong> e spunta:
              <span className="block font-mono text-[11px] mt-1">read_products, read_inventory, read_orders, write_draft_orders, read_fulfillments</span>
              <span className="block text-[11px] text-slate-500">(read_assigned_fulfillment_orders se la tua app di dropshipping lo richiede per il tracking)</span>
            </li>
            <li><strong>Installa l&apos;app</strong> e copia il <strong>token di accesso API Admin</strong> (inizia con <span className="font-mono">shpat_</span>): Shopify lo mostra una volta sola.</li>
            <li>Il dominio è quello <span className="font-mono">nome-negozio.myshopify.com</span> (lo vedi in Impostazioni → Domini).</li>
            <li>Nel negozio, l&apos;app di dropshipping (DSers, Syncee, Spocket…) deve evadere in automatico gli ordini pagati: noi creiamo l&apos;ordine già pagato con il tag <span className="font-mono">lialenergy</span>.</li>
          </ol>
        </details>
        <div>
          <span className={label}>Dominio del negozio</span>
          <input className={input} value={form.shop_domain ?? ""} placeholder="nome-negozio.myshopify.com"
            onChange={(e) => setForm({ ...form, shop_domain: e.target.value })} />
        </div>
        <div>
          <span className={label}>Token API Admin</span>
          <input className={input} type="password" autoComplete="off" value={token}
            placeholder={settings.access_token_configured ? `Salvato (${settings.access_token_hint}) — scrivi qui solo per cambiarlo` : "shpat_..."}
            onChange={(e) => setToken(e.target.value)} />
          <p className="text-[11px] text-slate-500 mt-1">Resta salvato sul server e non viene mai mostrato.</p>
        </div>
        <div>
          <span className={label}>Versione API</span>
          <input className={input} value={form.api_version} onChange={(e) => setForm({ ...form, api_version: e.target.value })} />
          <p className="text-[11px] text-slate-500 mt-1">Formato AAAA-MM. Aggiornala quando Shopify ritira quella in uso (ogni ~12 mesi).</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className={btnPrimary} disabled={saving} onClick={save}>Salva collegamento</button>
          <button className={btnGhost} disabled={testing || !settings.access_token_configured || !settings.shop_domain} onClick={test}>
            {testing ? "Verifica..." : "Verifica connessione"}
          </button>
        </div>
        <p className="text-xs text-slate-400 light:text-slate-500">
          Stato: {settings.last_connected_at
            ? <span className="text-emerald-400">collegato ({formatDate(settings.last_connected_at)})</span>
            : <span className="text-amber-400">non ancora verificato</span>}
        </p>

        <div className="pt-4 border-t border-white/5 light:border-slate-200 space-y-3">
          <Switch checked={form.enabled} onChange={(v) => setForm({ ...form, enabled: v })}
            title="Shop visibile ai clienti" hint="Aggiunge la scheda del Marketplace nello Shop del cliente." />
          <Switch checked={form.auto_forward} onChange={(v) => setForm({ ...form, auto_forward: v })}
            title="Invio automatico al negozio (consigliato)" hint="Appena il cliente ha pagato, l'ordine viene creato nel negozio Shopify già pagato: l'app di dropshipping lo evade. Se qualcosa va storto si riprova da solo; se il negozio lo rifiuta ricevi un avviso." />
        </div>
      </div>

      <div className={`${card} p-5 space-y-4`}>
        <h3 className="text-sm font-bold text-white light:text-slate-900">Prezzi e spedizione</h3>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <span className={label}>Il prezzo parte da</span>
            <select className={input} value={form.price_basis}
              onChange={(e) => setForm({ ...form, price_basis: e.target.value as ShopifySettingsRead["price_basis"] })}>
              <option value="COST">costo per articolo (fornitore)</option>
              <option value="PRICE">prezzo del negozio Shopify</option>
            </select>
          </div>
          <div>
            <span className={label}>Cambio 1 {form.shop_currency ?? "valuta negozio"} = EUR</span>
            <input className={input} inputMode="decimal" value={form.currency_rate} onChange={setNum("currency_rate")} />
          </div>
          <div>
            <span className={label}>Ricarico %</span>
            <input className={input} inputMode="numeric" value={form.markup_percentage} onChange={setNum("markup_percentage")} />
          </div>
          <div>
            <span className={label}>Ricarico fisso (€)</span>
            <input className={input} inputMode="decimal" value={(Number(form.markup_fixed_cents) / 100).toString()}
              onChange={(e) => setForm({ ...form, markup_fixed_cents: Math.round((parseFloat(e.target.value.replace(",", ".")) || 0) * 100) })} />
          </div>
          <div>
            <span className={label}>Arrotondamento</span>
            <select className={input} value={form.price_rounding}
              onChange={(e) => setForm({ ...form, price_rounding: e.target.value as ShopifySettingsRead["price_rounding"] })}>
              <option value="90">a ,90 (es. 12,90)</option>
              <option value="99">a ,99 (es. 12,99)</option>
              <option value="NONE">al centesimo</option>
            </select>
          </div>
          <div>
            <span className={label}>Spedizione</span>
            <select className={input} value={form.shipping_mode}
              onChange={(e) => setForm({ ...form, shipping_mode: e.target.value as ShopifySettingsRead["shipping_mode"] })}>
              <option value="CUSTOMER_PAYS">la paga il cliente (fissa)</option>
              <option value="INCLUDED">inclusa nel prezzo</option>
            </select>
          </div>
          <div>
            <span className={label}>Costo spedizione (€)</span>
            <input className={input} inputMode="decimal" value={(Number(form.shipping_flat_cents) / 100).toString()}
              onChange={(e) => setForm({ ...form, shipping_flat_cents: Math.round((parseFloat(e.target.value.replace(",", ".")) || 0) * 100) })} />
          </div>
          <div>
            <span className={label}>Tempi di consegna (giorni)</span>
            <input className={input} value={form.shipping_days ?? ""} placeholder="es. 7-15" onChange={(e) => setForm({ ...form, shipping_days: e.target.value })} />
          </div>
          <div className="col-span-2">
            <span className={label}>LialCash usabili sui nuovi prodotti (%)</span>
            <input className={input} inputMode="numeric" value={form.default_credit_percentage} onChange={setNum("default_credit_percentage")} />
            <span className="block text-[10px] text-slate-500 mt-1">
              30% consigliato, massimo {settings.max_credit_percentage}%: un prodotto dei Marketplace non si compra mai tutto in LialCash.
            </span>
          </div>
        </div>
        <div className="p-3 rounded-xl bg-orange-500/5 border border-orange-500/20 text-xs text-slate-300 light:text-slate-600">
          Esempio: un articolo che costa <strong>10 {form.shop_currency ?? ""}</strong> sarà in vendita a{" "}
          <strong className="text-orange-400">{euro(sampleCents)}</strong>
          {form.shipping_mode === "CUSTOMER_PAYS" ? ` + ${euro(Number(form.shipping_flat_cents))} di spedizione.` : " (spedizione inclusa)."}{" "}
          È il prezzo con bonifico istantaneo; con carta si aggiunge l&apos;aumento delle Regole dei Marketplace.
          <p className="text-[11px] text-slate-500 mt-1">
            Se un articolo non ha il &ldquo;costo per articolo&rdquo; in Shopify si parte dal suo prezzo. L&apos;arrotondamento è sempre per eccesso.
          </p>
        </div>
        <ErrorBox message={error} />
        {notice && <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">{notice}</div>}
        <button className={btnPrimary} disabled={saving} onClick={save}>{saving ? "Salvataggio..." : "Salva impostazioni"}</button>
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

// --- Catalogo del negozio ------------------------------------------------------------------

function CatalogTab({ settings, configured, onImported }: {
  settings: ShopifySettingsRead | undefined; configured: boolean; onImported: () => void;
}) {
  const [keyword, setKeyword] = useState("");
  const [query, setQuery] = useState<{ keyword: string; cursor: string | null; page: number } | null>(null);
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [preview, setPreview] = useState<ShopifyCatalogProduct | null>(null);

  const { data: results, error, isFetching } = useQuery({
    queryKey: ["admin", "shopify", "search", query],
    queryFn: () => {
      const q = query!;
      const params = new URLSearchParams();
      if (q.keyword) params.set("keyword", q.keyword);
      if (q.cursor) params.set("cursor", q.cursor);
      return getJson<ShopifyCatalogPage>(`/api/proxy/shopify/catalog/search?${params}`);
    },
    enabled: !!query,
    staleTime: 120_000,
  });

  if (!configured) {
    return <p className={`${card} p-6 text-sm text-slate-400`}>Prima collega il negozio Shopify in Impostazioni.</p>;
  }

  function goTo(page: number, list = cursors) {
    setQuery({ keyword: keyword.trim(), cursor: list[page] ?? null, page });
  }

  return (
    <div className="space-y-4">
      <form onSubmit={(e) => { e.preventDefault(); setCursors([null]); goTo(0, [null]); }} className={`${card} p-4 flex flex-col md:flex-row gap-3 md:items-end`}>
        <div className="flex-1">
          <span className={label}>Cerca nel negozio (titolo, SKU, fornitore) — vuoto = tutti</span>
          <input className={input} value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="es. cuffie, lampada, yoga" />
        </div>
        <button type="submit" className={btnPrimary} disabled={isFetching}>{isFetching ? "..." : "Cerca"}</button>
      </form>

      <ErrorBox message={error ? (error as Error).message : null} />

      {!query && (
        <p className="text-sm text-slate-500 text-center py-10">
          Cerca tra i prodotti attivi del negozio Shopify: vedi subito il prezzo a cui li venderesti, poi aprine uno per importarlo.
        </p>
      )}

      {results && (
        <>
          {results.items.length === 0 && <p className="text-sm text-slate-500 text-center py-6">Nessun prodotto trovato.</p>}
          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-3">
            {results.items.map((item) => (
              <button key={item.product_id} type="button" onClick={() => setPreview(item)}
                className={`${card} overflow-hidden text-left hover:border-orange-500/40 transition cursor-pointer`}>
                <div className="relative aspect-square bg-white">
                  <ProductThumbnail imageUrl={item.image_url} alt={item.title} className="w-full h-full object-cover" />
                  {item.already_imported && (
                    <span className="absolute top-1.5 left-1.5 px-2 py-0.5 rounded-full text-[9px] font-bold bg-emerald-500 text-white">Già importato</span>
                  )}
                </div>
                <div className="p-2.5">
                  <p className="text-[11px] text-slate-300 light:text-slate-700 line-clamp-2 min-h-[2rem]">{item.title}</p>
                  <div className="flex items-end justify-between mt-1.5">
                    <span className="text-[10px] text-slate-500">{item.variants.length} var.</span>
                    {item.min_price_cents !== null && <span className="text-sm font-bold text-orange-400">{euro(item.min_price_cents)}</span>}
                  </div>
                </div>
              </button>
            ))}
          </div>
          <div className="flex items-center justify-center gap-2">
            <button className={btnGhost} disabled={!query || query.page === 0 || isFetching} onClick={() => goTo((query?.page ?? 1) - 1)}>← Precedente</button>
            <button className={btnGhost} disabled={!results.next_cursor || isFetching}
              onClick={() => {
                const page = (query?.page ?? 0) + 1;
                const next = [...cursors.slice(0, page), results.next_cursor];
                setCursors(next);
                goTo(page, next);
              }}>Successiva →</button>
          </div>
        </>
      )}

      {preview && (
        <ImportModal product={preview} settings={settings} onClose={() => setPreview(null)} onImported={() => { setPreview(null); onImported(); }} />
      )}
    </div>
  );
}

function ImportModal({ product, settings, onClose, onImported }: {
  product: ShopifyCatalogProduct; settings: ShopifySettingsRead | undefined; onClose: () => void; onImported: () => void;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(product.title.slice(0, 255));
  const [description, setDescription] = useState(product.description_text);
  const [creditPct, setCreditPct] = useState(String(settings?.default_credit_percentage ?? 30));
  const generalMarkup = settings?.markup_percentage ?? 100;
  const [markup, setMarkup] = useState(String(generalMarkup));
  const markupValue = markup.trim() === "" || Number.isNaN(Number(markup)) ? generalMarkup : Number(markup);
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(product.variants.filter((v) => v.inventory === null || v.inventory > 0).map((v) => v.variant_id))
  );
  const [activate, setActivate] = useState(true);
  const [loading, setLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const priceOf = (v: ShopifyCatalogProduct["variants"][number]) =>
    settings ? salePriceCents(v.cost_amount, v.source_price_amount, settings, markupValue) : v.price_cents;

  async function handleImport() {
    setLoading(true);
    setSubmitError(null);
    try {
      await postJson("/api/proxy/shopify/products", {
        product_id: product.product_id,
        name: name.trim(),
        description,
        credit_discount_percentage: Number(creditPct),
        markup_percentage: markupValue === generalMarkup ? null : markupValue,
        variant_ids: Array.from(selected),
        activate,
      });
      await queryClient.invalidateQueries({ queryKey: ["admin", "shopify"] });
      onImported();
    } catch (err: any) {
      setSubmitError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-4xl max-h-[92vh] overflow-y-auto glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-white light:text-slate-900">Importa dal negozio Shopify</h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 text-slate-400 cursor-pointer" aria-label="Chiudi">✕</button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-5">
          <div className="md:col-span-2 space-y-3">
            <div className="aspect-square rounded-xl overflow-hidden bg-white border border-white/10">
              <ProductThumbnail imageUrl={product.images[0] ?? product.image_url} alt={product.title} className="w-full h-full object-contain" />
            </div>
            <div className="flex gap-1.5 overflow-x-auto">
              {product.images.slice(1, 8).map((src) => (
                <div key={src} className="w-12 h-12 shrink-0 rounded-md overflow-hidden bg-white">
                  <ProductThumbnail imageUrl={src} alt="" className="w-full h-full object-cover" />
                </div>
              ))}
            </div>
            <p className="text-xs text-slate-400 light:text-slate-500">
              {product.vendor ? `Fornitore ${product.vendor} · ` : ""}
              {product.already_imported && <span className="text-emerald-400">già importato</span>}
            </p>
          </div>
          <div className="md:col-span-3 space-y-3">
            <div>
              <span className={label}>Nome in vendita (in italiano)</span>
              <input className={input} value={name} maxLength={255} onChange={(e) => setName(e.target.value)} />
              <p className="text-[10px] text-slate-500 mt-0.5">Originale: {product.title}</p>
            </div>
            <div>
              <span className={label}>Descrizione</span>
              <textarea className={`${input} min-h-[110px]`} value={description} maxLength={8000} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <div>
              <span className={label}>Varianti da vendere</span>
              <div className="max-h-56 overflow-y-auto rounded-xl border border-white/10 light:border-slate-200 divide-y divide-white/5 light:divide-slate-200">
                {product.variants.map((v) => (
                  <label key={v.variant_id} className={`flex items-center gap-3 px-3 py-2 text-xs cursor-pointer ${v.inventory === 0 ? "opacity-50" : ""}`}>
                    <input type="checkbox" checked={selected.has(v.variant_id)}
                      onChange={(e) => {
                        const next = new Set(selected);
                        if (e.target.checked) next.add(v.variant_id); else next.delete(v.variant_id);
                        setSelected(next);
                      }} />
                    <span className="flex-1 min-w-0 truncate text-slate-200 light:text-slate-800">{v.label}{v.sku ? ` · ${v.sku}` : ""}</span>
                    <span className="text-slate-500 shrink-0" title="costo / prezzo nel negozio">
                      {v.cost_amount !== null ? `costo ${money(v.cost_amount, product.currency)}` : `prezzo ${money(v.source_price_amount, product.currency)}`}
                    </span>
                    <span className="font-bold text-orange-400 shrink-0 w-16 text-right">{euro(priceOf(v))}</span>
                    <span className="text-slate-500 shrink-0 w-14 text-right">{v.inventory === null ? "∞" : `${v.inventory} pz`}</span>
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
                : `Ricarico solo per questo prodotto (${markupValue}%).`}
              {" "}LialCash: massimo {settings?.max_credit_percentage ?? 99}%.
            </p>
            <ErrorBox message={submitError} />
            <button className={`${btnPrimary} w-full py-2.5`} disabled={loading || selected.size === 0 || !name.trim() || product.already_imported}
              onClick={handleImport}>
              {loading ? "Importazione..." : product.already_imported ? "Già importato" : `Importa ${selected.size} ${selected.size === 1 ? "variante" : "varianti"}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- Prodotti in vendita ----------------------------------------------------------------------

function ProductsTab({ settings }: { settings: ShopifySettingsRead | undefined }) {
  const queryClient = useQueryClient();
  const { data: products, error } = useQuery({
    queryKey: ["admin", "shopify", "products"],
    queryFn: () => getJson<ShopifyProductAdminRead[]>("/api/proxy/shopify/products"),
  });
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<ShopifyProductAdminRead | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const needle = search.trim().toLowerCase();
  const filtered = (products ?? []).filter((p) =>
    !needle || p.name.toLowerCase().includes(needle) || p.variants.some((v) => (v.sku ?? "").toLowerCase().includes(needle))
  );
  const pagination = usePagination(filtered);

  async function act(product: ShopifyProductAdminRead, action: "sync" | "toggle") {
    setBusyId(product.id);
    setActionError(null);
    try {
      if (action === "sync") await postJson(`/api/proxy/shopify/products/${product.id}/sync`);
      else await postJson(`/api/proxy/shopify/products/${product.id}`, { status: product.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" }, "PATCH");
      await queryClient.invalidateQueries({ queryKey: ["admin", "shopify", "products"] });
    } catch (err: any) {
      setActionError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  if (error) return <ErrorBox message={(error as Error).message} />;
  if (!products) return <div className={`${card} h-40 animate-pulse`} />;
  if (products.length === 0) {
    return <p className={`${card} p-8 text-center text-sm text-slate-400`}>Nessun prodotto ancora: importali da &ldquo;Catalogo Shopify&rdquo;.</p>;
  }

  return (
    <div className="space-y-3">
      <input className={input} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cerca per nome o SKU..." />
      <ErrorBox message={actionError} />
      <div className={`${card} divide-y divide-white/5 light:divide-slate-200 overflow-hidden`}>
        {pagination.pageItems.map((p) => {
          const live = p.variants.filter((v) => v.active && v.available_in_store);
          const prices = live.map((v) => v.effective_price_cents);
          const soldOut = live.length > 0 && live.every((v) => v.inventory !== null && v.inventory <= 0);
          const adminUrl = storeAdminUrl(settings?.shop_domain, p.shopify_product_id, "products");
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
                  {soldOut && <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-rose-500/10 border-rose-500/30 text-rose-400">Esaurito</span>}
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  {prices.length ? (Math.min(...prices) === Math.max(...prices) ? euro(prices[0] ?? 0) : `${euro(Math.min(...prices))} – ${euro(Math.max(...prices))}`) : "—"}
                  {" "}· {p.variants.length} varianti · LialCash {p.credit_discount_percentage}% · {p.paid_orders} venduti
                </p>
                <p className="text-[10px] text-slate-500">
                  Aggiornato dal negozio {formatDate(p.last_synced_at)}{p.markup_percentage !== null ? ` · ricarico ${p.markup_percentage}%` : ""}
                  {p.vendor ? ` · ${p.vendor}` : ""}
                </p>
                {p.sync_error && <p className="text-[11px] text-amber-400 mt-0.5">{p.sync_error}</p>}
              </div>
              <div className="flex flex-wrap gap-2">
                <button className={btnGhost} onClick={() => setEditing(p)}>Modifica</button>
                <button className={btnGhost} disabled={busyId === p.id} onClick={() => act(p, "sync")}>{busyId === p.id ? "..." : "Aggiorna dal negozio"}</button>
                <button className={btnGhost} disabled={busyId === p.id} onClick={() => act(p, "toggle")}>{p.status === "ACTIVE" ? "Nascondi" : "Metti in vendita"}</button>
                {adminUrl && <a className={btnGhost} href={adminUrl} target="_blank" rel="noopener noreferrer">Apri in Shopify</a>}
              </div>
            </div>
          );
        })}
      </div>
      <Pagination {...pagination} label="prodotti" />
      {editing && <EditProductModal product={editing} maxCredit={settings?.max_credit_percentage ?? 99} onClose={() => setEditing(null)} />}
    </div>
  );
}

function EditProductModal({ product, maxCredit, onClose }: { product: ShopifyProductAdminRead; maxCredit: number; onClose: () => void }) {
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
      await postJson(`/api/proxy/shopify/products/${product.id}`, {
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
          await postJson(`/api/proxy/shopify/variants/${v.id}`, {
            active: v.active, label: v.label, price_override_cents: v.price_override_cents,
          }, "PATCH");
        }
      }
      await queryClient.invalidateQueries({ queryKey: ["admin", "shopify", "products"] });
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
          {product.source_title && <p className="text-[10px] text-slate-500 mt-0.5">Nel negozio: {product.source_title}</p>}
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
            <span className={label}>LialCash usabili (%, max {maxCredit})</span>
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
              <div key={v.id} className={`flex flex-wrap items-center gap-3 px-3 py-2 text-xs ${!v.available_in_store ? "opacity-50" : ""}`}>
                <input type="checkbox" checked={v.active} title="In vendita"
                  onChange={(e) => setVariants(variants.map((x, j) => (j === i ? { ...x, active: e.target.checked } : x)))} />
                <input className="flex-1 min-w-[120px] rounded-md glass-input px-2 py-1 text-xs" value={v.label}
                  onChange={(e) => setVariants(variants.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
                <span className="text-slate-500">{v.cost_amount !== null ? `costo ${v.cost_amount.toFixed(2)}` : `prezzo ${v.source_price_amount.toFixed(2)}`}</span>
                <span className="text-slate-400">auto {euro(v.price_cents)}</span>
                <input className="w-24 rounded-md glass-input px-2 py-1 text-xs" inputMode="decimal" placeholder="prezzo fisso €"
                  value={v.price_override_cents === null ? "" : (v.price_override_cents / 100).toFixed(2)}
                  onChange={(e) => {
                    const cents = e.target.value.trim() === "" ? null : Math.round((parseFloat(e.target.value.replace(",", ".")) || 0) * 100) || null;
                    setVariants(variants.map((x, j) => (j === i ? { ...x, price_override_cents: cents } : x)));
                  }} />
                <span className="text-slate-500 w-14 text-right">{v.inventory === null ? "∞" : `${v.inventory} pz`}</span>
                {!v.available_in_store && <span className="text-rose-400">non più nel negozio</span>}
              </div>
            ))}
          </div>
          <p className="text-[10px] text-slate-500 mt-1">Il prezzo fisso, se c&apos;è, sostituisce quello calcolato: non segue più il costo del negozio.</p>
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

type Badge = { label: string; className: string };

const TONE = {
  ok: "bg-emerald-500/10 border-emerald-500/30 text-emerald-400",
  info: "bg-sky-500/10 border-sky-500/30 text-sky-400",
  warn: "bg-amber-500/10 border-amber-500/30 text-amber-400",
  bad: "bg-rose-500/10 border-rose-500/30 text-rose-400",
  muted: "bg-white/5 border-white/10 light:border-slate-300 text-slate-400",
};

const CUSTOMER_PAYMENT: Record<string, Badge> = {
  AWAITING_PAYMENT: { label: "Cliente: da pagare", className: TONE.warn },
  PAID: { label: "Cliente: pagato", className: TONE.ok },
  CANCELLED: { label: "Annullato", className: TONE.bad },
};

const STORE_ORDER: Record<string, Badge> = {
  NOT_SENT: { label: "Negozio: non creato", className: TONE.muted },
  SENDING: { label: "Negozio: invio in corso", className: TONE.info },
  SENT: { label: "Negozio: creato, in preparazione", className: TONE.info },
  SHIPPED: { label: "Spedito", className: TONE.info },
  DELIVERED: { label: "Consegnato", className: TONE.ok },
  ERROR: { label: "Negozio: errore", className: TONE.bad },
  CANCELLED: { label: "Annullato nel negozio", className: TONE.bad },
};

const ERROR_KIND: Record<string, string> = {
  TEMPORARY: "temporaneo, si riprova da solo",
  AUTHENTICATION: "token / permessi dell'app",
  VALIDATION: "dati rifiutati dal negozio",
  FATAL: "da verificare",
};

const ORDER_FILTERS: { key: string; label: string; match: (o: ShopifyOrderRead) => boolean }[] = [
  { key: "send", label: "Da inviare al negozio", match: (o) => o.status === "PAID" && ["NOT_SENT", "SENDING", "ERROR"].includes(o.fulfillment_status ?? "") },
  { key: "problems", label: "Problemi", match: (o) => o.status === "PAID" && ["ERROR", "CANCELLED"].includes(o.fulfillment_status ?? "") },
  { key: "unpaid", label: "Cliente non ha pagato", match: (o) => o.status === "AWAITING_PAYMENT" },
  { key: "moving", label: "In preparazione / in viaggio", match: (o) => ["SENT", "SHIPPED"].includes(o.fulfillment_status ?? "") },
  { key: "delivered", label: "Consegnati", match: (o) => o.fulfillment_status === "DELIVERED" },
  { key: "all", label: "Tutti", match: () => true },
];

function Pill({ badge }: { badge?: Badge }) {
  if (!badge) return null;
  return <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${badge.className}`}>{badge.label}</span>;
}

function OrdersTab({ settings }: { settings: ShopifySettingsRead | undefined }) {
  const queryClient = useQueryClient();
  const { data: orders, error } = useQuery({
    queryKey: ["admin", "shopify", "orders"],
    queryFn: () => getJson<ShopifyOrderRead[]>("/api/proxy/shopify/orders"),
    refetchInterval: 60_000,
  });
  const [filter, setFilter] = useState("send");
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
    || (o.shopify_order_name ?? "").toLowerCase().includes(needle)
    || (o.tracking_number ?? "").toLowerCase().includes(needle)
  );
  const pagination = usePagination(filtered);

  async function act(order: ShopifyOrderRead, action: "forward" | "sync") {
    setBusyId(order.id);
    setActionError(null);
    try {
      const updated = await postJson<ShopifyOrderRead>(`/api/proxy/shopify/orders/${order.id}/${action}`);
      if (updated.forward_error && updated.fulfillment_status === "ERROR") setActionError(updated.forward_error);
      await queryClient.invalidateQueries({ queryKey: ["admin", "shopify", "orders"] });
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
      <p className="text-[11px] text-slate-500">
        I bonifici si confermano da <strong>Ordini</strong>, come per tutti gli acquisti. Qui: invio al negozio Shopify e spedizione.
        {settings?.auto_forward ? " Invio automatico attivo: gli ordini pagati partono da soli." : " Invio automatico spento: usa “Crea nel negozio”."}
      </p>
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
      <input className={input} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cerca per ordine, cliente, prodotto, numero Shopify o tracking..." />
      <ErrorBox message={actionError} />

      {filtered.length === 0 ? (
        <p className={`${card} p-8 text-center text-sm text-slate-500`}>Nessun ordine qui.</p>
      ) : (
        <div className={`${card} divide-y divide-white/5 light:divide-slate-200 overflow-hidden`}>
          {pagination.pageItems.map((o) => {
            const customerPaid = o.status === "PAID";
            const canCreate = customerPaid && ["NOT_SENT", "ERROR"].includes(o.fulfillment_status ?? "") && !o.shopify_order_id;
            const storeUrl = storeAdminUrl(settings?.shop_domain, o.shopify_order_id, "orders");
            const open = openId === o.id;
            return (
              <div key={o.id} className={`p-4 ${o.fulfillment_status === "ERROR" ? "bg-rose-500/[0.04]" : ""}`}>
                <div className="flex flex-wrap items-start gap-4">
                  <div className="w-12 h-12 rounded-lg overflow-hidden bg-white shrink-0">
                    <ProductThumbnail imageUrl={o.product_image_url} alt="" className="w-full h-full object-cover" />
                  </div>
                  <div className="flex-1 min-w-[240px]">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-white light:text-slate-900">{o.customer_display_name}</span>
                      <span className="text-xs text-slate-500 font-mono">#{o.id.slice(0, 8).toUpperCase()}</span>
                    </div>
                    <div className="flex items-center gap-1.5 flex-wrap mt-1">
                      <Pill badge={CUSTOMER_PAYMENT[o.status]} />
                      {customerPaid && <Pill badge={STORE_ORDER[o.fulfillment_status ?? ""]} />}
                    </div>
                    <p className="text-xs text-slate-400 light:text-slate-500 mt-1">
                      {o.product_name} · {o.variant_label} × {o.quantity} · cliente {euro(o.amount_cents + o.card_surcharge_cents)}
                      {o.supplier_cost_cents != null && <> · costo ≈ {euro(o.supplier_cost_cents)}</>}
                      {o.estimated_margin_cents != null && (
                        <span className={o.estimated_margin_cents >= 0 ? "text-emerald-400" : "text-rose-400"}> · margine ≈ {euro(o.estimated_margin_cents)}</span>
                      )}
                    </p>
                    <p className="text-[11px] text-slate-500">
                      {formatDate(o.paid_at ?? o.created_at)} · {o.city} ({o.province})
                      {o.shopify_order_name && <> · Shopify <span className="font-mono">{o.shopify_order_name}</span></>}
                      {o.tracking_number && <> · tracking <span className="font-mono">{o.tracking_number}</span></>}
                    </p>
                    {o.forward_error && o.fulfillment_status === "ERROR" && (
                      <p className="text-[11px] text-rose-400 mt-0.5">
                        {o.forward_error}{o.last_error_kind ? ` (${ERROR_KIND[o.last_error_kind] ?? o.last_error_kind})` : ""}
                      </p>
                    )}
                    {o.next_retry_at && o.fulfillment_status === "ERROR" && (
                      <p className="text-[11px] text-slate-500">Nuovo tentativo automatico {formatDate(o.next_retry_at)} · tentativi {o.attempt_count}</p>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2 sm:justify-end">
                    {canCreate && (
                      <button className={btnPrimary} disabled={busyId === o.id} onClick={() => act(o, "forward")}>
                        {busyId === o.id ? "Invio..." : o.fulfillment_status === "ERROR" ? "Riprova nel negozio" : "Crea nel negozio"}
                      </button>
                    )}
                    {o.shopify_order_id && o.fulfillment_status !== "DELIVERED" && (
                      <button className={btnGhost} disabled={busyId === o.id} onClick={() => act(o, "sync")}>Aggiorna stato</button>
                    )}
                    {storeUrl && <a className={btnGhost} href={storeUrl} target="_blank" rel="noopener noreferrer">Apri in Shopify</a>}
                    {o.tracking_url && <a className={btnGhost} href={o.tracking_url} target="_blank" rel="noopener noreferrer">Traccia</a>}
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
                      <p>{o.shipping_days ?? "?"} giorni stimati</p>
                    </div>
                    <div className="space-y-0.5">
                      <p className="font-semibold text-slate-300 light:text-slate-700">Cliente</p>
                      <p>{o.quantity} × {euro(o.unit_price_cents)} + spedizione {euro(o.shipping_cents)} = {euro(o.amount_cents)}</p>
                      <p>
                        LialCash {euro(o.credit_applied_cents)} · in euro {euro(o.amount_due_cents)} ({o.payment_method === "CARD" ? "carta" : "bonifico"})
                        {o.card_surcharge_cents > 0 && <> · di cui aumento carta {euro(o.card_surcharge_cents)}</>}
                      </p>
                      <p>Pagato {formatDate(o.paid_at)}</p>
                    </div>
                    <div className="space-y-0.5">
                      <p className="font-semibold text-slate-300 light:text-slate-700">Negozio Shopify</p>
                      <p>Ordine <span className="font-mono">{o.shopify_order_name ?? "—"}</span> · evasione {o.shopify_fulfillment_status ?? "—"}</p>
                      <p>Creato {formatDate(o.forwarded_at)} · tentativi {o.attempt_count ?? 0}</p>
                      {o.tracking_company && <p>Corriere {o.tracking_company}</p>}
                      <p>Ultimo controllo {formatDate(o.last_sync_at)}</p>
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
