"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PhotoUpload } from "@/components/photo-upload";
import { friendlyApiError } from "@/lib/api-error";
import type { ProductCatalogRead, RankRead } from "@/lib/types";

const ENERGY_LABELS: Record<string, string> = {
  ELECTRICITY: "Luce",
  GAS: "Gas",
  DUAL_FUEL: "Dual Fuel",
};

const PRODUCT_TYPE_LABELS: Record<string, string> = {
  ENERGY_CONTRACT: "Contratto Energia",
  DIGITAL: "Digitale",
  PHYSICAL: "Fisico",
  SUBSCRIPTION: "Abbonamento",
};

const CUSTOMER_TYPE_LABELS: Record<string, string> = {
  PRIVATE: "Privati",
  SOLE_PROPRIETOR: "Partita IVA",
  PMI: "PMI",
  CONDOMINIUM: "Condominio",
  ENERGY_INTENSIVE: "Energivori",
};

function euro(cents: number): string {
  return (cents / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function euroToCents(value: string): number {
  const parsed = parseFloat(value.replace(",", "."));
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : 0;
}

function centsToEuroInput(cents: number): string {
  return (cents / 100).toFixed(2);
}

function commissionTokensToCents(tokens: Record<string, string>): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [code, value] of Object.entries(tokens)) {
    if (value.trim()) out[code] = euroToCents(value);
  }
  return out;
}

function commissionTokensToEuro(tokens: Record<string, number>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [code, cents] of Object.entries(tokens)) {
    out[code] = centsToEuroInput(cents);
  }
  return out;
}

async function fetchProducts(): Promise<ProductCatalogRead[]> {
  const res = await fetch("/api/proxy/products");
  if (!res.ok) throw new Error("Impossibile caricare i prodotti.");
  return res.json();
}

async function fetchRanks(): Promise<RankRead[]> {
  const res = await fetch("/api/proxy/commissions/ranks");
  if (!res.ok) throw new Error("Impossibile caricare le qualifiche.");
  return res.json();
}

interface ProductFormState {
  name: string;
  description: string;
  imageUrl: string;
  basePriceEuro: string;
  initialFeeEuro: string;
  recurringFeeEuro: string;
  billingPeriod: string;
  vatPercentage: string;
  contractDurationMonths: string;
  // rank code -> gettone in EUR (string, same input pattern as the other money
  // fields) -- the personal token this product pays at that rank, see
  // catalog/models.py::ProductVersion.commission_tokens.
  commissionTokens: Record<string, string>;
}

const EMPTY_FORM: ProductFormState = {
  name: "",
  description: "",
  imageUrl: "",
  basePriceEuro: "",
  initialFeeEuro: "0",
  recurringFeeEuro: "0",
  billingPeriod: "MONTHLY",
  vatPercentage: "10",
  contractDurationMonths: "12",
  commissionTokens: {},
};

function ProductFormFields({
  form,
  onChange,
  ranks,
}: {
  form: ProductFormState;
  onChange: (patch: Partial<ProductFormState>) => void;
  ranks: RankRead[];
}) {
  return (
    <>
      <div className="space-y-1">
        <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Nome</label>
        <input required value={form.name} onChange={(e) => onChange({ name: e.target.value })}
          className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
      </div>

      <div className="space-y-1">
        <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Descrizione</label>
        <textarea rows={2} value={form.description} onChange={(e) => onChange({ description: e.target.value })}
          placeholder="Descrizione visibile ai clienti nel marketplace..."
          className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500 resize-none" />
      </div>

      <div className="space-y-1">
        <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Foto prodotto (URL immagine)</label>
        <div className="flex items-center gap-3">
          {form.imageUrl && (
            // eslint-disable-next-line @next/next/no-img-element -- externally-hosted, variable-source image (URL or uploaded)
            <img src={form.imageUrl} alt="" className="w-12 h-12 rounded-lg object-cover border border-white/10 light:border-slate-200 shrink-0" />
          )}
          <input value={form.imageUrl} onChange={(e) => onChange({ imageUrl: e.target.value })}
            placeholder="https://..."
            className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Prezzo base (EUR)</label>
          <input required inputMode="decimal" value={form.basePriceEuro} onChange={(e) => onChange({ basePriceEuro: e.target.value })}
            placeholder="18.00"
            className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Aliquota IVA (%)</label>
          <input inputMode="decimal" value={form.vatPercentage} onChange={(e) => onChange({ vatPercentage: e.target.value })}
            placeholder="10"
            className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Fee iniziale (EUR)</label>
          <input inputMode="decimal" value={form.initialFeeEuro} onChange={(e) => onChange({ initialFeeEuro: e.target.value })}
            className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Fee ricorrente (EUR)</label>
          <input inputMode="decimal" value={form.recurringFeeEuro} onChange={(e) => onChange({ recurringFeeEuro: e.target.value })}
            className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Periodicità fatturazione</label>
          <select value={form.billingPeriod} onChange={(e) => onChange({ billingPeriod: e.target.value })}
            className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
            <option value="MONTHLY">Mensile</option>
            <option value="QUARTERLY">Trimestrale</option>
            <option value="ANNUAL">Annuale</option>
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Durata contratto (mesi)</label>
          <input inputMode="numeric" value={form.contractDurationMonths}
            onChange={(e) => onChange({ contractDurationMonths: e.target.value })}
            placeholder="Vuoto = nessun rinnovo"
            className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
          <p className="text-[10px] text-slate-500">Lascia vuoto per prodotti senza rinnovo (digitali, fisici, acquisti una tantum).</p>
        </div>
      </div>

      <div className="space-y-1 pt-2 border-t border-white/5 light:border-slate-200">
        <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">
          Gettone provvigionale per grado (EUR)
        </label>
        <p className="text-[10px] text-slate-500 mb-2">
          Quanto guadagna il promoter per un contratto di QUESTO prodotto, in base al proprio grado.
          Determina anche la differenza imprenditoriale riconosciuta agli sponsor superiori.
        </p>
        <div className="grid grid-cols-3 gap-2">
          {[...ranks].sort((a, b) => a.level - b.level).map((r) => (
            <div key={r.id} className="space-y-0.5">
              <label className="text-[10px] text-slate-400 light:text-slate-500 font-mono block">{r.code}</label>
              <input
                inputMode="decimal"
                value={form.commissionTokens[r.code] ?? ""}
                onChange={(e) =>
                  onChange({ commissionTokens: { ...form.commissionTokens, [r.code]: e.target.value } })
                }
                placeholder="0.00"
                className="w-full rounded-lg glass-input px-2 py-1.5 text-xs focus:border-orange-500"
              />
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

export function AdminProductsPanel() {
  const queryClient = useQueryClient();
  const { data: products, error: loadError } = useQuery({
    queryKey: ["admin", "products"],
    queryFn: fetchProducts,
  });
  const { data: ranks = [] } = useQuery({
    queryKey: ["admin", "ranks"],
    queryFn: fetchRanks,
  });

  const [showCreate, setShowCreate] = useState(false);
  const [isDuplicating, setIsDuplicating] = useState(false);
  const [code, setCode] = useState("");
  const [productType, setProductType] = useState("ENERGY_CONTRACT");
  const [energyType, setEnergyType] = useState("ELECTRICITY");
  const [customerType, setCustomerType] = useState("PRIVATE");
  const [createForm, setCreateForm] = useState<ProductFormState>(EMPTY_FORM);
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [editingProduct, setEditingProduct] = useState<ProductCatalogRead | null>(null);
  const [editForm, setEditForm] = useState<ProductFormState>(EMPTY_FORM);
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const [deletingProduct, setDeletingProduct] = useState<ProductCatalogRead | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  function openDuplicate(product: ProductCatalogRead) {
    const v = product.current_version;
    setCode(`${product.code}-COPY`);
    setProductType(product.product_type);
    setEnergyType(product.energy_type ?? "ELECTRICITY");
    setCustomerType(product.customer_type);
    setCreateForm({
      name: v ? `${v.name} (copia)` : "",
      description: v?.description ?? "",
      imageUrl: v?.image_url ?? "",
      basePriceEuro: v ? centsToEuroInput(v.base_price_cents) : "",
      initialFeeEuro: v ? centsToEuroInput(v.initial_fee_cents) : "0",
      recurringFeeEuro: v ? centsToEuroInput(v.recurring_fee_cents) : "0",
      billingPeriod: v?.billing_period ?? "MONTHLY",
      vatPercentage: v?.vat_percentage != null ? String(v.vat_percentage) : "",
      contractDurationMonths: v?.contract_duration_months != null ? String(v.contract_duration_months) : "",
      commissionTokens: v ? commissionTokensToEuro(v.commission_tokens) : {},
    });
    setCreateError(null);
    setIsDuplicating(true);
    setShowCreate(true);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateLoading(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/proxy/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code,
          product_type: productType,
          energy_type: productType === "ENERGY_CONTRACT" ? energyType : null,
          customer_type: customerType,
          name: createForm.name,
          description: createForm.description,
          image_url: createForm.imageUrl.trim() || null,
          base_price_cents: euroToCents(createForm.basePriceEuro),
          initial_fee_cents: euroToCents(createForm.initialFeeEuro),
          recurring_fee_cents: euroToCents(createForm.recurringFeeEuro),
          billing_period: createForm.billingPeriod,
          vat_percentage: createForm.vatPercentage.trim() ? parseFloat(createForm.vatPercentage) : null,
          contract_duration_months: createForm.contractDurationMonths.trim()
            ? parseInt(createForm.contractDurationMonths, 10)
            : null,
          commission_tokens: commissionTokensToCents(createForm.commissionTokens),
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setShowCreate(false);
      setIsDuplicating(false);
      setCode("");
      setCreateForm(EMPTY_FORM);
      await queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
    } catch (err: any) {
      setCreateError(err.message || "Impossibile creare il prodotto.");
    } finally {
      setCreateLoading(false);
    }
  }

  function openEdit(product: ProductCatalogRead) {
    const v = product.current_version;
    setEditForm({
      name: v?.name ?? "",
      description: v?.description ?? "",
      imageUrl: v?.image_url ?? "",
      basePriceEuro: v ? centsToEuroInput(v.base_price_cents) : "",
      initialFeeEuro: v ? centsToEuroInput(v.initial_fee_cents) : "0",
      recurringFeeEuro: v ? centsToEuroInput(v.recurring_fee_cents) : "0",
      billingPeriod: v?.billing_period ?? "MONTHLY",
      vatPercentage: v?.vat_percentage != null ? String(v.vat_percentage) : "",
      contractDurationMonths: v?.contract_duration_months != null ? String(v.contract_duration_months) : "",
      commissionTokens: v ? commissionTokensToEuro(v.commission_tokens) : {},
    });
    setEditError(null);
    setEditingProduct(product);
  }

  async function handleEditSave(e: React.FormEvent) {
    e.preventDefault();
    if (!editingProduct?.current_version) return;
    setEditLoading(true);
    setEditError(null);
    try {
      const res = await fetch(`/api/proxy/products/versions/${editingProduct.current_version.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: editForm.name,
          description: editForm.description,
          image_url: editForm.imageUrl.trim() || null,
          base_price_cents: euroToCents(editForm.basePriceEuro),
          initial_fee_cents: euroToCents(editForm.initialFeeEuro),
          recurring_fee_cents: euroToCents(editForm.recurringFeeEuro),
          vat_percentage: editForm.vatPercentage.trim() ? parseFloat(editForm.vatPercentage) : null,
          contract_duration_months: editForm.contractDurationMonths.trim()
            ? parseInt(editForm.contractDurationMonths, 10)
            : null,
          commission_tokens: commissionTokensToCents(editForm.commissionTokens),
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setEditingProduct(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
    } catch (err: any) {
      setEditError(err.message || "Impossibile salvare le modifiche.");
    } finally {
      setEditLoading(false);
    }
  }

  async function handleDeleteProduct() {
    if (!deletingProduct) return;
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      const res = await fetch(`/api/proxy/products/${deletingProduct.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await friendlyApiError(res, "Impossibile eliminare il prodotto."));
      setDeletingProduct(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
    } catch (err: any) {
      setDeleteError(err.message || "Impossibile eliminare il prodotto.");
    } finally {
      setDeleteLoading(false);
    }
  }

  const deleteConfirmModal = deletingProduct && (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up">
        <h3 className="text-lg font-bold text-white light:text-slate-900 mb-2">Elimina prodotto</h3>
        <p className="text-xs text-slate-400 light:text-slate-500 mb-4">
          Stai per eliminare definitivamente il prodotto{" "}
          <span className="font-semibold text-slate-300 light:text-slate-700">
            &quot;{deletingProduct.current_version?.name ?? deletingProduct.code}&quot;
          </span>{" "}
          e tutte le sue versioni. L&apos;operazione non può essere annullata. Se il prodotto ha contratti
          associati, l&apos;eliminazione verrà rifiutata: in quel caso puoi solo disattivarlo.
        </p>
        {deleteError && <p className="text-xs text-rose-400 mb-3">{deleteError}</p>}
        <div className="flex justify-end gap-3">
          <button
            onClick={() => { setDeletingProduct(null); setDeleteError(null); }}
            className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer"
          >
            Annulla
          </button>
          <button
            onClick={handleDeleteProduct}
            disabled={deleteLoading}
            className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
          >
            {deleteLoading ? "Eliminazione..." : "Elimina definitivamente"}
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-400 light:text-slate-500">
          Cataloghi luce, gas, dual fuel ed Energia Circolare venduti in marketplace.
        </p>
        <button
          onClick={() => {
            setCode("");
            setProductType("ENERGY_CONTRACT");
            setEnergyType("ELECTRICITY");
            setCustomerType("PRIVATE");
            setCreateForm(EMPTY_FORM);
            setCreateError(null);
            setIsDuplicating(false);
            setShowCreate(true);
          }}
          className="px-4 py-2 rounded-xl text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white shadow-lg shadow-orange-500/20 transition cursor-pointer shrink-0"
        >
          + Nuovo Prodotto
        </button>
      </div>

      {loadError && <p className="text-sm text-rose-400">Impossibile caricare i prodotti.</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {products === undefined ? (
          <p className="text-sm text-slate-500 col-span-full text-center py-8">Caricamento...</p>
        ) : products.length === 0 ? (
          <p className="text-sm text-slate-500 col-span-full text-center py-8">Nessun prodotto nel catalogo.</p>
        ) : (
          products.map((p) => (
            <div key={p.id} className="glass-card rounded-2xl overflow-hidden border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70">
              <div className="h-32 bg-slate-900 light:bg-slate-100 flex items-center justify-center overflow-hidden relative">
                {p.current_version?.image_url ? (
                  // eslint-disable-next-line @next/next/no-img-element -- external, admin-supplied URLs; not part of the Next asset pipeline
                  <img src={p.current_version.image_url} alt={p.current_version.name} className="w-full h-full object-cover" />
                ) : (
                  <svg className="w-10 h-10 text-slate-700 light:text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14M4 8h16M4 4h16v16H4V4z" />
                  </svg>
                )}
                <div className="absolute top-2 right-2 flex items-center gap-1.5">
                  <button
                    onClick={() => openDuplicate(p)}
                    className="p-1.5 rounded-lg bg-slate-950/70 hover:bg-slate-950/90 text-white transition cursor-pointer"
                    title="Duplica prodotto"
                    disabled={!p.current_version}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                  </button>
                  <button
                    onClick={() => openEdit(p)}
                    className="p-1.5 rounded-lg bg-slate-950/70 hover:bg-slate-950/90 text-white transition cursor-pointer"
                    title="Modifica prodotto"
                    disabled={!p.current_version}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                  </button>
                  <button
                    onClick={() => { setDeletingProduct(p); setDeleteError(null); }}
                    className="p-1.5 rounded-lg bg-slate-950/70 hover:bg-rose-600 text-white transition cursor-pointer"
                    title="Elimina prodotto"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
              <div className="p-5">
                <div className="flex items-center justify-between mb-3">
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-amber-500/10 text-amber-400 border-amber-500/20">
                    {p.product_type === "ENERGY_CONTRACT"
                      ? (p.energy_type ? ENERGY_LABELS[p.energy_type] ?? p.energy_type : "Energia")
                      : PRODUCT_TYPE_LABELS[p.product_type] ?? p.product_type}
                  </span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                    p.status === "ACTIVE"
                      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                      : "bg-slate-500/10 light:bg-slate-200/50 text-slate-400 light:text-slate-500 border-slate-500/20 light:border-slate-300"
                  }`}>
                    {p.status}
                  </span>
                </div>
                <h4 className="text-sm font-semibold text-white light:text-slate-900 mb-0.5">
                  {p.current_version?.name ?? p.code}
                </h4>
                <p className="font-mono text-[10px] text-slate-500 mb-2">{p.code}</p>
                {p.current_version?.description && (
                  <p className="text-xs text-slate-400 light:text-slate-500 mb-3 line-clamp-2">
                    {p.current_version.description}
                  </p>
                )}
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-400 light:text-slate-500">
                    Target: {CUSTOMER_TYPE_LABELS[p.customer_type] ?? p.customer_type}
                  </span>
                  {p.current_version && (
                    <span className="text-right">
                      <span className="block text-sm font-bold text-orange-400">
                        {euro(p.current_version.base_price_cents)}
                      </span>
                      {p.current_version.vat_percentage != null && (
                        <span className="block text-[10px] text-slate-500">IVA {p.current_version.vat_percentage}%</span>
                      )}
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white light:text-slate-900">
                {isDuplicating ? "Duplica Prodotto" : "Nuovo Prodotto"}
              </h3>
              <button onClick={() => { setShowCreate(false); setIsDuplicating(false); }}
                className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {isDuplicating && (
              <p className="text-xs text-slate-400 light:text-slate-500 -mt-2 mb-4">
                Tutti i campi sono precompilati dal prodotto originale, incluso il gettone per grado. Cambia almeno il codice prima di salvare.
              </p>
            )}

            <form onSubmit={handleCreate} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Codice</label>
                <input required value={code} onChange={(e) => setCode(e.target.value)} placeholder="Es: LUCE-PMI-01"
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm font-mono focus:border-orange-500" />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Tipo Prodotto</label>
                  <select value={productType} onChange={(e) => setProductType(e.target.value)}
                    className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                    {Object.entries(PRODUCT_TYPE_LABELS).map(([code2, label]) => (
                      <option key={code2} value={code2}>{label}</option>
                    ))}
                  </select>
                </div>
                {productType === "ENERGY_CONTRACT" && (
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Tipo Energia</label>
                    <select value={energyType} onChange={(e) => setEnergyType(e.target.value)}
                      className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                      {Object.entries(ENERGY_LABELS).map(([code2, label]) => (
                        <option key={code2} value={code2}>{label}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Cliente Target</label>
                <select value={customerType} onChange={(e) => setCustomerType(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                  {Object.entries(CUSTOMER_TYPE_LABELS).map(([code2, label]) => (
                    <option key={code2} value={code2}>{label}</option>
                  ))}
                </select>
              </div>

              <ProductFormFields form={createForm} onChange={(patch) => setCreateForm((f) => ({ ...f, ...patch }))} ranks={ranks} />

              {createError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{createError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => { setShowCreate(false); setIsDuplicating(false); }}
                  className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer">
                  Annulla
                </button>
                <button type="submit" disabled={createLoading}
                  className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                  {createLoading ? "Creazione..." : isDuplicating ? "Crea Copia" : "Crea Prodotto"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editingProduct && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white light:text-slate-900">Modifica Prodotto</h3>
              <button onClick={() => setEditingProduct(null)}
                className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <p className="font-mono text-[10px] text-slate-500 mb-4">{editingProduct.code}</p>

            {editingProduct.current_version && (
              <div className="mb-5 pb-5 border-b border-white/5 light:border-slate-200">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block mb-2">Carica foto</label>
                <PhotoUpload
                  currentUrl={editForm.imageUrl || null}
                  uploadPath={`products/versions/${editingProduct.current_version.id}/photo`}
                  onUploaded={(url) => {
                    setEditForm((f) => ({ ...f, imageUrl: url }));
                    queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
                  }}
                  alt={editingProduct.current_version.name}
                  size={72}
                />
              </div>
            )}

            <form onSubmit={handleEditSave} className="space-y-4">
              <ProductFormFields form={editForm} onChange={(patch) => setEditForm((f) => ({ ...f, ...patch }))} ranks={ranks} />

              {editError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{editError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setEditingProduct(null)}
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

      {deleteConfirmModal}
    </div>
  );
}
