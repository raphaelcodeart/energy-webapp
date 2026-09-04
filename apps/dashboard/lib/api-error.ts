/**
 * Turns a backend error response into a message a human can read.
 *
 * The API returns FastAPI's default shape, `{"detail": "..."}` (or, for
 * validation errors, `{"detail": [{"msg": "...", ...}, ...]}`) -- correct for
 * a machine, meaningless (and previously shown verbatim, braces and all) to
 * a promoter or customer. This maps the backend's own exception messages
 * (see apps/api/app/domains/*\/service.py and router.py) to short Italian
 * sentences, and falls back to a generic one for anything unrecognized or
 * clearly not human-facing (HTML error pages, stack traces).
 */

const KNOWN_MESSAGES: Record<string, string> = {
  "Invalid email or password": "Email o password non corretti.",
  "Account temporarily locked, try again later": "Troppi tentativi: account bloccato temporaneamente. Riprova tra qualche minuto.",
  "Invalid refresh token": "Sessione scaduta. Effettua di nuovo l'accesso.",
  "Refresh token expired": "Sessione scaduta. Effettua di nuovo l'accesso.",
  "Missing refresh token": "Sessione scaduta. Effettua di nuovo l'accesso.",
  "Invalid or expired token": "Sessione scaduta. Effettua di nuovo l'accesso.",
  "Missing bearer token": "Sessione scaduta. Effettua di nuovo l'accesso.",
  "Wrong token type": "Sessione scaduta. Effettua di nuovo l'accesso.",
  "Invalid or expired referral code -- registration is invite-only":
    "Questo link di invito non è valido o è scaduto. Chiedi a chi te lo ha mandato un link nuovo.",
  "An account with this email already exists": "Esiste già un account registrato con questa email.",
  "Customer role is not configured for this organization": "Errore di configurazione dell'account. Contatta l'assistenza.",
  "first_name and last_name are required for this customer kind": "Nome e cognome sono obbligatori.",
  "company_name is required for this customer kind": "La ragione sociale è obbligatoria.",
  "Invalid or already-used reset link": "Il link per reimpostare la password non è valido o è già stato usato.",
  "This reset link has expired": "Il link per reimpostare la password è scaduto: richiedine uno nuovo.",
  "password must be at least 8 characters": "La password deve avere almeno 8 caratteri.",
  "Only customers can apply to become a promoter": "Solo i clienti registrati possono candidarsi come promoter.",
  "No agent profile for this user": "Il tuo account non ha ancora un profilo promoter attivo.",
  "Not authorized for this branch": "Non hai accesso a questa parte della rete commerciale.",
  "Not authorized for this contract": "Non hai accesso a questo contratto.",
  "Not authorized for this contract's documents": "Non hai accesso ai documenti di questo contratto.",
  "Agent not found": "Promoter non trovato.",
  "Contract not found": "Contratto non trovato.",
  "Customer not found": "Cliente non trovato.",
  "Document not found": "Documento non trovato.",
  "Post not found": "Post non trovato.",
  "Notification not found": "Notifica non trovata.",
  "Product not found": "Prodotto non trovato.",
  "Product version not found": "Versione del prodotto non trovata.",
  "Supply point not found": "Punto di fornitura non trovato.",
  "Ticket not found": "Ticket non trovato.",
  "Commission movement not found": "Movimento di commissione non trovato.",
  "Invalid or expired promoter code": "Codice promoter non valido o scaduto.",
  "An agent cannot be its own parent": "Un promoter non può essere sponsor di se stesso.",
  "Agent has no active network node": "Questo promoter non ha una posizione attiva nella rete.",
  "Move would create a cycle: new parent is a descendant of the agent":
    "Spostamento non valido: creerebbe un ciclo nella rete commerciale.",
  "Unknown agent": "Promoter sconosciuto.",
  "Customer is already attributed to this promoter": "Questo cliente è già attribuito a questo promoter.",
  "This customer has no existing promoter attribution to correct": "Questo cliente non ha un'attribuzione da correggere.",
  "Contract has no network snapshot; cannot calculate commissions":
    "Impossibile calcolare le commissioni: manca lo storico rete per questo contratto.",
  "Contract has no network snapshot to simulate against":
    "Impossibile simulare: manca lo storico rete per questo contratto.",
  "status must be APPROVED or REJECTED": "Lo stato deve essere Approvato o Rifiutato.",
  "Only a resolved ticket can be deleted.": "Solo un ticket risolto può essere eliminato.",
  "iban is required": "L'IBAN è obbligatorio.",
  "Insufficient balance": "Saldo insufficiente per completare l'operazione.",
  "Insufficient balance to reverse this transaction": "Saldo insufficiente per stornare questa transazione.",
  "Cannot send to your own wallet": "Non puoi inviare denaro al tuo stesso wallet.",
  "Wallet not found": "Indirizzo wallet non trovato.",
  "Transaction not found": "Transazione non trovata.",
  "Cannot reverse a REVERSAL": "Non è possibile stornare uno storno.",
};

const PERMISSION_LABELS: Record<string, string> = {
  "customers.read": "consultare i clienti",
  "customers.create": "creare clienti",
  "customers.update": "modificare i clienti",
  "contracts.read": "consultare i contratti",
  "contracts.create": "creare contratti",
  "contracts.submit": "inviare i contratti",
  "contracts.review": "revisionare i contratti",
  "contracts.approve": "approvare i contratti",
  "contracts.activate": "attivare i contratti",
  "network.read_branch": "consultare la rete commerciale",
  "network.manage": "gestire la rete commerciale",
  "network.recruit": "reclutare nuovi promoter",
  "network.approve": "approvare i promoter",
  "commissions.read_own": "consultare le proprie provvigioni",
  "commissions.read_branch": "consultare le provvigioni della rete",
  "commissions.simulate": "simulare le provvigioni",
  "commissions.approve": "approvare le provvigioni",
  "commissions.evaluate_ranks": "valutare i gradi",
  "commission_adjustments.create": "creare rettifiche di provvigione",
  "payments.manage": "gestire i pagamenti",
  "documents.download": "scaricare i documenti",
  "reports.export": "esportare i report",
  "reports.read": "consultare i report",
  "audit.read": "consultare il registro attività",
  "settings.manage": "gestire le impostazioni",
  "products.read": "consultare i prodotti",
  "products.manage": "gestire i prodotti",
  "tickets.create": "creare ticket",
  "tickets.respond": "rispondere ai ticket",
  "tickets.delete": "eliminare i ticket",
  "documents.upload": "caricare documenti",
  "documents.review": "revisionare i documenti",
  "documentation.manage": "gestire la documentazione",
  "wallet.manage": "gestire i wallet",
};

const GENERIC_FALLBACK = "Si è verificato un errore imprevisto. Riprova più tardi.";

function extractDetail(raw: string): string | undefined {
  if (!raw) return undefined;
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed?.detail === "string") return parsed.detail;
    if (typeof parsed?.error === "string") return parsed.error;
    if (Array.isArray(parsed?.detail) && typeof parsed.detail[0]?.msg === "string") {
      return parsed.detail[0].msg as string;
    }
  } catch {
    // Not JSON -- plain text or an HTML error page (e.g. a 502 from in front
    // of the API). translateErrorDetail()'s own shape check handles that.
  }
  return undefined;
}

/** Maps one already-extracted backend `detail` string to an Italian sentence. */
export function translateErrorDetail(detail: string): string {
  if (KNOWN_MESSAGES[detail]) return KNOWN_MESSAGES[detail];

  const permissionMatch = /^Missing permission: (.+)$/.exec(detail);
  if (permissionMatch) {
    const label = PERMISSION_LABELS[permissionMatch[1] ?? ""] ?? "eseguire questa operazione";
    return `Non hai i permessi per ${label}. Serve un account con un ruolo superiore.`;
  }
  if (/^Agent is \w+, not PENDING_APPROVAL$/.test(detail)) {
    return "Questo promoter non è (più) in attesa di approvazione.";
  }
  if (/^Existing application\/profile is \w+$/.test(detail)) {
    return "Hai già una candidatura o un profilo promoter attivo.";
  }
  if (/^This user already has a promoter profile \(\w+\)$/.test(detail)) {
    return "Questo cliente ha già un profilo promoter (attivo, in attesa o cessato).";
  }
  if (/^An account with email '.*' already exists$/.test(detail)) {
    return "Esiste già un account con questa email.";
  }
  if (/^Promoter code '.*' is already in use$/.test(detail)) {
    return "Questo codice promoter è già in uso: scegline un altro.";
  }
  if (/^Role .* is not configured for this organization$/.test(detail)) {
    return "Errore di configurazione dei ruoli. Contatta l'assistenza.";
  }
  const transitionMatch = /^Cannot transition contract from (\w+) to (\w+)$/.exec(detail);
  if (transitionMatch) {
    return `Non è possibile far passare il contratto dallo stato ${transitionMatch[1]} a ${transitionMatch[2]}.`;
  }
  if (/^Movement is \w+, not payable$/.test(detail)) {
    return "Questo movimento non è pagabile nel suo stato attuale.";
  }
  if (/must be one of/.test(detail) || /must be in .* format/.test(detail)) {
    return "Uno dei valori inseriti non è valido.";
  }

  // Unrecognized, but still a short, human-written sentence (not a stack
  // trace or an HTML page) -- show it rather than hide real information
  // behind a generic message.
  if (detail.length > 0 && detail.length < 200 && !/[<>{}]/.test(detail)) return detail;
  return GENERIC_FALLBACK;
}

/** Reads a failed fetch Response and returns a ready-to-display Italian message. */
export async function friendlyApiError(res: Response, fallback: string = GENERIC_FALLBACK): Promise<string> {
  let raw: string;
  try {
    raw = await res.text();
  } catch {
    return fallback;
  }
  const detail = extractDetail(raw);
  return detail ? translateErrorDetail(detail) : fallback;
}
