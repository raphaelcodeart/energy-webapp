# Piano: Cashback da riscatto fatture fornitori-partner

**Stato: Fasi 0, 1, 2, 3 (senza OCR reale) E 4 sono tutte implementate e
verificate end-to-end via HTTP reale il 2026-09-05.** Il progetto è
funzionalmente completo: un cliente può riscattare una fattura partner in
crediti, e quei crediti si possono davvero spendere per pagare (in parte) un
prodotto dropshipping/partner nel nuovo dominio `orders`. Resta solo l'OCR
vero (deliberatamente rimandato) e il self-checkout diretto del cliente
(per ora solo admin crea gli ordini, per scelta esplicita dell'utente).

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

## Cosa è stato costruito (Fasi 0-4 complete)

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
- `orders/` — dominio nuovo (Fase 4), acquisto di prodotti DROPSHIPPING/
  PARTNER con sconto crediti opzionale. **Deliberatamente NON un `Contract`**:
  `Contract.supply_point_id` è NOT NULL per disegno (ogni contratto è una
  fornitura energia), un ordine di un gadget non ha nulla di equivalente --
  vedi `orders/models.py` per il ragionamento completo. Decisione confermata
  con l'utente (vedi §Decisioni prese sotto).
  Stati: `AWAITING_PAYMENT → PAID`, con `CANCELLED` raggiungibile solo da
  `AWAITING_PAYMENT` (storna il credito applicato, vedi sotto). Se il credito
  applicato copre il 100% del prezzo, l'ordine salta direttamente a `PAID`
  alla creazione -- nessun bonifico da attendere.
  Admin sceglie cliente + prodotto + quanto credito applicare (fino al tetto
  configurato sul prodotto E al saldo disponibile del cliente -- entrambi
  mostrati in anteprima via `GET /orders/quote` prima di creare l'ordine).
  Il resto (`amount_cents - credit_applied_cents`) si paga in bonifico come
  già avviene per i contratti, confermato con `POST /orders/{id}/confirm-payment`.
  Solo admin per ora (`wallet.manage`-gated su ogni endpoint): **nessun
  self-checkout cliente**, per scelta esplicita dell'utente il 2026-09-05.
  `POST /orders/{id}/cancel` storna l'esatta transazione di debito crediti
  via `reverse_transaction()` (non un nuovo accredito generico) -- vedi sotto
  per l'estensione fatta a quella funzione.
- `wallets/` (ulteriore estensione per la Fase 4) — nuovo tipo
  `PURCHASE_DEBIT` (speculare a `ADMIN_CREDIT`: `to_wallet_id` NULL invece di
  `from_wallet_id` NULL, i soldi escono da un wallet per pagare un ordine e
  cessano di esistere) e nuova funzione `debit_wallet_for_purchase()` con la
  stessa guardia atomica compare-and-swap di `debit_and_transfer()`. Il saldo
  viene comunque controllato ANCHE prima di creare la riga Order (non solo
  nel CAS), per non lasciare un ordine "fantasma" flush-ato ma mai committato
  in sessione se il debito fallisce -- un `db.rollback()` esplicito lì
  avrebbe invece rotto il fixture di test a SAVEPOINT, stesso motivo per cui
  `debit_and_transfer()` non lo fa già. `reverse_transaction()` esteso per
  gestire correttamente lo storno di un `PURCHASE_DEBIT` (nessun wallet
  destinatario da cui prelevare, solo un accredito di ritorno al mittente).
- Migrazioni: `0019_wallet_transfer_gate`, `0020_partners_and_product_categories`,
  `0021_invoice_redemptions`, `0022_orders` -- tutte applicate e verificate
  su questo server.

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
  "Ricarica/Cashback", più un'etichetta per il nuovo tipo `PURCHASE_DEBIT`
  ("Pagamento ordine (crediti)").
- `admin-orders-panel.tsx` (nuovo, Fase 4) — nuova tab admin "Ordini": form
  "Nuovo Ordine" (seleziona cliente con login attivo + prodotto non-INTERNAL,
  mostra in tempo reale via `GET /orders/quote` il tetto sconto e il saldo
  cliente, precompila l'importo crediti al massimo utilizzabile ma resta
  modificabile, anteprima del residuo da bonifico prima di confermare), lista
  ordini filtrabile per stato con azioni "Conferma bonifico ricevuto" /
  "Annulla" (con motivo).

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

**Fase 4 verificata live separatamente** (stesso metodo, HTTP reale): prodotto
dropshipping da 80,00€ con 25% di sconto crediti configurato, cliente con
30,00€ di saldo, ordine creato applicando 20,00€ di credito (il tetto) →
saldo sceso a 10,00€, ordine `AWAITING_PAYMENT` con residuo 60,00€ →
`confirm-payment` → `PAID`. Verificati anche: rifiuto sopra il tetto
configurato, rifiuto per saldo insufficiente (nessun ordine fantasma creato),
copertura 100% in crediti che salta dritto a `PAID` senza bonifico,
annullamento che restituisce esattamente il credito applicato via una vera
riga `REVERSAL` (non un accredito generico), doppio annullamento/doppia
conferma bloccati, prodotto `INTERNAL` rifiutato con messaggio che rimanda a
`POST /contracts`. Dati di test rimossi.

## Cosa NON è stato costruito

- [ ] **OCR reale**: il wizard chiede l'importo a mano al cliente; non c'è
      nessuna lettura automatica assistita del documento. Deliberatamente
      rimandato -- richiede una decisione su quale servizio di lettura
      documenti usare (costo/dipendenza esterna), l'ammin verifica comunque
      sempre a mano quindi il sistema è già pienamente funzionante senza.
- [ ] Controllo automatico anti-duplicato (stessa fattura caricata due
      volte) -- oggi previene solo la verifica umana.
- [ ] **Self-checkout cliente**: il cliente non può ancora creare da solo un
      ordine dal marketplace -- per scelta esplicita dell'utente, per ora
      resta un'azione admin (come già oggi per i contratti). Se in futuro si
      vuole aprire il self-checkout, l'endpoint `POST /orders` andrebbe
      riaperto a un ruolo cliente con `customer_user_id` forzato al chiamante
      (non passato liberamente come oggi), non serve altro cambiamento di
      modello dati.

## Decisioni prese

- [x] **I prodotti interni Lial NON generano mai cashback automatico.**
      L'unica fonte di credito è il riscatto fattura partner.
- [x] **Percentuale**: fissa al 3%, sia per il pagamento richiesto sia per il
      bonus (`invoice_redemptions/models.py::CASHBACK_PERCENTAGE`).
- [x] **Tetto alla percentuale di sconto sui prodotti**: nessun limite di
      sistema imposto -- un admin può impostare qualunque valore 0-100 su un
      prodotto DROPSHIPPING/PARTNER. Deciso per omissione (non richiesto
      esplicitamente un tetto), facile da aggiungere dopo se serve.
- [x] **Modello dati checkout**: nuovo dominio `orders` separato da
      `Contract`, non un'estensione di quest'ultimo. Confermato con l'utente
      il 2026-09-05 (opzione "consigliata" della domanda posta).
- [x] **Chi avvia un ordine**: solo admin per ora, niente self-checkout
      cliente. Confermato con l'utente il 2026-09-05.
- [x] **Chi può confermare riscatti/pagamenti**: `ADMIN` (non solo
      `SUPER_ADMIN`) può già farlo -- verificato nel DB, `wallet.manage` è
      concesso a SUPER_ADMIN/ORGANIZATION_ADMIN/ADMIN. Nessuna modifica
      necessaria, era già così.
- [x] **Pagamento del residuo nel checkout**: bonifico + conferma admin,
      stesso meccanismo già esistente per i contratti (nessun
      `PaymentProvider` reale nel sistema, non è cambiato con questa fase).

## Decisioni ancora da prendere

- [ ] **Fatture duplicate/false**: serve un controllo automatico
      numero-fattura + fornitore, o la sola verifica umana basta?
- [ ] **Scadenza dei crediti**: restano validi per sempre o decadono?
- [ ] **Anagrafica fornitori-partner**: bastano nome/logo (quello che c'è
      oggi), o servono anche referente/accordo di partnership/percentuale
      commissione ricevuta da loro?
- [ ] **IBAN aziendale reale**: `COMPANY_BANK_IBAN` è ancora vuoto in
      `.env` -- il wizard cliente funziona ma mostra "contatta
      l'amministrazione" finché non viene compilato.

## Come riprendere se una sessione futura parte da zero

1. Leggi questo file per intero prima di fare qualunque altra cosa: **tutte
   le Fasi 0-4 sono FATTE e verificate** (Fase 3 senza OCR reale, per
   scelta), non richiederle da capo. Il progetto è funzionalmente completo
   da riscatto a spesa.
2. Se l'utente chiede di continuare, i pezzi mancanti sono solo: OCR reale,
   controllo anti-duplicato fatture, self-checkout cliente (vedi "Cosa NON è
   stato costruito") -- tutti extra/rifiniture, non fondamenta mancanti.
3. Per le decisioni ancora aperte sopra, chiedi solo quelle.
4. Aggiorna le checkbox di questo file mano a mano che qualcosa cambia.
