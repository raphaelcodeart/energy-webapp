/** Contract status labels and colours, shared by the pratica screens
    (Session 52). The older contract screens keep their own copies of the
    same table; these words must stay identical to theirs. */

export const CONTRACT_STATUS_LABELS: Record<string, string> = {
  DRAFT: "Bozza",
  SUBMITTED: "Inviata",
  DOCUMENTS_PENDING: "Documenti mancanti",
  UNDER_REVIEW: "In revisione",
  APPROVED: "Approvata",
  PAYMENT_PENDING: "In attesa di pagamento",
  PAID: "Pagata",
  ACTIVATION_PENDING: "In attivazione",
  ACTIVE: "Attiva",
  SUSPENDED: "Sospesa",
  CANCELLED: "Cessata",
  EXPIRED: "Scaduta",
  RENEWED: "Rinnovata",
  REJECTED: "Respinta",
};

export function contractStatusBadge(status: string): string {
  switch (status) {
    case "ACTIVE":
    case "RENEWED":
      return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
    case "DRAFT":
      return "bg-slate-500/10 light:bg-slate-200/50 text-slate-400 light:text-slate-500 border-slate-500/20 light:border-slate-300";
    case "REJECTED":
    case "CANCELLED":
    case "SUSPENDED":
      return "bg-rose-500/10 text-rose-400 border-rose-500/20";
    case "UNDER_REVIEW":
      return "bg-sky-500/10 text-sky-400 border-sky-500/20";
    default:
      return "bg-amber-500/10 text-amber-400 border-amber-500/20";
  }
}

export const PAYMENT_PLAN_LABELS: Record<string, string> = {
  FULL: "Soluzione unica",
  INSTALMENTS_3: "3 rate mensili",
  MONTHLY_12: "12 rate mensili",
};

export const ENERGY_POINT_LABELS: Record<string, string> = {
  ELECTRICITY: "Luce",
  GAS: "Gas",
};

/** How a supply point is named on screen: its code when one was recorded
    (contracts from before Session 53), otherwise its place in the pratica --
    "POD 1", "POD 2" -- since the code is no longer asked. */
export function pointCode(point: { pod_code?: string | null; pdr_code?: string | null; position?: number }): string {
  if (point.pod_code) return `POD ${point.pod_code}`;
  if (point.pdr_code) return `PDR ${point.pdr_code}`;
  return point.position ? `POD ${point.position}` : "Punto di fornitura";
}

export function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleDateString("it-IT") : "—";
}
