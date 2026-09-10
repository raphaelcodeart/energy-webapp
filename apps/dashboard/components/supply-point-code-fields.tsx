"use client";

const MAX_SUPPLY_POINTS = 10;

/** One POD or PDR code to activate, plus its own meter number. Shared by
    every screen that collects supply-point codes (contract-activation-
    wizard.tsx for the customer/promoter self-service flow,
    admin-create-contract-panel.tsx for the admin "Nuovo Contratto" form)
    so the "Quanti POD/PDR hai?" question and its behavior never drift
    apart between them. */
export type CodeEntry = { code: string; meterNumber: string };

export function emptyEntries(count: number): CodeEntry[] {
  return Array.from({ length: count }, () => ({ code: "", meterNumber: "" }));
}

/** Resizes an entry list to match a new quantity, preserving whatever was
    already typed in the rows that still exist. */
export function resizeEntries(prev: CodeEntry[], count: number): CodeEntry[] {
  if (prev.length === count) return prev;
  const next = [...prev];
  while (next.length < count) next.push({ code: "", meterNumber: "" });
  next.length = count;
  return next;
}

/** The stepper itself: "Quanti POD hai?" / "Quanti PDR hai?", worded
    explicitly as a question (per the user's explicit request) so it's
    unmistakable that this asks for a QUANTITY, distinct from the code
    rows it renders below (see SupplyPointCodeFields). */
function QuantityStepper({ label, value, onChange }: { label: string; value: number; onChange: (n: number) => void }) {
  return (
    <div className="space-y-1">
      <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">{label}</label>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onChange(Math.max(1, value - 1))}
          className="w-8 h-8 rounded-lg bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-300 text-white light:text-slate-900 font-bold hover:bg-white/10 transition cursor-pointer disabled:opacity-40"
          disabled={value <= 1}
        >
          −
        </button>
        <span className="w-8 text-center text-sm font-bold text-white light:text-slate-900 tabular-nums">{value}</span>
        <button
          type="button"
          onClick={() => onChange(Math.min(MAX_SUPPLY_POINTS, value + 1))}
          className="w-8 h-8 rounded-lg bg-white/5 light:bg-slate-900/5 border border-white/10 light:border-slate-300 text-white light:text-slate-900 font-bold hover:bg-white/10 transition cursor-pointer disabled:opacity-40"
          disabled={value >= MAX_SUPPLY_POINTS}
        >
          +
        </button>
      </div>
    </div>
  );
}

/** "Quanti POD/PDR hai?" -- the quantity question -- plus, right below it,
    exactly that many code (+ optional meter number) rows. Used identically
    by customer self-service, promoter CRM (same component, see
    contract-activation-wizard.tsx's customerId prop), and the admin "Nuovo
    Contratto" form -- one place to keep the wording and behavior
    consistent across all three. */
export function SupplyPointCodeFields({
  kind,
  entries,
  onChange,
}: {
  kind: "POD" | "PDR";
  entries: CodeEntry[];
  onChange: (entries: CodeEntry[]) => void;
}) {
  const label = kind === "POD" ? "Quanti POD hai?" : "Quanti PDR hai?";
  const placeholder = kind === "POD" ? "IT001E..." : "00000000000000";

  function updateEntry(i: number, field: keyof CodeEntry, value: string) {
    onChange(entries.map((entry, idx) => (idx === i ? { ...entry, [field]: value } : entry)));
  }

  return (
    <div className="space-y-3 pt-3 border-t border-white/5 light:border-slate-200">
      <QuantityStepper label={label} value={entries.length} onChange={(n) => onChange(resizeEntries(entries, n))} />
      <div className="space-y-2">
        {entries.map((entry, i) => (
          <div key={i} className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">
                Codice {kind} {entries.length > 1 ? `#${i + 1}` : ""}
              </label>
              <input
                required
                value={entry.code}
                onChange={(e) => updateEntry(i, "code", e.target.value)}
                placeholder={placeholder}
                className="w-full rounded-xl glass-input px-3 py-2.5 text-sm uppercase focus:border-orange-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-semibold text-slate-300 light:text-slate-600 uppercase block">Contatore (opz.)</label>
              <input
                value={entry.meterNumber}
                onChange={(e) => updateEntry(i, "meterNumber", e.target.value)}
                className="w-full rounded-xl glass-input px-3 py-2.5 text-sm focus:border-orange-500"
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
