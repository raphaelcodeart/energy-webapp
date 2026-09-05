# Piano: Cashback da riscatto fatture fornitori-partner

**Stato: Fasi 0, 1, 2 implementate e verificate end-to-end (via HTTP reale,
multipart incluso, non solo a livello di servizio) il 2026-09-05. Fase 3
(wizard) implementata SENZA OCR reale (inserimento manuale dell'importo,
verifica sempre umana). Fase 4 (sconto crediti nel checkout) NON ancora
implementata — vedi sotto.**

Se stai riprendendo questo lavoro dopo un crash/reset di sessione, questo file
ti dice esattamente a che punto siamo — leggilo prima di chiedere di nuovo
all'utente cosa vuole, la risposta è già qui sotto.

Relazione di design originale (diagramma del flusso, ragionamento):
artifact "Cashback Circolare" pubblicato il 2026-09-05
(`claude.ai/code/artifact/c79ffd6e-b10b-421b-b3dc-b71dfdba398f`). Il design lì
descritto è stato seguito fedelmente, salvo dove annotato sotto.

## Lavoro collegato completato nella stessa sessione (non è il progetto cashback in sé)

- [x] **Bonifico wallet disabilitato di default per tutti** (clienti e
      promoter), abilitabile individualmente solo per promoter specifici.
      Migrazione `0019_wallet_transfer_gate.py` (colonna `wallets.can_transfer`,
      default `false`). Abilitati: Alessandro Pantano, Marco Web. Toggle admin
      in "Anagrafiche Promoter".

## L'idea in una frase

Il cliente (o promoter) riscatta come credito interno il valore di una
bolletta già pagata a un fornitore-partner esterno (Lial fa da broker),
pagando a Lial solo il 3% di quell'importo via bonifico; alla conferma admin
riceve credito = 100% + 3% bonus, spendibile come sconto sui prodotti esterni
dello shop (mai sui prodotti interni Lial, mai in contanti).

**Principio cardine, rispettato dall'implementazione**: il credito nasce SOLO
da un ingresso reale di denaro (il bonifico del 3%, confermato da un admin).
Non nasce mai dallo spendere un credito già esistente.

## Cosa è stato costruito (Fasi 0-2, backend + admin UI + wizard cliente)

**Backend** (`apps/api/app/domains/`):
- `partners/` — dominio nuovo: anagrafica fornitori (nome, logo, attivo/non
  attivo). `GET /partners` aperto a chiunque sia autenticato (serve al
  wizard cliente); `POST`/`PATCH` gated da un nuovo permesso `partners.manage`
  (stessi ruoli di `products.manage`: SUPER_ADMIN/ORGANIZATION_ADMIN/ADMIN/
  SALES_MANAGER).
- `invoice_redemptions/` — dominio nuovo, il cuore del flusso. Stati:
  `SUBMITTED → PAYMENT_PENDING → CREDITED`, con `REJECTED` raggiungibile da
  `SUBMITTED` o `PAYMENT_PENDING`. Un solo campo `confirmed_amount_cents`
  (non un campo separato "verificato"): l'azione admin "verify" fa entrambe
  le cose insieme (conferma l'importo E genera il codice di pagamento),
  niente stato di riposo intermedio -- vedi il commento in
  `service.py::verify()`. Il documento NON passa dal dominio `documents`
  esistente (il suo `contract_id` è NOT NULL per disegno, un riscatto non ha
  un contratto Lial dietro) -- riusa direttamente
  `core/storage.py::upload_document`/`generate_presigned_document_url` con
  una propria `storage_key` sulla riga.
  Endpoint cliente: `POST /invoice-redemptions` (multipart), `GET .../mine`,
  `GET .../mine/{id}/photo-url`, `GET .../payment-info` (IBAN aziendale, vedi
  sotto). Endpoint admin (gated `wallet.manage`, stessa sensibilità del resto
  della superficie wallet): `GET .../admin` (coda, filtrabile per stato),
  `GET .../admin/{id}/photo-url`, `POST .../admin/{id}/verify`,
  `POST .../admin/{id}/reject`, `POST .../admin/{id}/confirm-payment`.
- `wallets/` (esteso, non nuovo) — `WalletTransaction` ha ora `source`
  (`MANUAL_ADMIN` / `INVOICE_REDEMPTION_BASE` / `INVOICE_REDEMPTION_BONUS`,
  nullable) e `reference_invoice_redemption_id`. `credit_wallet()` accetta
  questi due parametri opzionali. `confirm_payment()` chiama `credit_wallet()`
  **due volte** (mai una riga unica da importo+bonus sommati), entrambe le
  chiamate con idempotency key derivata deterministicamente dall'id del
  riscatto (`invoice-redemption:{id}:base|bonus`) -- non serve una key dal
  client, il guard sullo stato (`PAYMENT_PENDING` richiesto) rende l'azione
  già di per sé eseguibile una sola volta; un retry dopo un fallimento
  parziale ri-colpisce le stesse due key e non duplica nulla.
- `catalog/` (esteso) — `Product.category` (`INTERNAL` default /
  `DROPSHIPPING` / `PARTNER`) e `ProductVersion.credit_discount_percentage`
  (0-100, default 0). `catalog/service.py::_clamp_credit_discount()` è
  l'UNICO punto che forza lo sconto a 0 quando la categoria è `INTERNAL` --
  vale sia in creazione che in modifica prodotto/versione, e cambiare la
  categoria di un prodotto esistente A `INTERNAL` azzera lo sconto su TUTTE
  le sue versioni (query bulk in `update_product()`).
- `core/config.py` — nuove settings `COMPANY_BANK_IBAN` (vuoto di default) e
  `COMPANY_BANK_HOLDER`. Finché `COMPANY_BANK_IBAN` è vuoto, il wizard
  cliente mostra "contatta l'amministrazione" invece di un IBAN -- stesso
  pattern "sicuro a vuoto" di `SMTP_HOST`. **Da compilare quando si ha un
  conto aziendale reale su cui far arrivare i bonifici del 3%.**
- `notifications/` (esteso) — due nuovi tipi: `INVOICE_REDEMPTION_VERIFIED`
  (avvisa il cliente di pagare il 3%, con l'importo e il codice causale) e
  `INVOICE_REDEMPTION_REJECTED`. Non serve un tipo dedicato per "accreditato"
  -- `credit_wallet()` invia già `CASHBACK_RECEIVED` automaticamente, quindi
  una conferma pagamento produce due notifiche (una per riga di credito),
  comportamento accettato così com'è, non soppresso.
- Migrazioni: `0019_wallet_transfer_gate`, `0020_partners_and_product_categories`,
  `0021_invoice_redemptions` -- tutte applicate e verificate su questo server.

**Frontend** (`apps/dashboard/components/`):
- `admin-partners-panel.tsx` — CRUD semplice (nome, attiva/disattiva). Nuova
  tab admin "Fornitori Partner".
- `admin-invoice-redemptions-panel.tsx` — coda con filtro per stato, "Vedi
  documento" (apre l'URL presigned), form "Verifica importo" (mostra il 3%
  calcolato live prima di confermare), "Conferma bonifico ricevuto", "Rifiuta"
  con motivo. Nuova tab admin "Riscatti Fatture".
- `invoice-redemption-panel.tsx` — lato cliente/promoter: form nuova
  richiesta (partner, importo dichiarato, upload foto/PDF con
  `capture="environment"` per la fotocamera mobile), lista "le tue
  richieste" con stato, e per una richiesta `PAYMENT_PENDING` mostra importo
  da pagare + IBAN (o messaggio "contatta l'amministrazione") + codice
  causale. Nuova tab "Riscatta Cashback" sia nella dashboard cliente sia in
  quella promoter (stesso componente, condiviso).
- `admin-products-panel.tsx` (esteso) — select "Categoria" nel form di
  creazione prodotto, campo "Sconto pagabile in crediti (%)" (disabilitato
  con spiegazione quando categoria = Interno), badge categoria + badge
  sconto sulla card di ogni prodotto in elenco.
- `wallet-panel.tsx` / `admin-wallets-panel.tsx` (estesi) — le righe dello
  storico ora mostrano un'etichetta specifica quando `source` è valorizzato
  ("Riscatto fattura" / "Bonus 3% riscatto fattura") invece del generico
  "Ricarica/Cashback".

**Verificato live** (non solo test unitari): intero ciclo via chiamate HTTP
reali contro l'API in esecuzione, incluso upload multipart vero -- fattura da
80,00€ dichiarata e confermata → richiesti 2,40€ → bonifico confermato →
wallet accreditato esattamente 82,40€ in due righe distinte
(`INVOICE_REDEMPTION_BASE` 8000, `INVOICE_REDEMPTION_BONUS` 240), entrambe
con lo stesso `reference_invoice_redemption_id`. Verificati anche: rifiuto
per tipo file non supportato, rifiuto per partner inesistente, blocco di un
secondo `confirm-payment` sulla stessa richiesta già accreditata (nessun
doppio accredito), permessi (`PROMOTER` riceve 403 su `POST /partners`). I
dati di test creati durante la verifica sono stati rimossi dal database
(nessun partner/riscatto fittizio o saldo alterato è rimasto).

## Cosa NON è stato costruito

- [ ] **Fase 4 — Sconto crediti nel checkout**: `Product.category` e
      `credit_discount_percentage` esistono e sono configurabili, MA nessuna
      schermata di acquisto/creazione contratto legge ancora questi campi per
      applicare davvero lo sconto o proporre "paga con crediti" come metodo.
      Questo è il pezzo che resta per chiudere il cerchio (i crediti oggi si
      possono guadagnare ma non ancora spendere in checkout). Vedi anche
      `docs/paid-contract-commission-audit.md` per come funziona oggi la
      creazione/pagamento di un contratto -- un contratto non ha nemmeno un
      campo importo proprio oggi (prezzo letto dal `product_version` al
      momento dell'acquisto), quindi questa fase probabilmente richiede anche
      di congelare un `amount_cents` sul contratto, non solo aggiungere un
      selettore di pagamento.
- [ ] **OCR reale**: il wizard chiede l'importo a mano al cliente; non c'è
      nessuna lettura automatica assistita del documento. Deliberatamente
      rimandato -- richiede una decisione su quale servizio di lettura
      documenti usare (costo/dipendenza esterna), l'ammin verifica comunque
      sempre a mano quindi il sistema è già pienamente funzionante senza.
- [ ] Controllo automatico anti-duplicato (stessa fattura caricata due
      volte) -- oggi previene solo la verifica umana.

## Decisioni prese

- [x] **I prodotti interni Lial NON generano mai cashback automatico.**
      L'unica fonte di credito è il riscatto fattura partner.
- [x] **Percentuale**: fissa al 3%, sia per il pagamento richiesto sia per il
      bonus (`invoice_redemptions/models.py::CASHBACK_PERCENTAGE`).
- [x] **Tetto alla percentuale di sconto sui prodotti**: nessun limite di
      sistema imposto -- un admin può impostare qualunque valore 0-100 su un
      prodotto DROPSHIPPING/PARTNER. Deciso per omissione (non richiesto
      esplicitamente un tetto), facile da aggiungere dopo se serve.

## Decisioni ancora da prendere

- [ ] **Fatture duplicate/false**: serve un controllo automatico
      numero-fattura + fornitore, o la sola verifica umana basta?
- [ ] **Pagamento del residuo nel checkout** (Fase 4): sempre bonifico come
      oggi? (Non esiste alcun `PaymentProvider` reale nel sistema.)
- [ ] **Scadenza dei crediti**: restano validi per sempre o decadono?
- [ ] **Anagrafica fornitori-partner**: bastano nome/logo (quello che c'è
      oggi), o servono anche referente/accordo di partnership/percentuale
      commissione ricevuta da loro?
- [ ] **IBAN aziendale reale**: `COMPANY_BANK_IBAN` è ancora vuoto in
      `.env` -- il wizard cliente funziona ma mostra "contatta
      l'amministrazione" finché non viene compilato.

## Come riprendere se una sessione futura parte da zero

1. Leggi questo file per intero prima di fare qualunque altra cosa: Fasi
   0-2 (+3 senza OCR) sono FATTE e verificate, non richiederle da capo.
2. Se l'utente chiede di continuare, il pezzo mancante è la Fase 4
   (checkout) -- inizia da lì, non dalle fondamenta.
3. Per le decisioni ancora aperte sopra, chiedi solo quelle.
4. Aggiorna le checkbox di questo file mano a mano che qualcosa cambia.
