# Implementation Progress

Updated at the end of each work session. This is the authoritative "what's actually
done vs. planned" record — `architecture.md` describes the target, this file describes
reality.

## Session 62 — 2026-09-17 — Shop Lial Partner dentro "Fai la spesa con Lial"; stock CJ corretto

Richiesta dell'utente: il cliente non vedeva i prodotti CJ nello Shop, e al
cliente non interessa da dove arriva un prodotto: meglio una categoria sola?

- [x] Perché non si vedevano: lo shop era lasciato spento (Session 60). Nessun
  bug di visibilità; aggiunto però un avviso in Impostazioni se lo shop è
  visibile mentre la sandbox è accesa (i clienti pagherebbero ordini che CJ non
  spedisce).
- [x] Scelta UX: i prodotti CJ compaiono **dentro "Fai la spesa con Lial"**,
  con la stessa card dei prodotti del catalogo (prezzo, "+ spedizione",
  tempi di consegna, LialCash usabili). Tolta la scheda separata. Backend,
  tabelle, checkout e interruttore dello shop restano separati: ogni card apre
  il proprio checkout. "Acquisti LialEnergy" (AliExpress) non è stato toccato.
- [x] Nessuna traccia della provenienza per il cliente: titolo della finestra
  prodotto, voce sulla pagina Stripe ("Ordine XXXX — Lial Energy") e dettaglio
  in Contabilità dicono "Fai la spesa con Lial"; lo staff continua a vedere
  "Shop Lial Partner (CJ)".
- [x] **Bug trovato in verifica dal vivo**: l'unico prodotto importato risultava
  esaurito, ma CJ ne ha 40.000. `product/query` restituisce `inventories: null`
  per la maggior parte dei prodotti; lo stock ora arriva da
  `product/stock/getInventoryByPid` (una chiamata per prodotto). Il magazzino di
  partenza è quello che copre più varianti (a parità, il più vicino). Prodotto
  in produzione risincronizzato: disponibile.
- [x] Test: 2 nuovi (stock e magazzino), suite 389 verde.

## Session 61 — 2026-09-17 — Shop Lial Partner: ricarico 100% già all'importazione

Richiesta dell'utente: "pago 10, vendo a 20" già al momento dell'importazione,
modificabile dopo.

- [x] Ricarico generale predefinito portato al 100% (modello; in produzione
  impostato da 40 a 100, prodotti ricalcolati). Nessuna modifica di schema.
- [x] Finestra "Importa": nuovo campo **Ricarico %** precompilato con il
  ricarico generale; i prezzi delle varianti si ricalcolano mentre si scrive.
  Uguale al generale → sul prodotto non si salva nulla e segue le Impostazioni;
  diverso → ricarico solo per quel prodotto, modificabile da Prodotti in
  vendita → Modifica.
- [x] Test: nuovo default 100% (14 test CJ).

## Session 60 — 2026-09-17 — Shop Lial Partner: integrazione CJ Dropshipping

Richiesta dell'utente: un secondo negozio "importato", come quello AliExpress
("Acquisti LialEnergy"), ma collegato davvero via API a CJ Dropshipping
(it.cjdropshipping.com): tabelle e gestione interna separate, per il cliente
un'altra scheda dello Shop, **"Shop Lial Partner"**, con lo stesso checkout e
la stessa possibilità di spendere i LialCash. Chiave API configurabile
dall'amministratore. Regole in `business-rules.md#partner-shop`, tabelle in
`database-model.md` §17.

- [x] Dominio nuovo `cj_dropshipping` (models, client, pricing, service,
  router, schemas), quattro tabelle: `cj_settings`, `cj_products`,
  `cj_variants`, `cj_orders`; `wallet_transactions.reference_cj_order_id`.
  Migrazioni `0044_cj_dropshipping` e `0045_cj_token_text` (i token JWT di CJ
  superano i 500 caratteri: scoperto al primo collegamento reale, colonne
  portate a TEXT, test di regressione aggiunto).
- [x] Client CJ API 2.0: token (180 giorni) salvati e rinnovati da soli, un
  solo slot Redis al secondo per organizzazione condiviso da API e Celery
  (limite CJ), errori di CJ mostrati in italiano agli amministratori.
- [x] Prezzi: costo CJ in USD × cambio × (1 + ricarico%) + ricarico fisso,
  arrotondato **per eccesso** a ,90 / ,99 / al centesimo; spedizione pagata dal
  cliente al costo reale (preventivo CJ in tempo reale, cache 30 minuti) oppure
  inclusa nel prezzo. Cambiare una regola ricalcola subito tutti i prodotti.
- [x] Admin, voce di menu **Shop Lial Partner**: Impostazioni (chiave API
  mascherata, verifica connessione e saldo CJ, shop acceso/spento, sandbox,
  invio automatico, cambio, ricarico, arrotondamento, spedizione, LialCash
  predefiniti, esempio di prezzo dal vivo); Catalogo CJ (ricerca per parola,
  categoria, prezzo, spedizione gratuita, con il prezzo di vendita già
  calcolato; anteprima con foto, varianti, stock, magazzino di partenza e
  spedizione più economica verso l'Italia; importazione con nome e descrizione
  da tradurre); Prodotti in vendita (modifica, foto principale, ricarico per
  prodotto, prezzo fisso per variante, varianti attive, "Aggiorna da CJ",
  nascondi); Ordini (da gestire / non pagati / in viaggio / consegnati, "Invia
  a CJ", "Paga su CJ", "Aggiorna stato", tracking, margine stimato, errori).
- [x] Cliente: scheda "Shop Lial Partner" nello Shop (visibile solo con shop
  acceso e almeno un prodotto), scheda prodotto con galleria, varianti,
  quantità e tempi di consegna, checkout con indirizzo precompilato dal
  profilo, spedizione calcolata dal vivo, LialCash con codice via email,
  bonifico o carta. Gli ordini compaiono in "I miei Ordini" con stato della
  spedizione e link "Traccia pacco"; notifica ed email quando parte e quando
  arriva.
- [x] Invio a CJ: `createOrderV2` (solo creazione) + `payBalance` dal saldo
  CJ; numero d'ordine `LIAL-<id>` usato anche per ritrovare su CJ un ordine
  creato da un invio interrotto. Presa in carico con UPDATE condizionale
  (niente doppi invii tra clic e automatico); un invio rimasto a metà si
  riprende dopo 10 minuti. Ordine creato ma non pagato (saldo CJ basso) resta
  "Su CJ, da pagare": il nuovo tentativo paga soltanto.
- [x] Celery: `cj_sync_orders_task` ogni 30 minuti (stato, tracking,
  consegna), `cj_sync_products_task` alle 03:30 (costo, stock,
  disponibilità, prezzi), `cj_forward_order_task` per l'invio automatico.
- [x] Stripe: `create_checkout_session_for_cj_order`, webhook
  `metadata.kind="cj_order"`. Contabilità: movimenti in euro e LialCash degli
  ordini CJ, dettaglio con indirizzo, tracking e cronologia della spedizione.
- [x] Ordini admin e cliente unificati: gli ordini CJ compaiono anche in
  "Ordini" (conferma bonifico, annulla con restituzione LialCash).
- [x] Produzione: chiave API salvata nel database (mai nel repository),
  collegamento verificato (token fino al 16/03/2027, saldo CJ 0 USD, 578
  categorie, ricerca e anteprima con spedizione reale CN→IT). **Lo shop è
  lasciato spento e in sandbox**: si accende da Impostazioni dopo aver
  importato i prodotti (vedi open-questions #17).
- [x] Test: 13 nuovi (`tests/test_cj_dropshipping.py`, CJ simulato), suite
  completa verde. Nota di deploy: celery-worker e celery-beat hanno una loro
  immagine, vanno ricostruiti (`build celery-worker celery-beat`), non solo
  ricreati.

## Session 59 — 2026-09-16 — Cashback dei contratti a rate: intero alla prima rata oppure rata per rata, a scelta dell'amministratore

Richiesta dell'utente: per semplificare, con un contratto pagato a 3 o 12 rate
riconoscere l'intero cashback già alla prima rata, in un'unica ricarica; e
rendere la scelta amministrabile in Impostazioni (intero subito, oppure una
ricarica a ogni rata incassata). Dettagli in
`business-rules.md#instalment-cashback`.

- [x] Impostazione dell'organizzazione `contract_instalment_cashback_mode`
  (`PER_INSTALMENT` predefinito, `UPFRONT`), nessuna modifica di schema: vive
  nel JSONB `organizations.settings`. Scheda nuova in Impostazioni.
- [x] Cashback anticipato: alla prima rata l'intero importo, con la stessa
  chiave del pagamento unico; il registro del wallet, non l'impostazione,
  impedisce che quel contratto riceva poi anche il cashback per rata.
- [x] **Difetti trovati nel farlo**: una rata confermata a mano
  dall'amministratore non dava cashback; e la chiave per rata era la fattura
  Stripe, quindi una rata fallita, confermata a mano e poi riaddebitata da
  Stripe sulla stessa fattura avrebbe dato cashback due volte. Ora la chiave è
  il numero della rata e la conferma manuale accredita. In produzione non
  c'era ancora nessun cashback per rata, quindi nessun dato da migrare.
- [x] Schermata di pagamento: il testo sul cashback segue l'impostazione.
  Istruzioni del webhook in Impostazioni corrette con i tre eventi necessari.
- [x] Test: 3 nuovi (anticipato, cambio d'impostazione senza doppioni, rata
  confermata a mano e poi riaddebitata), 2 aggiornati per il nuovo campo. Suite
  completa verde (374).

## Session 58 — 2026-09-16 — Documentazione riallineata

Su richiesta dell'utente: documentazione aggiornata e struttura del database
rigenerata per il repository.

- [x] `server-migration-guide.md`: dump allineato alla revision `d5a1b3c9e472`
  (migrazione 0043), 67 tabelle, le due tabelle delle pratiche nell'elenco per
  dominio, e gli **eventi del webhook Stripe da abilitare** nella
  configurazione di un server nuovo.
- [x] `open-questions.md`: aggiunti i punti ancora aperti — eventi `invoice.*`
  del webhook Stripe, pacchetto gas registrato come luce, IVA nei prezzi dello
  Shop, controllo dello stesso POD senza codice.
- [x] `docs/database-schema.sql` rigenerato con `scripts/dump-schema.sh`
  (nessuna modifica di schema da 0043: il diff è solo il token casuale di
  `pg_dump`).

## Session 57 — 2026-09-16 — Documenti: "Visualizza" apre un popup, non una nuova scheda

Richiesta dell'utente: cliccando "Visualizza" su un documento caricato (es.
documento d'identità) non si deve uscire dalla pagina, ma vedere l'immagine
ingrandita in un popup. Chiarito anche che nella pagina Stripe ogni riga
"rata mensile" è un POD: 140 + 140 + 60 = 340 € al mese.

- [x] `document-preview-modal.tsx`: il file viene scaricato dal link firmato e
  mostrato in memoria (blob) sopra la pagina — foto adattata allo schermo con
  "Dimensione reale" / clic per lo zoom, PDF nel visore del browser, "Scarica"
  e chiusura con Esc. In memoria e non con un riquadro che punta al file
  perché nginx manda `X-Frame-Options: DENY` su tutto, che bloccherebbe i PDF.
- [x] Usato da ogni elenco documenti (cliente, promoter, pratica, admin).
- Nessuna modifica al backend né al database.

## Session 56 — 2026-09-16 — Pagina Stripe: il piano a rate scritto per intero

Segnalazione dell'utente: pagando in 3 rate una pratica da 1.020 € Stripe
mostrava "340,00 € al mese", e non era chiaro. Verificato in sola lettura: gli
importi erano giusti (3 × 340 = 1.020; 12 × 85 = 1.020) e **il pagamento non era
stato completato** — la sessione a 3 rate risultava aperta e non pagata, quella
a 12 rate chiusa dal sistema all'apertura della nuova, nessun addebito né
webhook. Il difetto era di comunicazione: Stripe per un abbonamento mostra
solo la cifra mensile.

- [x] Testo sopra il pulsante di pagamento con numero di rate, importo, totale
  e "gli addebiti si fermano da soli dopo l'ultima rata"; descrizione per riga.
  Parametri provati sull'API Stripe in modalità test (sessione creata e subito
  fatta scadere) prima del rilascio.
- [x] Test aggiornato. Suite completa verde (371).

## Session 55 — 2026-09-16 — Catalogo solo in lettura, il promoter compila la pratica per il cliente, documenti con foto

Richiesta dell'utente: in "I miei Contratti" il catalogo con "Attiva Contratto"
sul singolo pacchetto non ha più senso — diventa "Dettagli" e l'attivazione
passa solo dalla pratica. Lo stesso sistema lo deve avere il promoter per i
suoi clienti, nuovi o già registrati, segnando che l'ha fatto lui ma lasciando
tutto al cliente, che poi trova i contratti e paga. Documenti caricabili come
file o fotografati.

- [x] Catalogo: "Dettagli" al posto di "Attiva Contratto"; il popup del
  pacchetto porta alla pratica. Testi della sezione aggiornati.
- [x] Promoter: "Registra e apri la pratica" apre subito la pratica per il
  cliente appena registrato; "Attiva nuovo contratto" in evidenza per quelli
  esistenti. Badge "Compilata da…" / "Preparata dal tuo promoter…".
- [x] All'invio di una pratica del promoter: notifica ed email al cliente.
- [x] Pulsante **Foto** (fotocamera del telefono) su ogni documento e sugli
  allegati aggiuntivi.
- [x] **Difetto trovato**: un promoter che è anche cliente ("Lavora con noi")
  veniva rifiutato sui documenti dei contratti dei propri clienti, perché il
  controllo leggeva solo il primo ruolo del token. Ora si verificano entrambe
  le relazioni, compreso "ha compilato la pratica".
- [x] Test: 2 nuovi. Suite completa verde.
- Nessuna modifica allo schema del database.

## Session 54 — 2026-09-16 — Contabilità: totali, rate dei contratti, dettaglio collegato di ogni movimento

Richiesta dell'utente: nella pagina Contabilità togliere il sottotitolo
dell'area cliente e l'immagine di intestazione per fare spazio a più card di
totali (totale speso bonifico + Stripe, provvigioni, altri dati utili);
rendere l'elenco dei movimenti professionale e leggibile (data piccola in
grassetto, titolo grande, sottotitolo piccolo); ogni riga — riscatto, ordine,
ricarica — deve aprire un popup con il dettaglio di quella specifica cosa,
tutto collegato, con ogni dato del pagamento (orari di accettazione ecc.) e
strumenti di ricerca utili.

- [x] **Mancavano i pagamenti dei contratti**: pagare un contratto non
  lasciava nessuna traccia in euro in Contabilità, solo il cashback. Ora ogni
  rata pagata è un movimento `CONTRACT_PAYMENT` (carta o bonifico).
- [x] `GET /accounting/mine/summary`: totali calcolati sul server dagli stessi
  movimenti, compresa la prossima rata e le provvigioni per chi è promoter.
- [x] `GET /accounting/{mine,admin}/detail?ref=`: dettaglio unico per
  movimento LialCash, ordine, riscatto e contratto, con cronologia al secondo
  e autore di ogni passaggio; lato cliente limitato alle sue cose.
- [x] Pagina cliente ridisegnata: niente sottotitolo né banner, 10 card di
  totali, ricerca testuale + periodo + 9 filtri con totali della selezione,
  movimenti raggruppati per mese, riga nuova (data/ora piccola in grassetto,
  icona per categoria, titolo grande, descrizione piccola, chip del
  riferimento), popup di dettaglio con navigazione tra movimenti collegati e
  "Indietro". Stesso popup nella Contabilità admin.
- [x] Test: 4 nuovi (dettaglio ordine con cronologia e privacy, totali, rate
  del contratto in contabilità, cronologia con orari con e senza fuso). Suite
  completa verde (368) prima dell'ultimo test, aggiunto dopo il controllo
  sui dati reali.
- [x] **Trovato verificando sui dati reali, dopo il rilascio**: il dettaglio di
  un ordine vero rispondeva 500, perché alcune colonne più vecchie restituiscono
  orari senza fuso e la cronologia non riusciva a ordinarli insieme agli altri.
  Corretto (normalizzati a UTC) e ricontrollato in sola lettura: tutti i
  dettagli di un cliente reale (15) e i primi movimenti della vista admin (29)
  rispondono.
- Nessuna modifica allo schema del database.

## Session 53 — 2026-09-16 — Pratica: dati una volta, "quanti POD hai?", poi solo il contratto per POD

Correzione dell'utente sul flusso appena rilasciato: vuole tutti i dati
(indirizzo compreso, PEC, IBAN) **una volta all'inizio** come prima, insieme a
**"Quanti POD hai?"** con il contatore; poi i documenti d'identità una volta;
poi trovarsi **i POD già creati** e solo **associare il contratto** a ciascuno.
Il **codice POD non serve**: tolto.

- [x] Migrazione 0043: indirizzo sulla pratica (backfill dal primo punto),
  `supply_points.energy_type` nullable. Provata su una copia del database
  reale, andata e ritorno.
- [x] Backend: la pratica si crea con dati + indirizzo + numero di POD (e
  l'eventuale pacchetto di partenza per tutti); `PUT /points-count` aggiunge o
  toglie POD (prima quelli senza contratto); `PATCH /points/{id}/address` per
  un POD a un altro indirizzo; niente più codici né validazione POD/PDR; è il
  pacchetto scelto a fare del POD un punto luce o gas; tutti i pacchetti sono
  proponibili su ogni POD. Le righe Stripe mostrano "pacchetto — indirizzo".
- [x] Wizard in 4 passaggi: Dati (con "Quanti POD hai?") → Documenti →
  Contratti → Riepilogo. I POD si chiamano "POD 1", "POD 2"… quando non hanno
  un codice.
- [x] Test aggiornati (20 nella suite della pratica). Suite completa verde.
- Conseguenza dichiarata: senza codice non c'è più il controllo "stesso POD in
  due contratti in corso"; il punto reale si identifica dalla bolletta.

## Session 52 — 2026-09-16 — La pratica di attivazione: N punti, N contratti, un pagamento

Richiesta dell'utente: quando si attiva un contratto si chiede al cliente
quanti POD ha, ma poi tutti i punti prendevano lo stesso pacchetto, i
documenti andavano caricati per ogni punto e si pagava con N checkout
separati. Serve: configurare ogni POD con il suo pacchetto, un totale e un
pagamento unico, ma **ogni POD resta un contratto indipendente** per il
cliente, per il promoter e per le provvigioni. L'area "Attiva contratti"
diventa l'elenco delle pratiche, con un pulsante ben evidente per aprirne una
nuova. Dettagli in `business-rules.md#contract-request`.

Scelte prese in autonomia (l'utente ha chiesto "ingegnerizza bene e fai tu"):
un solo flusso anche per un solo POD (niente percorso separato); un piano di
pagamento per pratica (Stripe non gestisce in modo pulito durate diverse nello
stesso abbonamento); documenti dell'intestatario una volta sola sulla pratica;
niente pacchetti luce+gas combinati (il catalogo non ne ha); i contratti
esistenti ricevono ciascuno una pratica di un contratto.

- [x] **Modello dati** (migrazione 0042): `contract_requests`,
  `contract_request_checkouts`; `contracts.contract_request_id` NOT NULL
  (backfill 1:1, stesso id), `stripe_subscription_item_id`,
  `billing_stopped_at`; `product_version_id` nullable solo in bozza (CHECK);
  documenti della pratica (`documents.contract_request_id`, CHECK un solo
  proprietario); rate uniche per `(contract_id, stripe_invoice_id)`.
  Provata su una copia del database reale, andata e ritorno.
- [x] **Backend** `contracts/requests.py` + `/contract-requests`: bozza, punti
  (validazione POD/PDR, un contratto in corso per codice), pacchetto per punto
  con prezzo congelato alla scelta, invio di tutti i punti insieme, accessi
  cliente/promoter/staff.
- [x] **Pagamento unico**: una Checkout con una riga per contratto, oppure un
  abbonamento con una voce per contratto; ogni fattura mensile letta riga per
  riga e registrata sul contratto giusto; pagamento doppio rilevato e non
  riaccreditato; "Interrompi addebiti" toglie dall'abbonamento solo quel
  contratto. Corretto anche lo stop dopo l'ultima rata: il periodo su API
  dahlia non è più sull'abbonamento, e senza `proration_behavior="none"`
  Stripe avrebbe accreditato al cliente i giorni dopo l'ultima rata.
- [x] **Cliente**: "I miei Contratti" = elenco pratiche + "Attiva nuovo
  contratto" + catalogo "Scopri i pacchetti"; la voce di menu "Attiva
  Contratto" è confluita qui (i vecchi link `?tab=activate-contract`
  funzionano). Wizard in 5 passaggi con salvataggio continuo e "Riprendi".
- [x] **Promoter** ("Miei Clienti"): stessa pratica per il cliente, elenco
  pratiche per cliente; invia ma non paga.
- [x] **Admin**: nuova voce "Pratiche" (filtri Da verificare / Documenti
  mancanti / Non pagate / Rate non riscosse / In compilazione), dettaglio con
  intestatario, documenti comuni, tentativi di pagamento, e ogni punto con
  Documenti, Provvigioni, Recensisci, Interrompi addebiti; **"Approva i N
  contratti in revisione"** mostra l'anteprima provvigioni di ciascuno e manda
  una transizione per contratto. In "Tutti i Contratti" ogni riga porta alla
  sua pratica.
- [x] Rimossi i componenti del vecchio flusso a contratto singolo
  (`contract-activation-wizard`, `contract-completion-screen`,
  `contract-payment-panel`). Le rotte per contratto restano: le sessioni
  Stripe già aperte su un contratto singolo vengono ancora onorate.
- [x] Test: 19 nuovi (`tests/test_contract_requests.py`, comprese le rotte
  HTTP e i webhook con righe per contratto). Suite completa verde.
- [ ] **Segnalato, non toccato**: il pacchetto "GAS Energia Circolare con cash
  back" (codice `LUCE-STD-COPY`) è registrato come **luce**: con il filtro per
  tipo di punto compare tra i pacchetti per i POD. Va corretto da Prodotti →
  tipo energia Gas (ha già un contratto, che resta invariato).

## Session 51 — 2026-09-16 — Verifica del flusso soldi: tre difetti trovati e corretti

L'utente ha chiesto di spiegare quando partono provvigioni e cashback, se gli
abbonamenti addebitano davvero da soli il mese dopo, e se i prodotti fisici
sono distinti dagli abbonamenti. Verificando invece di rispondere a memoria:

- [x] **Le rate successive non ci arrivavano.** L'endpoint webhook su Stripe
  (letto via API, sola lettura) ha abilitato **solo**
  `checkout.session.completed`. Stripe addebita davvero la carta ogni mese,
  ma `invoice.paid` / `invoice.payment_failed` non vengono mai inviati:
  dalla 2ª rata in poi niente cashback, niente provvigioni, nessun avviso di
  addebito fallito. **Da abilitare sul pannello Stripe** (non modificato da
  qui senza conferma dell'utente).
- [x] **E anche abilitandoli sarebbero stati ignorati.** L'account e l'SDK
  sono sulla versione API `2026-08-26.dahlia`, dove `invoice.subscription`
  non esiste più (è in `invoice.parent.subscription_details.subscription`).
  Il codice leggeva il campo vecchio: ogni rata sarebbe sembrata una fattura
  senza abbonamento e scartata in silenzio. `payments/service.py::
  _invoice_subscription_id` legge entrambe le forme; un test le copre tutte e
  due.
- [x] **Un prodotto fisico poteva diventare "× 12 mesi".** Il form admin
  imposta ogni versione a MONTHLY / 12 mesi di default, quindi anche i due
  Power Bank e lo Zaino li hanno. Il checkout ordini addebitava già il prezzo
  una volta sola, ma la scheda Shop mostrava "39,00 € /mese", e un prodotto
  fisico o digitale in categoria Lial Energy sarebbe passato dal calcolo
  "canone × mesi". Ora `pricing.RECURRING_PRODUCT_TYPES` = ENERGY_CONTRACT e
  SUBSCRIPTION: solo questi sono prezzati a canone; PHYSICAL/DIGITAL restano
  prezzo unico, e l'etichetta "/mese" compare solo per i tipi ricorrenti.
- [ ] **Segnalato, non toccato**: nello Shop la scheda e il dettaglio prodotto
  mostrano "+ IVA 22% (totale)", ma l'ordine addebita il prezzo di listino
  senza aggiungere IVA. Serve una decisione: il prezzo dello Shop è IVA
  inclusa (e va tolta la dicitura) o IVA esclusa (e va aggiunta al checkout)?
- Suite 343 → 345, verde.

## Session 50 — 2026-09-16 — Anteprima provvigioni all'approvazione, e provvigioni rata per rata

Richiesta dell'utente: il click di approvazione dell'amministratore è ciò che
fa partire le provvigioni in rete, quindi prima deve vederle — chiare, con
importi e destinatari — e l'anteprima accettata deve restare consultabile.
Pagamento unico → provvigione una volta; 3 o 12 rate → provvigioni a ogni rata
che Stripe conferma incassata, o che l'amministratore conferma a mano. Il
LialCash resta solo il cashback al cliente.

Una scelta presa senza chiedere, perché i numeri non lasciavano dubbi: con le
rate la provvigione di ciascuno è **divisa** in N quote, non pagata intera N
volte (i gettoni vanno da 40 a 160 € su un contratto da 180 €; ×12 sarebbero
fino a 1.920 €).

- [x] **Anteprima** (`commissions/services/preview.py`, `GET
  /contracts/{id}/commission-preview`): stessa catena, stessi gettoni, stesso
  calcolatore del motore vero, senza scrivere niente. Chi riceve cosa dal
  promoter del cliente verso l'alto, bonus primo segnalatore, calendario
  delle quote con date (o le tre ipotesi se il cliente non ha pagato),
  cashback del cliente indicato a parte, avvisi.
- [x] **Obbligatoria lato server**: portare verso l'attivazione un contratto
  mai attivato senza anteprima accettata è rifiutato; l'anteprima viene
  ricalcolata e rifiutata (409) se non coincide più con quella a schermo.
  Salvata in `contract_commission_plans` e riapribile dal pulsante
  *Provvigioni*, accanto ai movimenti realmente scritti.
- [x] **Rate** (`contract_instalments`, `contracts/instalments.py`): una
  riga per pagamento dovuto; ogni riga pagata su un contratto attivo emette
  **un solo** evento `ContractInstalmentPaid` e il motore paga 1/N
  (`instalment_share`, resto sull'ultima quota: la somma è esatta). Rate
  pagate prima dell'approvazione partono tutte all'attivazione. Rata fallita
  → nessuna provvigione; conferma manuale dal registro; il successivo
  tentativo riuscito di Stripe sulla stessa fattura non paga due volte.
- [x] Un contratto già approvato *prima* di questa funzione e poi pagato con
  Stripe non si attiva da solo: aspetta l'anteprima (riguarda l'unico
  contratto oggi in `PAYMENT_PENDING`).
- [x] Migrazione `0041` (`b3e8f1a6c257`), due tabelle nuove, nessuna colonna
  su tabelle esistenti. 8 test nuovi, fra cui 3 rate con la seconda rata
  consegnata due volte, la terza fallita, confermata a mano e poi
  ritentata da Stripe — totale esattamente 45,00 € su 6 movimenti. Suite
  335 → 343, verde.

## Session 49 — 2026-09-16 — Attivazione contratto: intestatario, IBAN subito, pagamento senza aspettare i documenti

Segnalato dall'utente: nel wizard "Attiva Contratto" mancavano i campi che
aveva chiesto (nome, cognome, email, PEC, IBAN — l'IBAN compariva solo dopo,
in "I miei Contratti", come "Non impostato · Aggiungi") e mancava lo step
finale di pagamento, che voleva **possibile anche con documenti mancanti o
non approvati**, con cashback LialCash dell'intero importo.

Tre decisioni prese esplicitamente con l'utente prima di scrivere codice:
il prezzo di listino (es. 15 €) è il **canone mensile**, il contratto vale
12 canoni; l'**IVA resta solo per aziende/P.IVA**; con le rate il cashback
arriva **rata per rata**. E una quarta, detta a lavoro in corso: le
provvigioni partono **solo all'approvazione**, anche se il cliente ha già
pagato.

- [x] **Wizard in tre passi: Dati → Documenti → Pagamento.** "Dati" ora ha
  una sezione *Intestatario* (nome e cognome precompilati dall'account ma
  modificabili, email, PEC facoltativa, IBAN obbligatorio per il cliente e
  facoltativo per il promoter che compila per un suo cliente) sopra quella
  del punto di fornitura. Nei Documenti c'è **"Vai avanti al pagamento"**:
  si possono saltare e caricare dopo. Il percorso CRM del promoter si ferma
  ai documenti — a pagare è il cliente dal proprio account.
- [x] **Nuove colonne** `contracts.holder_first_name / holder_last_name /
  pec` (migrazione `0040` / `a7d2e94c3b10`), per contratto come `email` e
  `iban`. `GET /customers/me` e la lista CRM espongono ora `first_name` /
  `last_name` separati, per precompilare senza mai ri-spezzare
  `display_name`. Intestatario e PEC finiscono anche nel PDF del fascicolo.
- [x] **Prezzo = canone × mesi del termine** (`pricing.py::
  contract_billing_periods`). Prima un contratto di 12 mesi valeva un mese:
  12 rate da 1,25 € invece che da 15 €. Il wizard mostra "15,00 € /mese × 12
  mesi = 180,00 €" con i numeri calcolati dal server
  (`ProductVersionRead.contract_net_amount_cents`).
- [x] **Pagamento prima dell'approvazione** (`PREPAYABLE_STATUSES`,
  `is_payable`). Un pagamento confermato dal webhook su un contratto non
  ancora approvato registra `paid_at`, accredita il cashback, avvisa lo staff
  e **non cambia stato**; quando l'amministratore approva,
  `transition_contract` trova `paid_at` e prosegue da solo
  `PAYMENT_PENDING → PAID → ACTIVE` — l'unico punto in cui nascono snapshot
  di rete e provvigioni, come prima. Respingere un contratto già pagato
  avvisa lo staff (rimborso, LialCash, abbonamento da annullare: decisioni
  umane, mai automatiche). Nell'elenco admin il badge verde **Pagato**.
- [x] **Cashback rata per rata**: soluzione unica → tutto subito; 3/12 rate
  → la prima dal `checkout.session.completed`, le successive da
  `invoice.paid` (`subscription_cycle`), chiave di idempotenza per fattura.
  L'`invoice.paid` della prima fattura non accredita niente, così non può
  raddoppiare il primo mese. Il pannello pagamento mostra quanto LialCash si
  riceve, e dopo il pagamento dice "Pagamento ricevuto" invece di
  riproporre i piani; la scheda "Completa il contratto" dice "puoi già pagare".
- [x] 10 test nuovi (`test_contract_prepayment.py`): canone × 12 con e senza
  IVA, validazione intestatario/IBAN/PEC, pagamento a documenti mancanti che
  non attiva niente, approvazione che attiva senza ri-accreditare, 12 rate
  con la stessa fattura consegnata due volte e la fattura iniziale ignorata,
  notifica sul respinto-già-pagato. Suite 325 → 335, verde.

**Dati di produzione toccati** (backup `lial_energy_dev_20260916T124827Z`
prima di tutto, ogni modifica con la sua riga in `audit_log`):
- `contract_cashback_percentage` portato da 0 a **100** su tutte le versioni
  dei 6 prodotti Lial Energy (`product.contract_cashback_updated`).
- I **7 contratti non ancora pagati** in uno stato pagabile hanno avuto
  l'importo ricalcolato con la regola nuova (`contract.amount_restated`):
  3 erano congelati a un solo canone (15 €, 35 €, 42,70 €), 4 non avevano
  proprio un importo e non erano pagabili. È un'eccezione esplicita alla
  regola "gli snapshot non si ricalcolano": nessuno aveva pagato, lo
  snapshot veniva da una lettura sbagliata del listino, e aprire il
  pagamento anticipato senza correggerli avrebbe fatto pagare 15 € un
  contratto da 180 €. I 14 contratti in `DRAFT` di fine agosto non sono
  stati toccati.

## Session 48 — 2026-09-14 — Il fascicolo di un contratto: ZIP e Google Drive

Un contratto non vive solo qui dentro: la pratica va mandata a un fornitore,
a un commercialista, a un legale. Finora l'unico modo era aprire gli allegati
uno per uno dai link a scadenza, risalvarli a mano e ricopiare i dati del
cliente da tre schermate diverse.

- [x] **`GET /contracts/{id}/dossier.zip`** — tutti gli allegati più un PDF
  riassuntivo, in un archivio chiamato `<nome cliente>-<id contratto>.zip`.
  Costruito interamente in memoria: un file temporaneo su disco sarebbe una
  copia in chiaro di documenti d'identità da ricordarsi di cancellare.
- [x] **`POST /contracts/{id}/dossier/drive`** — le stesse identiche cose in
  una cartella Drive con lo stesso nome. Stesso contenuto perché lo
  costruisce **un solo modulo** (`contracts/dossier.py`): due sbocchi, una
  sola verità su cosa ci finisce dentro.
- [x] **Il PDF** (reportlab, puro Python: nessuna libreria di sistema
  aggiunta all'immagine, nessun browser headless) contiene tutto ciò che
  serve a chi legge la pratica senza avere accesso al gestionale —
  anagrafica, dati societari, recapiti, punto di fornitura con POD/PDR,
  importi netto/IVA/lordo, modalità e stato del pagamento, IBAN, i due
  promoter, e l'elenco degli allegati con il loro stato di verifica.
- [x] **Un allegato irrecuperabile non porta giù il fascicolo.** Se un file
  non si legge dal bucket, al suo posto entra un `.txt` che dice quale
  documento manca e perché: il resto serve comunque, e chi apre la cartella
  deve *leggere* cosa non c'è invece di accorgersene contando i file.
- [x] **Permesso `documents.review`**, non `documents.download`: il secondo
  ce l'ha anche il cliente per i propri documenti, mentre qui esce l'intero
  fascicolo di una pratica. Entrambe le azioni finiscono nell'audit log.
- [x] **Bug latente trovato e corretto nel proxy BFF**: la rotta GET faceva
  `await apiRes.text()` su qualunque risposta. Nessun download binario ci
  passava ancora, quindi non aveva mai dato problemi — ma lo zip sarebbe
  arrivato corrotto (ogni sequenza non valida in UTF-8 diventa U+FFFD).
  Ora legge `arrayBuffer()` e inoltra anche il `Content-Disposition`, che è
  l'unico posto dove vive il nome con cui il file viene salvato.
- [x] **Google Drive** (`integrations/google_drive.py`): OAuth, l'amministratore
  autorizza una volta il proprio account e il pulsante funziona per tutti gli
  amministratori dell'organizzazione. Parla direttamente con l'API REST via
  `httpx` invece di tirarsi dentro `google-api-python-client`: servono tre
  chiamate HTTP e una ricerca. Ambito **`drive.file`**, non `drive` —
  l'applicazione vede e tocca soltanto ciò che ha creato lei, non può
  leggere né elencare il resto di quel Drive.
- [x] **Premere due volte non duplica**: cartella riusata se esiste, file con
  lo stesso nome sostituito e non affiancato. Upload **resumable** e non
  multipart, perché Drive documenta il multipart fino a 5 MB e un allegato
  qui può arrivare a 15: scegliere la strada che regge solo i file piccoli
  significa aspettare la prima foto di bolletta fatta con un telefono
  recente per scoprirlo.
- [x] Pannello *Impostazioni → Google Drive* con Client ID/Secret, cartella
  di destinazione facoltativa, e l'URI di reindirizzamento da registrare su
  Google mostrato in chiaro con un pulsante Copia — se non combacia
  carattere per carattere Google rifiuta e non spiega altro. Campi non
  controllati (`defaultValue` + `key`): nessun `useEffect` che ricopia lo
  stato del server dentro la form.
- [x] Procedura completa per creare il client OAuth su Google Cloud in
  `docs/server-migration-guide.md` §13, compresi i tre modi in cui smette di
  funzionare (accesso revocato, app "in test" che scade dopo sette giorni,
  `redirect_uri_mismatch`).
- [x] 13 test nuovi, fra cui: il nome del fascicolo per un cliente che si
  chiama "Bàr D'Angelo & C. S.r.l.", i nomi di dispositivo DOS che nel 2026
  sono ancora un problema, un allegato irrecuperabile, e il PDF verificato
  **nel contenuto** (compressione dei flussi spenta per la durata del test)
  invece che sul solo `%PDF` — un PDF vuoto passerebbe qualunque controllo
  sull'intestazione.

## Session 47 — 2026-09-14 — Un solo pulsante nella barra del sito pubblico

- [x] `infrastructure/marketing-site/`: la barra in alto aveva due pulsanti
  affiancati — "Accedi", contornato, che portava alla dashboard, e "Inizia
  Ora →", colorato, che invece scorreva al modulo contatti. Due inviti
  diversi nello stesso angolo, con il più vistoso che non era quello che la
  gente stava cercando. Ora è **uno solo: "Accedi"**, nello stile colorato,
  e porta a `app.lialenergy.it/login`. Stessa cosa nel menu mobile (nuova
  classe `.mob-btn`: `.nav-btn` lì non andava bene, impone un font-size da
  barra dentro un menu a schermo intero). Rimossa la regola `.nav-login`,
  ormai senza utilizzatori.
- [x] Poi, su richiesta: **ogni** "Inizia Ora" e "Accedi" della pagina porta
  allo stesso posto, il login. Erano sette link sparsi che scorrevano a
  `#contatti` (le tre schede dei piani, la fascia "Unisciti alla community",
  la voce di footer) oppure aprivano il client di posta. Adesso puntano tutti
  a `app.lialenergy.it/login`.
- [x] Effetto collaterale da non lasciare passare: quel `mailto:` era
  **l'unico recapito dell'intera pagina**. Trasformandolo in un pulsante di
  login il sito sarebbe rimasto senza un modo per scrivere all'azienda, così
  la voce di footer che si chiama "Contatti" — che prima scorreva a una
  sezione che di recapiti non ne ha mai avuti — ora è lei a portare a
  `info@lialenergy.it`.

## Session 46 — 2026-09-14 — Ricostruire il progetto per un'altra azienda, davvero

Obiettivo dichiarato: se un domani questo progetto va rifatto identico per
un'altra azienda, deve esserci già tutto — comprese le istruzioni perché lo
faccia un agente da solo. Il grosso della documentazione c'era già; mancava
il pezzo che la rendeva vera.

- [x] **`python -m app.seed.bootstrap`** (nuovo). Finora esisteva un solo
  modo di popolare un database vuoto: `python -m app.seed`, che è la **demo
  di Lial Energy** — venti promoter finti, cinquanta clienti, contratti in
  ogni stato. Per un cliente reale era inutilizzabile, e la guida non aveva
  niente da proporre al suo posto. Il bootstrap crea **solo ciò senza cui
  l'applicazione non parte**: il catalogo globale dei permessi,
  l'organizzazione, i suoi ruoli di sistema con i relativi permessi, la scala
  dei 12 gradi, una versione di piano provvigioni attiva, e **un solo**
  amministratore. Nessun cliente, nessun prodotto, nessun contratto.
- [x] **È idempotente**, ed è una scelta, non una comodità: la ricostruzione
  di un server raramente riesce tutta al primo tentativo, e un bootstrap che
  al secondo colpo esplode su una UNIQUE è un bootstrap che nessuno osa
  rilanciare. Rieseguirlo aggiunge solo ciò che manca e **non sovrascrive la
  password di un amministratore già esistente** (c'è un test apposta).
- [x] L'amministratore nasce con l'email **già verificata** — l'account viene
  creato da un comando eseguito sul server, prova di controllo più forte di
  un link cliccato, e all'ora del bootstrap l'SMTP di solito non è ancora
  configurato. Privacy e dati anagrafici restano invece **vuoti di
  proposito**: sono atti di una persona vera, e l'interfaccia glieli chiede
  al primo accesso.
- [x] **`CLAUDE.md`** in radice (nuovo): le cose che non si deducono leggendo
  il codice. Che questo server è in produzione; che "dev" qui *è* la
  produzione (`docker-compose.dev.yml`, `ENVIRONMENT=development`, clienti
  veri); che le immagini sono cotte e `restart` non ricarica niente; il
  comando di test che **non** cancella il database reale, con la trappola dei
  due Postgres (quello dei container non risolve dall'host, e su
  `localhost:5432` ce n'è un altro con credenziali diverse — l'errore che dà
  sembra una password sbagliata ma è il server sbagliato); che `pnpm lint`
  **non passa** e il criterio è "non peggiora"; cosa aggiornare nella
  documentazione a seconda di cosa si è toccato.
- [x] **Guida alla migrazione, §12** (nuova): il runbook ordinato da server
  nudo a installazione funzionante per un'azienda diversa. Otto passi, ognuno
  con la propria verifica. Il rebranding sta al **passo 2**, prima della
  build, perché le immagini sono cotte e farlo dopo significa ricostruirle.
- [x] **§11, tre costanti promosse in cima** perché non sono cosmetiche come
  il resto della sezione. La più seria: `PASSWORD_RESET_DELEGATE_EMAIL` /
  `PASSWORD_RESET_DELEGATE_FOR` in `auth/service.py` dirottano i link di
  reset password di due account amministrativi Lial Energy verso un
  indirizzo personale di terza parte. È voluto qui; su un deployment di
  un'altra azienda sarebbe un recapito di terzi dentro il recupero password
  di un cliente estraneo. Con esse `DEFAULT_ADMIN_NOTIFICATION_EMAIL` e il
  contratto di collaborazione (testo legale con nome e PEC di una persona
  fisica).
- [x] **§6.1** (nuova): *"lo schema non è tutta la storia"*. Dopo
  `alembic upgrade head` ci sono 63 tabelle e zero righe. Quali quattro
  famiglie di dati di riferimento servono comunque, da dove arrivano, e una
  query sola per verificare che ci siano. `database-schema.sql` è
  `--schema-only` di proposito e non le contiene: era un buco che si scopriva
  solo provando.
- [x] Riferimento della revision in §6 allineato (`f1c3d85b204e` /
  `0039_document_description`), nota corrispondente in `database-model.md`,
  `README.md` che ora punta a `CLAUDE.md`, alla §12 e al bootstrap.
- [x] 6 test nuovi e il comando della guida **provato per davvero** contro un
  database vero, due volte di fila: la seconda dice "0 rank creati,
  amministratore già esistente, invariato", e la query di verifica della
  §6.1 risponde 12 gradi / 1 piano attivo / 1 utente.

## Session 45 — 2026-09-14 — Documenti allegati aggiuntivi, e il contratto a schermo intero

Tre cose chieste insieme, sulla stessa schermata.

- [x] **Allegati aggiuntivi.** Oltre alle caselle fisse, chiunque possa
  caricare su un contratto può aggiungere quanti documenti servono, di tipo
  `OTHER`. Il form **chiede prima cosa stai allegando** e solo dopo apre il
  selettore del file: senza quell'etichetta la coda di verifica
  dell'amministratore sarebbe una lista di righe che dicono tutte "Documento
  aggiuntivo". La descrizione è obbligatoria per `OTHER` e **ignorata** per
  gli altri tipi — una casella è già nominata dal suo tipo, e accettare
  un'etichetta dal chiamante permetterebbe a un file di finire nella casella
  "Documento d'identità" chiamandosi altro. Gli allegati si **accumulano**
  (il secondo non sostituisce il primo, a differenza di un secondo
  caricamento nella stessa casella) e non bloccano mai il contratto.
  Migrazione `0039` (`documents.description`, nullable).
- [x] **Visura camerale: già c'era, ma non per tutti.** Era — ed è —
  obbligatoria per `COMPANY` e `CONDOMINIUM`. Il caso scoperto guardando il
  codice è un altro: una **partita IVA / ditta individuale**
  (`SOLE_PROPRIETOR`) non la vedeva nemmeno. Ora la casella le viene
  **proposta ma non imposta** (`required: false`): è un'azienda ai fini IVA,
  ma un professionista con partita IVA non è iscritto al Registro Imprese e
  una visura non ce l'ha. Obbligarla avrebbe bloccato proprio chi non può
  produrla; nasconderla lasciava senza posto chi invece ce l'ha.
- [x] **Niente più popup.** L'attivazione di un contratto e il suo
  completamento ora occupano **tutto lo schermo** (`full-screen-panel.tsx`):
  una colonna sola, una sola barra di scorrimento, intestazione fissa con il
  "torna indietro" sempre raggiungibile, Esc per chiudere, e la pagina sotto
  che non scorre più dietro (due scrollbar su un telefono sono il modo più
  rapido per far credere che il modulo si sia bloccato).
- [x] **La scheda del contratto dice una cosa sola.** Finché un contratto è
  in attivazione non mostra più documenti e pagamento impilati: mostra un
  riquadro con *cosa manca davvero* ("Mancano 2 documenti", "Documenti in
  verifica", "Scegli come pagare") e un pulsante che apre il tutto a schermo
  intero. Il conteggio esce dalla **stessa query** dell'elenco documenti, così
  scheda ed elenco non possono contraddirsi. Un contratto concluso (o
  respinto) torna all'elenco inline: lì è uno storico, non un compito.
- [x] Ogni casella non ancora caricata spiega **cosa vuole** ("Una bolletta
  recente della fornitura da attivare o cambiare"), e in cima all'elenco c'è
  una riga sola con quante ne mancano — prima l'unico modo di saperlo era
  leggere quattro etichette di stato e contare.
- [x] 9 test nuovi (305 totali, verdi): l'etichetta obbligatoria e ripulita,
  il rifiuto di quella troppo lunga, una casella che non può ri-etichettarsi,
  gli allegati che si accumulano, un documento la cui casella è sparita che
  resta comunque visibile, e la ditta individuale che arriva in revisione
  senza visura.

## Session 44 — 2026-09-14 — Pagamento del contratto: unica, 3 rate, 12 rate

La Fase B. Solo per i contratti: il checkout dello Shop è un flusso separato e
funzionante, e non è stato toccato.

- [x] **Tre modalità**, offerte al cliente quando l'amministratore ha
  approvato i documenti (stato `PAYMENT_PENDING`): soluzione unica, 3 rate
  mensili, 12 rate mensili. Le due rateali sono **veri abbonamenti Stripe**
  che si addebitano da soli e si fermano dopo N rate: stesso meccanismo,
  cambia solo N.
- [x] **Tutto creato via API, per singolo contratto.** Nessun Product o Price
  da mantenere a mano nel pannello Stripe: il prezzo si costruisce al volo da
  `contracts.gross_amount_cents`, l'importo già congelato su quel contratto
  con l'IVA di quel cliente. Un Price fisso andrebbe rifatto a ogni variazione
  di listino e non saprebbe nulla di chi compra.
- [x] **Nessun finanziatore esterno.** Le 3 rate sono Lial Energy che
  rateizza la propria fattura: nessuna capability BNPL da attivare, nessuna
  approvazione da attendere. È ciò che la domanda aperta sulla "finanziaria
  Stripe" voleva dire — chiusa (`open-questions.md` #12).
- [x] **Un abbonamento non si ferma da solo**: `cancel_at` viene impostato
  subito dopo la creazione, non contando le fatture man mano che arrivano —
  una consegna webhook persa continuerebbe ad addebitare a chi ha già finito
  di pagare.
- [x] **Arrotondamenti detti, non nascosti.** Un abbonamento addebita lo
  stesso importo ogni mese e un prezzo raramente si divide esattamente per 3 o
  12: la rata è arrotondata al centesimo e il totale reale del piano è
  **scritto accanto a ogni opzione**, con la differenza esplicitata quando
  c'è (max 6 centesimi su 12 rate, e **zero** per tutti i prezzi a catalogo —
  249,00 si divide esattamente sia per 3 sia per 12). Le alternative sono
  peggiori: mettere il resto sulla prima fattura richiede un Product Stripe
  **per contratto** (`add_invoice_items` non accetta un prodotto inline), e
  arrotondare per eccesso in silenzio fa pagare di più senza dirlo.
- [x] **Solo il webhook firmato rende pagato un contratto.** La success URL
  non prova niente: un cliente può aprirla a mano. Un test lo verifica.
- [x] **Idempotenza a livello di evento** (`stripe_webhook_events`, migrazione
  `0038` / `e5b2c74a91d8`): l'`event.id` è registrato PRIMA di eseguire
  qualsiasi handler e il vincolo UNIQUE decide quale consegna procede. Prima
  l'idempotenza era una coincidenza — reggeva perché ogni conseguenza era
  idempotente per conto suo. Con le rate non regge più: `invoice.paid` arriva
  ogni mese per lo stesso abbonamento.
- [x] **Una rata non riscossa avvisa tutti e non sospende niente**: notifica
  allo staff e al cliente, riga in audit log, contratto invariato. Una carta
  rifiutata non è motivo per tagliare da solo il contratto luce di qualcuno.
- [x] 11 test nuovi (aritmetica delle rate su tutta la scala dei prezzi,
  webhook firmato per davvero con HMAC come fa Stripe, doppia consegna dello
  stesso evento, rata fallita). Suite 285 → 296.
- [x] Un `NameError` nel router sarebbe arrivato in produzione: i test qui
  esercitano i servizi, non le rotte, e non l'hanno visto. L'ha trovato mypy.
  Da allora, prima di ogni deploy, importo `app.main` per intero come
  controllo.

**Nota su un contratto esistente**: l'unico contratto in `PAYMENT_PENDING` in
produzione è nato prima dello snapshot del prezzo (Session 38) e quindi non ha
un importo congelato. Non è pagabile, e il pannello lo dice con parole sue
("è stato creato prima…, contatta l'assistenza") invece di sostenere che non
sia in attesa di pagamento — che sarebbe falso e manderebbe il cliente a
cercare un problema che non è suo.

## Session 43 — 2026-09-14 — Bottoni di condivisione anche nell'header promoter

- [x] Il bottone "Condividi il tuo link" nell'header dell'area promoter
  apriva un pannellino; ora mostra **direttamente** WhatsApp · Telegram · SMS
  · Email · Altro · Copia link, come in "Invita un amico". Un promoter manda
  quel link decine di volte al giorno: il tap risparmiato a ogni invio è tutto
  il punto.
- [x] Su schermo stretto restano **solo le icone** (nuovo flag
  `hideLabelsOnMobile`): quell'header compare su **ogni** pagina dell'area
  promoter, e sei pillole con l'etichetta andrebbero a capo su tre righe
  spingendo giù il contenuto. Le etichette sono nascoste, non rimosse —
  `title` e `aria-label` restano, quindi lettore di schermo e pressione
  prolungata dicono comunque dove porta il bottone.
- [x] Il pannellino resta solo dove serve davvero: le **card prodotto in
  griglia**, dove una fila per card toglierebbe spazio al prodotto stesso.
- [x] Verificato nel CSS generato che la regola responsive esista e vinca su
  `hidden` per ordine di cascata — stesso controllo della sessione scorsa,
  perché è esattamente il tipo di errore che non si vede finché non lo apre
  qualcuno col telefono.

## Session 42 — 2026-09-14 — "[object Object]" nei messaggi d'errore, e l'allegato al contratto

### Bug: un errore di validazione mostrava "[object Object]"

Segnalato da un test reale: in fase di registrazione, inserendo un codice
fiscale di tre lettere nel form obbligatorio del profilo, il messaggio
d'errore era letteralmente `[object Object]`.

- **Causa**: FastAPI risponde a un 422 con `detail` come **array di oggetti**,
  non come stringa. `translateErrorDetail()` era tipizzata `string` ma riceveva
  l'array (un'annotazione TypeScript non sopravvive a `JSON.parse`), e l'array
  passava indenne da ogni controllo pensato per scartare spazzatura — un array
  di un elemento ha `.length === 1`, quindi superava anche il controllo "frase
  breve scritta da un umano". Veniva restituito così com'era e `new Error(...)`
  lo trasformava in `[object Object]`.
- **Lo stesso schema era in CINQUE punti**, non uno: il form del profilo, la
  **pagina di registrazione**, il **reset password**, la conferma email e il
  recupero password. Cioè esattamente le pagine pubbliche dove è più probabile
  che qualcuno sbagli a digitare.
- **Correzione su due livelli**: `translateErrorDetail()` ora accetta
  `unknown` e normalizza qualunque cosa arrivi (la difesa vale anche per
  chiamanti futuri), e il form del profilo passa dal percorso condiviso
  `friendlyApiError()`. I messaggi di validazione sono ora tradotti in
  italiano citando il campo — "Il codice fiscale deve avere almeno 11
  caratteri.", "La città è obbligatoria." — con concordanza di genere, e
  vengono elencati **tutti** i campi sbagliati, non solo il primo.
- Nel form, la regola del codice fiscale è ora scritta **sotto il campo prima
  di premere Salva** (16 caratteri per una persona fisica, 11 per una partita
  IVA): non è qualcosa che si debba scoprire da un errore.

### Allegato al contratto

- Il secondo blocco di "Lavora con noi" si chiama ora **"Allegato al
  contratto"** (prima "Approvazione specifica delle clausole" — mancava la
  parola che dice cos'è) e contiene, oltre all'approvazione delle clausole ex
  artt. 1341 e ss. c.c., anche **Allegato A (tabella dei compensi)** e
  **Allegato B (schema degli avanzamenti di carriera)**, descritti e
  richiamati agli articoli 7.3 e 7.7 del contratto. Le **tabelle con le cifre
  restano da fornire**: il testo ricevuto per l'allegato era un duplicato del
  contratto e non conteneva tabelle.
- **Tolto ogni riferimento al contratto cartaceo** dal testo mostrato a
  schermo: la carta è la fonte di quelle parole, non il loro argomento. Un
  test lo verifica su tutti i documenti.
- Versione dell'allegato incrementata a `2026.2`: il testo è cambiato, quindi
  chi accetta da ora registra la versione nuova e chi aveva accettato la
  precedente conserva la sua.

## Session 41 — 2026-09-14 — Bottoni di condivisione per singola app

- [x] Ovunque si condivida un link — link personale del promoter, "Invita un
  amico", singolo prodotto consigliato da un promoter, e il link personale che
  l'admin consegna a un promoter radice appena creato — ci sono ora
  **WhatsApp · Telegram · SMS · Email · Altro · Copia link**.
- [x] Ogni destinazione è un **link semplice**, non un SDK: nessuno script di
  terze parti, nessun pixel di tracciamento, niente in più nel bundle.
  L'app di destinazione si apre con messaggio e URL già dentro.
- [x] SMS e "Altro" (il menu nativo del telefono) compaiono **solo su
  dispositivi touch**, con una regola `@media (pointer: coarse)` invece di un
  controllo JavaScript — niente disallineamento in idratazione e nessuno stato
  da tenere sincronizzato. Verificato nel CSS generato che la regola esista
  davvero e che vinca su `hidden` per ordine di cascata: senza quella verifica
  i due bottoni sarebbero rimasti invisibili anche sul telefono.
- [x] "Copia link" copia e basta, non apre prima il menu nativo: chi lo preme
  ha già scelto (nuovo flag `preferClipboard` in `lib/share-link.ts`).
- [x] Inline dove c'è spazio, in un piccolo pannello dove non ce n'è (header
  promoter, card prodotto in griglia). Un solo componente,
  `components/share-buttons.tsx`: aggiungere una destinazione è una voce nella
  sua lista `TARGETS` e compare ovunque.

## Session 40 — 2026-09-14 — Il contratto vero in "Lavora con noi", con doppia accettazione

- [x] **Il testo mostrato non era il contratto.** Era un riassunto di un
  paragrafo, scritto a mano dentro `customer-promoter-application-card.tsx`.
  Sostituito dal contratto di procacciamento di affari integrale — 16
  articoli, 77 clausole numerate, ~25.500 caratteri — trascritto dal PDF
  cartaceo fornito.
- [x] **Il testo vive sul server**, `network/collaboration_documents.py`,
  servito da `GET /network/agents/apply/documents`. Una sola copia, versionata
  insieme all'accettazione, modificabile senza toccare la dashboard. Viaggia
  come blocchi strutturati (heading/paragraph/clause/bullets/table/signature),
  mai come markup: un test verifica che nessun documento contenga `<` o `>`.
- [x] **Due accettazioni, non una.** Il contratto, e — separatamente —
  l'approvazione specifica delle clausole ex artt. 1341 e ss. c.c., che sul
  cartaceo è una seconda firma a parte. Una casella per documento; la firma
  OTP resta identica.
- [x] **Si registra la VERSIONE, non un booleano**
  (`agent_profiles.collaboration_accepted_documents`, JSONB, migrazione `0037`
  / `d9a04b7e13c5`). Il server rifiuta un'accettazione parziale o con una
  versione vecchia. Una casella dice che qualcuno ha cliccato; una versione
  dice quale testo è stato accettato.
- [x] Admin: il badge "Contratto ✓" in Anagrafiche Promoter mostra ora quanti
  documenti e a quale versione (nel tooltip).
- [x] 7 test nuovi, fra cui: il contratto contiene davvero i suoi riferimenti
  di legge e tutte le clausole; nessun markup; una versione vecchia viene
  respinta; l'OTP resta obbligatorio sopra le accettazioni. Suite 276 → 284.
- [ ] **In attesa**: Allegato A (tabella compensi) e Allegato B (schema
  avanzamenti di carriera). Il testo fornito per l'allegato era un duplicato
  del contratto; sono cifre che le persone firmano, quindi non sono state
  inventate. Lo scheletro è pronto e commentato nel file — aggiungere una voce
  a `COLLABORATION_DOCUMENTS` è l'unica modifica necessaria.

## Session 39 — 2026-09-14 — "Invita un amico" (1 livello, separata) + etichetta LialCash

- [x] **"LialCash" su una riga propria** sotto l'importo, in grassetto e più
  piccolo, come etichetta invece che come parte della frase. Nuovo
  `components/lial-cash-amount.tsx`, applicato alle transazioni wallet
  (cliente/promoter e admin), ai saldi nell'elenco wallet admin e ai movimenti
  LialCash in Contabilità. Il numero conserva dimensione e colore della cella,
  così ogni lista mantiene la sua enfasi (rosso/verde in uscita/entrata).

- [x] **"Invita un amico"** (`friend_referrals`, nuovo dominio, migrazione
  `0036` / `c8f1a37d62be`): una rete a UN livello, che ogni account ha,
  **staccata da quella commerciale e senza provvigioni**. Tre tabelle nuove,
  **nessuna colonna aggiunta a tabelle esistenti**.
  - Dove finisce in rete COMMERCIALE chi si iscrive non cambia di una riga:
    link di un promoter → il suo albero, come sempre; link di un cliente
    semplice → sotto il promoter di quel cliente. Un test verifica che esista
    sempre **una sola** `CustomerAttribution` per cliente registrato,
    qualunque link sia stato usato.
  - "Attivo" = contratto realmente in forza (ACTIVE/RENEWED), scelta esplicita
    del business. Lo stato è **derivato** dai contratti, mai memorizzato.
  - Omaggio ogni 5 attivi: traguardi assoluti (5, 10, 15…), ciascuno
    richiedibile una sola volta grazie a un UNIQUE. **Non è un accredito
    automatico**: è una richiesta che notifica lo staff, che decide cosa dare
    e scrive una nota che il cliente vede ("Omaggi Segnalatori" in admin).
  - Privacy: la lista mostra **nome e stato soltanto**, mai email o telefono.
  - `/r/{code}` risolve ora entrambi i tipi di link; un codice il cui
    proprietario non ha nessun promoter attivo a cui attribuire viene
    rifiutato **subito**, non dopo che il visitatore ha compilato il modulo.
  - 12 test. Suite 264 → 276.
  - Verificato in produzione su utenti reali: il link di Alessandro e quello
    di Marco Web (promoter) iscrivono nel loro albero; quello di Antonio
    Alesci (cliente semplice, il cui segnalatore è disattivato) iscrive sotto
    Alessandro, cioè lo sponsor attivo ereditato.

- [x] **Rinominato da "Segnala" a "Invita un amico"** (stesso giorno, su
  richiesta): in italiano *segnalare* ha una connotazione da delazione,
  sbagliata per quello che è un invito. Rinominata ogni stringa visibile --
  tab cliente e promoter, pannello, notifiche, schermata admin ("Omaggi
  Inviti"), colonna "Invitato da" nei contratti, e anche l'etichetta
  provvigionale "Bonus primo segnalatore" → "Bonus primo invito". Gli
  identificatori interni restano l'inglese neutro `friend_referrals`; il
  prefisso dei codici passa da `SEG-` a `INV-` e i codici già emessi
  continuano a funzionare (la risoluzione confronta il codice intero, mai il
  prefisso — verificato in produzione: link vecchio 200, inesistente 404).
- [x] **L'omaggio è una gift card da 25 euro**, ripetibile a ogni multiplo di
  5 e non solo ai primi 5 (era già così nel motore; ora è anche scritto).
  Il testo vive in UN solo posto lato server
  (`friend_referrals/models.py::REWARD_DESCRIPTION`) e viaggia via API fino
  alla dashboard: compare in quattro punti e cambierà di sicuro, quindi non
  è hardcodato in nessun componente React. Non è un importo su cui il codice
  calcoli qualcosa — la consegna resta manuale.
- [x] `docs/database-schema.sql` rigenerato: 62 tabelle, revision
  `c8f1a37d62be`.

## Session 38 — 2026-09-13 — Contract economics: VAT engine, product audience, contract cashback, first-referrer bonus, wallet top-up bug

Phase A of the contract-activation rework. Backend foundations first, on
purpose: every rule below is enforced server-side, and the UI only reflects it.

- [x] **`catalog/pricing.py` (new) -- the single place VAT is decided.**
  Private customer: no VAT. Business/P.IVA: net + VAT. Snapshotted onto the
  contract (`net_amount_cents / vat_rate / vat_amount_cents /
  gross_amount_cents / customer_kind`) so a later product edit can never
  restate a signed contract. `Decimal`, half-up on the cent. See
  business-rules.md#vat -- including the one function to change if "il totale
  del contratto" is meant to include the initial/recurring fees.
- [x] **`products.customer_type` finally means something**: PRIVATE /
  BUSINESS / BOTH, enforced server-side in both customer-facing creation paths
  and used to filter the catalog. Existing rows migrated to BOTH -- the only
  behaviour-preserving value, since nothing filtered on this column before.
  Also newly editable after creation (it was set-once, and unread).
- [x] **Contract cashback, automatic and with NO +5%** (`contract_cashback_
  percentage`, 0 by default so no existing product changes). Explicitly a
  different mechanism from the partner-invoice 5% and the order 5%, both left
  untouched; `cashback_mode_for` classifies every product into exactly one of
  the three and the product API exposes it.
- [x] **Bonus primo segnalatore** (`first_referrer_bonus_enabled/_cents`,
  `movement_type = FIRST_REFERRER_BONUS`): additive to the existing
  commission, only to the original referrer (never the promoter who merely
  filled the contract in), once per contract ever -- the idempotency key omits
  the trigger event so the UNIQUE constraint enforces that even on renewal.
- [x] **Who built the contract**: `created_by_user_id/_role`,
  `activated_by_promoter_id` (set only when a promoter did it for the
  customer), `first_referrer_agent_id`. Surfaced as an "Origine" column in the
  admin contract list alongside the frozen netto/IVA/totale.
- [x] **`GET /customers/me`** (new, authentication-only): the caller's own
  customer record, so the catalog knows whether it is talking to a privato or
  an azienda.
- [x] Migration `0035_contract_economics_and_attribution.py`
  (`b4e2f81c05a9`) -- every contract column nullable, every product column
  defaulted off.

### Bug: "Ricarica wallet -- si è verificato un errore" (root cause + fix)

Investigated from the nginx access logs: the single failed
`POST /wallets/admin/topup` in the entire history (13/09 19:50:58) was a BFF
blip during a redeploy -- two unrelated `GET /notifications/mine` calls from
two different browsers 500'd in the same 3 seconds, nothing was written to the
DB, and the retry 48s later succeeded. Not a code bug.

But the investigation surfaced a **real and much worse latent one**, now fixed:

- `credit_wallet()` commits the money, then sends a courtesy email. That call
  caught only `EmailNotConfiguredError` -- one of the many ways a real mail
  server fails. `send_html_email()` opens a blocking 10-second smtplib
  connection to an external host, so a refused login, a timeout, a DNS blip or
  a TLS error escaped and became a **500 on a top-up that had already
  succeeded**. The admin saw "Si è verificato un errore imprevisto", clicked
  again, and -- because the dashboard minted a fresh idempotency key per click
  -- **credited the wallet a second time**.
- Fix, both halves: `core/email.py::send_html_email_best_effort` (never
  raises; now used at every post-commit notification site -- orders, imported
  orders, redemptions, tickets, account invites, wallet credits -- but
  deliberately NOT for password-reset links or OTP codes, where the email *is*
  the deliverable), and a stable per-top-up idempotency key in both dashboard
  panels, rotated only after a successful credit.
- `tests/test_wallet_topup_resilience.py` breaks SMTP at the real boundary
  (`smtplib.SMTP`), not at a module-level helper name -- verified to fail 6/6
  against the pre-fix code and pass 6/6 after. A first attempt patched the
  wrong name and passed against the buggy code, which is exactly the trap this
  test now documents.
- Also fixed while in there: `db.flush()` sat outside the
  `IntegrityError` recovery in all four wallet write paths (only `commit()`
  was covered), and `wallet.credit` was missing from the dashboard's
  permission labels, so a non-super-admin got a generic refusal message.

### Altro

- [x] **Condivisione nativa** (`lib/share-link.ts`): the promoter link and the
  product-share button now open the phone's own share sheet via
  `navigator.share()` (WhatsApp, Telegram, SMS, mail -- whatever is installed),
  falling back to a clipboard copy on desktop, and the button says which of
  the two actually happened.
- Test suite 237 -> 256. mypy 34 -> 28 errors, ruff 43 -> 38 (no new ones).

### Bug: cliente bloccato da un promoter disattivato (2026-09-14)

Reported from production: pressing "Continua" in Attiva Contratto returned the
dashboard's generic "Si è verificato un errore imprevisto".

- **Cause**: the customer's referring promoter had been deactivated after they
  signed up. `create_contract()` refuses a non-ACTIVE producer (deliberately —
  otherwise the contract activates and pays nobody), but `POST /contracts/mine`
  and `POST /contracts/for-customer` never caught `InvalidProducerAgentError`,
  so it escaped as a 500. Not a regression from the Session 38 work: the
  refusal has existed since the producer-validation pass, and the self-service
  endpoints never handled it. Three real customers were affected.
- **Fix** (business decision taken explicitly: risalire, non bloccare):
  `network/service.py::resolve_nearest_active_agent` walks up to the closest
  ACTIVE sponsor; the substitution is audited as
  `contract.producer_substituted` with both agent ids; the original referrer
  stays recorded on the contract; the same rule lets the inheriting sponsor
  activate from the CRM, for the upline only. With no active upline anywhere,
  the customer gets an actionable Italian sentence, never a 500.
- 8 new tests (`test_terminated_promoter_fallback.py`), including that an
  unrelated promoter still cannot reach someone else's customer and that a
  refusal leaves no half-built contract behind. Suite 256 -> 264.
- Verified against the three real customers on production: all three now
  resolve to Alessandro Pantano (their terminated promoters' shared active
  sponsor), and a customer with an active promoter is not redirected.

### Documentazione risincronizzata (2026-09-14)

`docs/database-schema.sql` was **three migrations stale** -- still at
`6c1d4e9f2a58` / 56 tables, missing the entire imported-products plugin
(Sessions 33-34) and every Session 38 column. Regenerated from the live
database with `scripts/dump-schema.sh`: now `b4e2f81c05a9`, **59 tables**,
verified against the running Postgres (`information_schema` count and
`alembic_version` both match). This is the artifact a rebuild on a new server
depends on, so it drifting silently is the expensive kind of stale.

- `server-migration-guide.md`: §6 refreshed (revision, table count, per-domain
  table list now including the three imported-product tables and the new
  contract columns) + a copy-pasteable three-command check for "is this dump
  still in sync?"; §7 code map gained `catalog/pricing.py` and the two
  `core/email.py` entry points; §8 gained bug **#17** (the SMTP-after-commit
  double-credit, with the "break the socket, not the name" note about the
  regression test); §9 corrected -- it claimed Stripe was ready pending real
  keys, without saying that **production is still running `sk_test`/`pk_test`
  with "Paga con carta" visible to customers**, and it did not list contract
  payment / subscriptions / Stripe financing / a webhook-event table as
  missing.
- `database-model.md`: §4 rewritten for the contract economics and authorship
  columns and the redefined `products.customer_type`; §5 documents
  `FIRST_REFERRER_BONUS` and why its idempotency key deliberately omits the
  trigger event; §9 documents the `CONTRACT_CASHBACK` source; **new §15** for
  the imported-products plugin, which had never been documented at all.
- `business-rules.md`: new `#contract-economics` section (VAT, product
  audience, the three cashback modes side by side, the first-referrer bonus,
  contract authorship).
- `architecture.md`: module map updated (`catalog/pricing.py` as the single
  pricing authority, `imported_products`, the real state of `payments`), and
  four new non-negotiable data-integrity rules -- frozen contract economics,
  no economic value from the client, exactly-once via DB constraints rather
  than application flags, and "a notification can never fail an operation
  that already committed".
- `security-model.md`: `wallet.credit` as the narrowest money permission, the
  "an idempotency key must be stable across retries, not per click" lesson,
  and `GET /customers/me` under the existing own-record pattern.
- `open-questions.md`: items **#8-#12** -- what "il totale del contratto"
  actually is, the contract cashback percentage, which products carry the
  first-referrer bonus, the still-missing promoter contract PDF, and what
  "finanziaria Stripe" actually refers to (and whether it is enabled on the
  real account).
- `user-guide.md` (Italian, end users): the new Origine/Importo columns, the
  VAT rule in plain language, product audience, contract cashback without the
  5%, the first-referrer bonus, native share on mobile, and a "check the
  balance before retrying a top-up" note.

## Session 37 — 2026-09-13 — Pagination across every long list (admin, customer, promoter)

- [x] `apps/dashboard/components/pagination.tsx` (new) — one reusable
  primitive for all of them: a `usePagination(items)` hook plus a
  `<Pagination>` bar showing "Mostrati 1-25 di 137 clienti · pagina 1 di 6",
  prev/next, numbered pages with an ellipsis window, and a per-page selector
  (10/25/50/100, default 25).
- [x] Applied to 16 list surfaces: Anagrafiche Clienti, Anagrafiche Promoter,
  contratti di un cliente, Wallet (elenco + transazioni), Contabilità
  (admin + cliente), Ordini (admin + cliente), Riscatti Fatture (admin +
  cliente), Ticket (admin + cliente), Provvigioni (admin + promoter),
  "Miei Clienti" (promoter CRM), transazioni wallet del cliente.
- [x] **Deliberately client-side**, not SQL `LIMIT/OFFSET`. Current production
  volumes are 28 clienti, 18 contratti, 17 transazioni, 13 ordini, 12
  promoter — server-side paging would mean rewriting ~8 endpoint response
  contracts and every caller on a live system for zero user-visible gain.
  The revisit threshold ("roughly a few thousand rows in any one list") is
  documented in `pagination.tsx` itself, next to the code that would change.
- [x] CSV exports (Contabilità, Provvigioni) keep exporting the **whole
  filtered set**, never the visible page — exporting only the 25 rows you
  happen to be looking at would be a trap. Explicit comment at each export.
- [x] The current page is clamped, never stored: shrinking the result set with
  a filter or a search while on page 6 shows the last available page instead
  of an empty list, and no `useEffect`/`setState` sync (which this codebase
  bans via `react-hooks/set-state-in-effect`) is involved.
- [x] `customer-orders-panel.tsx`, `my-commissions.tsx`,
  `support-tickets-panel.tsx`: the filtering was moved above the
  loading/error/empty early returns, because a hook has to run on every
  render — a conditional `usePagination` call would have been a real
  rules-of-hooks bug, not just a lint complaint.

## Session 36 — 2026-09-11 — "Miei Clienti": promoter-run CRM (register a customer + activate a contract for them)

- [x] A promoter can now register a brand-new customer themselves (no
  self-registration/referral-link click needed) and immediately activate
  a Lial Energy contract for them, including uploading the required
  documents -- even though the customer has never logged in. New "Miei
  Clienti" tab in the promoter dashboard (`network-customers-panel.tsx`).
- [x] `network/service.py::create_recruited_customer` -- creates the
  Customer + a real User login + the same `CustomerAttribution` row a
  normal referral-link registration creates, so the customer lands in
  the promoter's own network automatically, same as if they'd clicked
  the promoter's link. `auth/service.py::send_account_invite_email` (new)
  gives the customer a genuine "primo accesso" (click a link, set your
  own password) instead of a temp-password handoff to the promoter.
  `reset_password()` now also marks the account email-verified when
  completed this way, so a promoter-recruited customer clears both
  account gates (docs/business-rules.md#account-gates) with one email,
  not two.
- [x] `contracts/service.py::create_contract_for_recruited_customer` --
  the CRM counterpart to the existing self-service activation flow:
  producer_agent_id is always the calling promoter's own agent (never
  client-supplied), and the target customer must actually be attributed
  to that same promoter -- a promoter can never activate a contract for
  someone else's customer.
- [x] **Latent permission gap found and fixed while wiring this up**: had
  PROMOTER simply been granted `documents.upload`/`documents.download`
  (needed for this feature, and PROMOTER never had either before),
  `documents/router.py::_assert_contract_document_access`'s existing
  logic would have given them unrestricted access to every contract's
  documents in the whole org, not just their own -- it only ever scoped
  the CUSTOMER case. Fixed to scope PROMOTER to contracts they're the
  producer of, same as the customer-only scoping it already had.
  Deliberately left `GET /customers`/`GET /customers/{id}` (also
  technically callable by PROMOTER via its existing `customers.read`
  grant, and also unscoped) untouched -- out of scope for this session,
  worth revisiting; this feature's own customer list uses a brand-new,
  properly-scoped `GET /network/customers/mine` instead of that endpoint.
- [x] Migration 0034 grants PROMOTER the two new permissions. 7 new
  backend tests; full suite 219/219 passing.

## Session 35 — 2026-09-10 — Admin home quick-links, unified admin Contabilità, invoice-redemption payment leg fix

- [x] Admin "Panoramica" quick-access grid: added Ordini, Riscatti Fatture,
  Provvigioni, Ticket di Supporto, Contabilità to the existing 6 buttons
  (`admin-overview-panel.tsx::QUICK_LINKS`).
- [x] New admin-wide "Contabilità" screen (`GET /accounting/admin`,
  `wallet.manage`-gated, `accounting/service.py::list_all_movements`,
  `admin-accounting-panel.tsx`) -- every customer's LialCash + real-money
  movements merged into one list, filterable to a single customer with
  per-customer totals. New nav tab "Contabilità" in admin-client-page.tsx.
- [x] **Real gap fixed**: a CREDITED invoice redemption's own EUR payment
  (the 5% fee paid via Stripe/bonifico) never appeared in Contabilità at
  all -- only the two resulting LialCash credit rows (base+bonus) did.
  Added the missing `REDEMPTION_PAYMENT` movement, linked to the same
  `invoice_redemption_id`, in both `list_my_movements` and
  `list_all_movements`. Verified the underlying flow was otherwise
  already correct: the customer pays exactly `CASHBACK_PERCENTAGE`% (5%)
  of the confirmed invoice amount, and receives 100%+5% back as LialCash
  once confirmed -- unchanged, this session only fixed accounting
  *visibility*, not the payment math.
- [x] Both Contabilità screens redesigned: an in/out direction badge per
  row, a LialCash-vs-Euro currency badge (with payment method), and a
  "Tipo" column (Ricarica/Cashback/Pagamento/Trasferimento/Storno).
  Order/redemption payment rows now correctly show as an "uscita" (money
  the customer spent), not a "+" as before. Shared formatting extracted
  to `apps/dashboard/lib/accounting-format.ts` so the customer and admin
  screens can never drift apart on labeling.
- [x] `wallets/service.py::_to_transaction_dict` gained `from_user_id`/
  `to_user_id` (additive, not in `WalletTransactionRead`'s schema --
  Pydantic drops unknown kwargs) so the admin accounting view can
  attribute a WALLET row to its customer without a second lookup.
- [x] New tests: the redemption payment leg's amount/link, admin
  cross-customer listing + filtering. Full suite 212/212 passing.

## Session 34 — 2026-09-10 — "Acquisti LialEnergy": parallel imported-product plugin, celery outbox fix

New Shop subcategory, **"Acquisti LialEnergy"**, for products imported from
an external dropshipping/affiliate API (AliExpress first, others later) that
customers can pay for partly or fully with wallet LialCash. Built as an
explicitly requested parallel/isolated "plugin" -- a brand new domain
(`imported_products/`) with its own three tables (`import_providers`,
`imported_products`, `imported_product_orders`), never touching
`catalog.products`/`orders` or their existing behavior. Full detail in
`docs/cashback-partner-invoices-plan.md`'s "Session 34" section.

- [x] Backend domain `imported_products/` (models/schemas/service/router):
  provider CRUD (type/base_url/api_key, key masked like Stripe's), product
  CRUD (added by hand for now -- no live API sync yet, same "scaffold first,
  wire the real call later" precedent as MockPaymentProvider→Stripe), and a
  checkout flow that mirrors `orders/service.py` exactly minus every
  cashback field (these products only ever consume LialCash, never mint it).
- [x] `wallets`: new nullable `reference_imported_order_id` column on
  `wallet_transactions` + a new dedicated `debit_wallet_for_imported_purchase`
  function -- `debit_wallet_for_purchase` untouched.
- [x] `payments/service.py`: webhook dispatcher gained a third
  `metadata.kind` ("imported_order") alongside "order"/"invoice_redemption".
- [x] New permission `imported_products.manage` (SUPER_ADMIN/
  ORGANIZATION_ADMIN/ADMIN only), seeded via `alembic/versions/0033_imported_products.py`.
- [x] Frontend: `CustomerProductsPanel` gained an opt-in `showImportedTab`
  prop (only the Shop tab passes it) adding a fourth, visually identical
  category tab; new `imported-product-checkout-modal.tsx` (same LialCash/
  OTP/payment-method UX as the normal checkout, no cashback step); new
  `admin-imported-products-panel.tsx` (providers, catalog, orders with
  confirm/cancel).
- [x] Backend tests: `tests/test_imported_products.py` (7 tests -- provider
  key masking, partial/full credit, OTP enforcement, cancellation refund via
  REVERSAL, no-cashback-fields contract). Full suite: 210/210 passing.
- [x] **Pre-existing bug found and fixed, unrelated to this feature**:
  `celery_app.py` never imported `organizations.models` (or most other
  domains' models) anywhere in `process_outbox_task`'s own import chain --
  every run of that task (scheduled every minute) crashed with
  `NoReferencedTableError` on its first flush, meaning outbox-driven
  commission calculation may never have actually run via the scheduler.
  Fixed by adding the same "import every domain's models" block `main.py`
  already had. Verified live: three consecutive scheduled ticks succeeded
  after the fix (previously: 100% failure rate, confirmed via container logs).
- [x] Live-verified end-to-end against production (`lial_energy` DB via the
  running `api` container): provider+product creation, active-list
  visibility, then cleaned up -- no shared/singleton settings touched (see
  `[[lialenergy-live-verification-safety]]`-style discipline from Session 33).

## Session 33 — 2026-09-09 — Per-product cashback, "LialCash" branding, Contabilità, real payment channel for invoice redemptions, upload security hardening

Two requests handled back to back. First, the biggest single feature added
this session: a per-product "riscuoti subito cashback" checkout option with
strict anti-fraud requirements set by the user up front ("non deve poter
rubare soldi"). Then, after committing that, a security audit of every file
upload surface plus a follow-up feature request to give the partner-invoice
redemption fee a real payment channel (it only ever supported manual bank
transfer before). Full design detail lives in `business-rules.md` (Product
cashback / LialCash / Accounting / Partner-invoice cashback sections),
`security-model.md`, and `database-model.md` §9-14 -- this entry is the
session-level summary.

**Per-product cashback + OTP + "Contabilità" + LialCash rebrand**:
- `product_versions.cashback_enabled` (admin-toggleable, forced false for
  INTERNAL products, same enforcement pattern as `credit_discount_percentage`).
- `orders.cashback_requested`/`cashback_surcharge_cents`/`cashback_credited_at`:
  opting in at checkout adds a flat 5% surcharge on the residual owed in new
  money; once PAID, `_credit_order_cashback()` mints the base+bonus back to
  the wallet as two rows, computed from the real amount paid (never a
  pre-discount base) and idempotency-guarded.
- Self-checkout spending of existing wallet credit now requires an emailed
  OTP (`WALLET_CREDIT_SPEND_OTP_PURPOSE`, reusing the existing generic OTP
  system) -- admin-created orders are exempt (OTP would go to the customer,
  not the admin).
- "LialCash": every wallet balance/transaction display renamed from EUR to
  a LialCash label across the dashboard (never the underlying schema/currency
  field) to keep it visually distinct from real Stripe/bank-transfer money.
- New `accounting` domain (`GET /accounting/mine`, no new table -- merges
  `wallet_transactions` and paid `orders`' real-money legs on the fly) backing
  a new customer-facing "Contabilità" nav section: filters, totals, CSV export.
- 191 backend tests passing (177 existing + 14 new), ruff/mypy clean
  (4 pre-existing `Result.rowcount` false positives only), frontend build
  clean, full live verification via synthetic data (OTP flow, cashback
  surcharge/crediting on both bank-transfer and Stripe paths, idempotency on
  a retried webhook, accounting feed contents) then cleaned up.

**Upload security audit + hardening** (the user asked directly: "sono
sicuri i documenti caricati?"):
- The existing design (private bucket, no public policy, presigned URLs
  only, nginx Host-header signature mechanics, MIME whitelist + size caps)
  was already solid -- documented in full in `security-model.md`. Two real
  gaps found and fixed, not just narrated:
  1. **Magic-byte verification** (`core/storage.py::_verify_magic_bytes`):
     the client-supplied `Content-Type` header alone was trusted against the
     whitelist -- trivially spoofable. Now the file's actual leading bytes
     are checked against the real signature for every upload path (media,
     documentation, private documents bucket).
  2. **Rate limiting** added to every upload endpoint that lacked it
     (contract documents, order/redemption payment proofs, invoice-redemption
     submission) -- 20 requests/5min per IP, same mechanism as the auth
     endpoints.
  - Existing test fixtures using fake byte content (`b"fake"`,
    `b"irrelevant"`, etc.) for PDF/JPEG uploads had to be updated to carry
    real magic-byte prefixes (`%PDF-1.4`, `\xff\xd8\xff`) once the check
    started actually enforcing -- a maintenance side-effect of tightening
    the check, not a bug in it.

**Invoice-redemption fee now payable by card, with proof upload for bank
transfer** (previously the 3% fee was bank-transfer-only, manually
reconciled by an admin with no self-service card option and no proof
upload -- the user asked directly whether a payment path existed):
- `invoice_redemptions` gained `payment_method`/`stripe_checkout_session_id`/
  `payment_proof_*` columns, mirroring `orders` exactly. New endpoints:
  `PATCH .../payment-method`, `POST .../checkout-session`,
  `POST .../payment-proof`, `GET .../payment-proof-url` (customer and admin).
- `payments/service.py` generalized: `handle_webhook_event` now routes on
  the Stripe session's own `metadata.kind` ("order" vs "invoice_redemption",
  defaulting to "order" for pre-existing sessions) instead of assuming every
  webhook is for an order.
- **Real bug caught and fixed before it shipped**: the first draft of
  `invoice_redemptions/service.py::confirm_payment` (the manual admin
  action) did NOT refuse a CARD-method redemption -- meaning an admin could
  have manually minted wallet credit for a Stripe-selected redemption
  without Stripe ever confirming a real charge, exactly the "steal money"
  scenario the user's very first cashback request warned against. Caught
  while writing tests (mirroring `orders/service.py::confirm_payment`'s
  existing refusal, which the redemption path had been missing), fixed
  immediately, and specifically tested (`test_confirm_payment_refuses_a_card_redemption`)
  plus verified live before considering the feature done.
- Emails improved along the way: `verify()`/`reject()` on a redemption now
  send full branded emails (previously in-app notification only), and the
  credited-cashback email switched from raw EUR to "LialCash" wording for
  consistency with the rebrand above.
- 198 backend tests passing (191 + 7 new), ruff/mypy clean, frontend build
  clean. Live verification: magic-byte rejection of a spoofed PDF, full
  submit→verify→switch-to-CARD→(manual confirm correctly refused)→Stripe-
  webhook-credits→(retry doesn't double-credit) cycle, all test data cleaned
  up afterward.

**Docs updated this session**: `business-rules.md`, `security-model.md`,
`database-model.md` (§9-11 extended, new §14), `cashback-partner-invoices-plan.md`,
`docs/database-schema.sql` (regenerated via `scripts/dump-schema.sh`, now
includes every column above). Rebuilt/redeployed api+celery-worker+dashboard
images, migrations `0031_order_cashback`/`0032_invoice_redemption_payment`
applied to the live dev database.

### Session 33 (same day, continued) — Email consistency audit

The user asked for a full recap of every situation LialCash lands on a
wallet (product order cashback, invoice-redemption cashback, manual admin
top-up) and confirmation each one sends a well-detailed branded email --
including password reset "like every other email". Auditing that claim
found two real gaps, both fixed:

- **Password reset was still plain text** (`core/email.py::send_email()`,
  a separate, older primitive predating the branded-template system) --
  the one email in the platform that never got migrated to
  `render_email()`/`send_html_email()`. Now uses the exact same path as
  every other email (logo, CTA button, consistent styling). The now-fully-
  unused `send_email()` plain-text helper was removed rather than left as
  dead code.
- **The wallet-top-up email still said "&euro;" and linked to a
  non-existent `/dashboard/wallet` route** (leftover from before the
  LialCash rebrand and from before this app's actual route structure --
  wallet is a tab inside `/customer`, not its own page). Fixed to LialCash
  wording, a working deep link, and an explicit "un amministratore ha
  accreditato manualmente" line so it's clearly distinguishable from an
  order/redemption cashback email.
- **The OTP email for spending wallet credit at checkout was generic**
  ("Usa questo codice per confermare l'utilizzo dei tuoi LialCash su questo
  ordine", no product/amount) -- the user specifically asked for it to name
  the product, the order's value, and the LialCash amount involved. `POST
  /orders/mine/request-credit-otp` now takes `product_version_id`/
  `credit_applied_cents` in its body, looks the product up server-side
  (never trusting a client-supplied display string), and builds a fully
  detailed confirmation message.
- Generalized the "deep-link back into a specific dashboard tab from an
  email" mechanism in `customer-client-page.tsx` (previously handled only
  `tab=orders`/`tab=cashback` for the Stripe-return flow) so every email's
  CTA button (`?tab=wallet`, `?tab=orders`, `?tab=cashback`) now actually
  lands on the right tab instead of just the dashboard home.
- Verified live: `request_password_reset` runs the new HTML path without
  error, the OTP context line correctly includes a real product name/order
  value/credit amount pulled from `get_quote()`, `render_email()` output
  always contains the logo. 198/198 tests still passing, ruff/mypy clean,
  frontend build clean. Test data cleaned up. Rebuilt/redeployed
  api+celery-worker images (no schema change, no new migration needed).

### Session 33 (same day, continued) — Two real production incidents, both found and fixed live

**Incident 1 (self-inflicted)**: a live-verification script for the invoice-
redemption Stripe flow set placeholder Stripe keys (`sk_test_verify`/
`pk_test_verify`) on the real organization to test the checkout-session code
path without hitting the real Stripe API, then the cleanup afterward only
deleted the synthetic test rows it had inserted -- it never restored the org's
real Stripe keys, since that mutation was to a pre-existing shared row, not
something the usual "delete what I created" cleanup pattern covers. This
silently broke real "Paga con carta" until the user reported the failure in a
later turn. Fixed by clearing the broken keys (hiding the card option rather
than showing an error) until the user supplied their real keys, which were
then set and verified against the live Stripe API
(`stripe.Account.retrieve()`). Saved as a standing memory
(`lialenergy-live-verification-safety`) so future live-DB verification never
mutates a shared settings row without capturing and restoring its prior value.

**Incident 2 (pre-existing, unrelated to this session's own changes)**: while
confirming the Stripe-key fix actually worked, the user asked whether a real
test order had actually been marked paid -- it hadn't. Investigation (`nginx`
access log, Stripe's own Event/WebhookEndpoint API) found the Stripe webhook
endpoint had been registered pointing at `/api/payments/stripe/webhook/{id}`,
a path nginx routes entirely to the dashboard's BFF, not FastAPI -- **every
webhook delivery had been 404ing since the endpoint was first registered**,
meaning no card payment (order or invoice-redemption fee) had ever been
auto-confirmed by the real webhook; every prior "PAID via Stripe" order had
actually been reconciled by a human/script calling `mark_paid_via_stripe()`
directly. Fixed with a dedicated, more-specific `location
/api/payments/stripe/webhook/` block in `infrastructure/nginx/nginx.conf`
(variable + resolver, not a static target, so it survives the api container
being recreated) -- verified live (`curl -X POST .../payments/stripe/webhook/<id>`
now returns 400 "missing signature" instead of 404). The one real, currently-
pending stuck order (confirmed genuinely paid via a direct Stripe API check)
was reconciled the same way. See `server-migration-guide.md §8` bug #15 and
`business-rules.md §Partner-invoice-cashback`.

**Incident 3 (found immediately after "fixing" incident 2)**: the user tried
another real test payment and it still didn't confirm -- the nginx fix alone
wasn't enough. `payments/service.py::handle_webhook_event` called
`session.get("metadata")`, but `session`/`session.metadata` are
`stripe.StripeObject`, and this SDK version's `StripeObject` deliberately has
no `.get()` (raises `AttributeError`, points at `.to_dict()`/attribute access
instead) -- every existing test called `mark_paid_via_stripe()` directly,
bypassing `construct_event()` entirely, so no test ever exercised a real
`StripeObject` here. This is why the same class of bug shipped twice in a
row. Fixed with `getattr(getattr(session, "metadata", None), "kind",
"order")`. Added `tests/test_payments.py` -- builds a real HMAC-SHA256
Stripe-style signature and calls `handle_webhook_event()` end-to-end (order
path, invoice-redemption path, missing-metadata fallback, bad-signature
rejection), so this exact bug class fails a test next time instead of
shipping. Verified live all the way through the real public domain: a
genuinely HMAC-signed `curl` POST to `https://app.lialenergy.it/api/
payments/stripe/webhook/<org-id>` now returns `200 {"received":true}`
instead of 500. 202/202 tests passing (198 + 4 new), ruff/mypy clean.
Rebuilt/redeployed api+celery-worker.

### Session 33 (same day, continued) — Cashback unified to 5%, timestamps, demo product, checkout UX, dashboard home redesign

Four smaller, user-driven follow-ups in one pass:

- **Cashback percentage unified**: `invoice_redemptions/models.py::
  CASHBACK_PERCENTAGE` was 3%, `orders/service.py::
  ORDER_CASHBACK_PERCENTAGE` was 5% -- purely an artifact of being built in
  separate sessions. Both now 5%, every UI string and test assertion
  updated to match.
- **Full timestamps, not just dates**, on orders (customer + admin) and
  invoice redemptions (customer + admin, which previously showed no
  timestamp at all) -- wallet/accounting already had them.
- **Real demo product created**: `CASHBACK-TOTALE-01` ("Power Bank
  20000mAh - Cashback Totale", 50,00 EUR, 20% payable in LialCash,
  cashback_enabled), a permanent catalog entry (same precedent as Session
  26's two demo products), showing both mechanics together in the Shop.
- **`product-checkout-modal.tsx` redesigned**: was one flat block of
  controls; now numbered sections (spend LialCash / OTP / return cashback /
  payment method) with a real on/off switch (not a tiny checkbox), quick
  preset chips (25/50/75/max) instead of typing an amount, the full price
  shown struck-through next to the discounted price, and an always-visible
  running total. No business logic changed.
- **Customer and promoter dashboard "home" screens redesigned**: the full-
  height decorative photo banner was replaced with a compact hero (same
  photo, ~1/3 the height, greeting text overlaid) to make room for what's
  actually useful without scrolling -- a new `dashboard-wallet-stats.tsx`
  (three animated, glowing stat cards: wallet balance, cashback
  accumulated, LialCash spent, count-up on mount/refetch via a small
  dependency-free `useCountUp` hook) and a 6-item quick-access shortcut
  grid (new for the customer home; the promoter home already had a
  4-item version, extended to include Wallet and Riscatta Cashback).
  `SectionBanner` gained optional `compact`/`children` props for this,
  backward-compatible (every other call site is unaffected). Verified with
  a clean frontend build; rebuilt/redeployed the dashboard image.

### Session 33 (same day, continued) — Every cashback/bonus credit now traceable to its order or redemption

The backend already stored `reference_order_id`/`reference_invoice_
redemption_id` on every wallet transaction (added when orders/invoice
redemptions were built), but `WalletTransactionRead` in the frontend's own
`lib/types.ts` never declared `reference_order_id` -- a stale type gap --
and no UI actually surfaced either field, so a customer/promoter/admin
looking at "+50,00 LialCash · Cashback ordine" had no way to trace which
order it came from without asking support.

- `wallet-panel.tsx` (customer + promoter, shared): new "Riferimento"
  column, a clickable chip ("Ordine #XXXXXXXX" / "Riscatto #XXXXXXXX")
  deep-linking into "I miei Ordini"/"Riscatta Cashback" on whichever
  dashboard the panel is mounted in (checked via `window.location.pathname`).
  Required adding a `?tab=` deep-link effect to `promoter-client-page.tsx`,
  which didn't have one at all before (only the customer page did, for the
  Stripe-return-banner flow).
- `accounting-panel.tsx`: same reference chip added as its own column
  (customer-only, so no path-detection needed) plus in the CSV export.
  Backend gap here was real, not just a display omission:
  `accounting/service.py::list_my_movements` resolved `order_id`/
  `product_name` for order-linked rows but never resolved anything for
  invoice-redemption-linked rows (`order_id` stayed NULL, no partner name)
  -- added the same batched lookup pattern for `InvoiceRedemption`/
  `Partner`, and a new `invoice_redemption_id` field on
  `FinancialMovementRead` (kept separate from `order_id` rather than
  overloading it -- different domain entirely).
- `admin-wallets-panel.tsx`: the existing expandable-row detail (which
  already showed `reference_contract_id` when present) gained the same
  treatment for `reference_order_id`/`reference_invoice_redemption_id`.
- New test `test_invoice_redemption_credit_rows_carry_the_redemption_id_and_partner_name`.
  203/203 tests passing (202 + 1 new), ruff/mypy clean, frontend build
  clean. Verified live against the real OpenAPI schema that both
  `WalletTransactionRead.reference_order_id` and
  `FinancialMovementRead.invoice_redemption_id` are actually served.
  Rebuilt/redeployed api+celery-worker+dashboard.

## Session 32 — 2026-09-07 (same day, continued) — Email on wallet "Ricarica" top-up

The Session 27 cashback email only covered the partner-invoice redemption
flow (`invoice_redemptions/service.py::confirm_payment`) -- a plain admin
"Ricarica" top-up (`POST /wallets/admin/topup`) had no email at all, only
the existing in-app notification. Both routes actually converge on the same
`wallets/service.py::credit_wallet()`, so the email was added there instead
of per-caller:

- New `_send_wallet_credited_email()` (same branded-template mechanism as
  every other email in this project), called from `credit_wallet()` after
  the credit already committed -- best-effort, an SMTP hiccup can't undo
  money that's already landed.
- Guarded by `reference_invoice_redemption_id is None` so the two email
  sources never double up for the same credit: a redemption's own two
  `credit_wallet()` calls (base + bonus) both set that reference, and its
  caller already sends a richer, redemption-specific email right after --
  see business-rules.md#internal-wallet.
- Two new tests (`test_credit_wallet_sends_email_for_a_plain_top_up`,
  `test_credit_wallet_skips_email_when_already_sent_by_invoice_redemptions`)
  assert the routing itself via `unittest.mock.patch` on
  `_send_wallet_credited_email`, since SMTP isn't configured in the test
  environment (both paths would otherwise just log a warning and look
  identical). Full suite 164/164 passing, ruff/mypy clean. Rebuilt/
  redeployed api+celery images, confirmed healthy.

## Session 31 — 2026-09-07 — Cashback copy fix, real Partner data seeded

Small, quick follow-up:

- `invoice-redemption-panel.tsx`: "Hai già pagato una bolletta..." →
  "...bolletta/fattura..." per explicit wording request.
- Seeded the org's first three real `Partner` rows via the existing
  `POST /partners` admin endpoint (no code change needed -- the CRUD and
  the customer-facing dropdown/empty-state already existed, just unused
  until now): **Lial Energy** (so a customer can redeem cashback on their
  own Lial Energy bill, not only an external supplier's), **Eviso** (real
  logo verified and hotlinked from `eviso.it`), **Aenergy** (name only --
  deliberately no logo, see business-rules.md#partner-invoice-cashback for
  why). This also un-disables the "Nuova richiesta" button, which Session
  30's parallel-agent fix had correctly disabled while the partner list
  was empty.
- Verified: dashboard rebuilt/redeployed, live `GET /api/partners` confirms
  all three rows with `is_active: true`. No backend code changed this
  session, so no new tests/migration/schema-dump needed.

## Session 30 — 2026-09-06 (same day, continued) — Self-service Lial Energy contract activation ("Attiva Contratto")

The user's follow-up after Session 29 confirmed contracts were staff-only:
why not let the customer start one themselves? Full design in
`business-rules.md#contract-self-service` (kept current there) -- summary:

- A clarifying question was asked and answered before writing any code:
  once a customer finishes uploading required documents, should approval
  become fully automatic, or keep one staff document-check before payment?
  Chosen: **keep one check** -- "un click admin prima del pagamento". This
  shaped the whole design below.
- New `POST /contracts/mine` (`get_current_user` only, same "self-checkout"
  shape as `POST /orders/mine`) -- `contracts/service.py::
  create_contract_self_service` resolves the commission producer from the
  customer's own referral attribution (same lookup "lavora con noi" uses),
  rejects anything not `category=INTERNAL`, creates the supply point
  (reusing `customers/service.py::add_supply_point` directly, bypassing its
  staff-only router) and the contract, then immediately submits it to
  `DOCUMENTS_PENDING`.
- `documents/service.py::upload_document` now auto-advances a contract
  `SUBMITTED|DOCUMENTS_PENDING` → `UNDER_REVIEW` once every required
  document type has an upload -- not self-service-specific, any contract
  gets this once its documents are all in.
- `contracts/service.py::transition_contract` gained `AUTO_CASCADE_AFTER`:
  `APPROVED` auto-continues into `PAYMENT_PENDING`, `PAID` auto-continues
  through `ACTIVATION_PENDING` into `ACTIVE` -- collapsing what used to be
  5 staff clicks (UNDER_REVIEW→APPROVED→PAYMENT_PENDING→PAID→
  ACTIVATION_PENDING→ACTIVE) into exactly 2 ("Approva", "Conferma
  pagamento"), per the chosen option above. Every hop is still individually
  transitioned/audited/outbox-enqueued -- the cascade is a loop inside
  `transition_contract` calling itself, not a shortcut that skips any of
  that. Applies to every contract, not just self-service-originated ones.
- Real bug caught before it shipped: five existing tests
  (`test_branch_summary.py`, `test_commission_engine_integration.py`,
  `test_contract_renewal.py`, `test_rank_progress.py`,
  `test_rank_evaluation.py`) manually walked every status one hop at a
  time, including `PAYMENT_PENDING` and `ACTIVATION_PENDING` as their own
  explicit `transition_contract()` calls -- with the cascade, the contract
  was already past those by the time the loop tried to re-target them,
  raising `InvalidTransitionError`. Fixed by trimming those five loops to
  the still-manual hops only (`SUBMITTED`, `UNDER_REVIEW`, `APPROVED`,
  `PAID`) -- the admin contracts panel needed no equivalent fix, since its
  transition dropdown already only offers state-machine-valid next steps
  and just reflects wherever the contract ends up after the cascade.
- New `contract-activation-wizard.tsx` (2 steps: supply-point details incl.
  POD/PDR depending on the product's energy type, then the existing
  `ContractDocumentsPanel` embedded directly) wired to a new "Attiva
  Contratto" button on Lial Energy product cards in
  `customer-products-panel.tsx`. Real bug caught and fixed in the same
  pass: "I miei Contratti" (`customer-client-page.tsx`) was rendering a
  contracts list from a `Server Component`-fetched prop with no client-side
  refetch path at all -- activating a contract would never have shown up
  there without a full page reload. Converted to a `useQuery` seeded with
  that same prop as `initialData`, so the wizard's post-activation
  `invalidateQueries` call actually does something.
- Verified: 8 new backend tests (attribution resolution, non-INTERNAL
  rejection, no-customer-record rejection, no-referring-promoter rejection,
  both cascades, both auto-advance-on-upload cases) plus the 5 fixed
  existing tests, full suite 162/162 passing, ruff/mypy clean (same 30
  pre-existing errors as every prior session, none in touched files).
  `docker compose build` succeeded for both api and dashboard; redeployed
  and live-verified against the real database with read-only/
  validation-only calls (a fake product id correctly 400s "Product version
  not found", a real PARTNER product id correctly 400s "Solo i prodotti
  Lial Energy si attivano come contratto") -- deliberately did NOT create a
  real self-service contract end-to-end against production data; the
  create+cascade+auto-advance logic itself is covered by the 8 new
  automated tests against a real Postgres engine instead.

## Session 29 — 2026-09-06 (same day, continued) — Verified credit-% checkout + contract-flow authority, product-showcase redesign, live camera capture, desktop nav bar

Follow-up session: two things verified against the live database rather
than re-explained from memory (both confirmed already correct, see
`business-rules.md`'s "Session 29 follow-up" and "Who can move a contract
through this pipeline" -- kept current there, not duplicated here), plus
visual/UX polish:

- Verified live: a PARTNER product's own `credit_discount_percentage`
  correctly caps the wallet-credit amount a checkout will accept
  (`GET /orders/quote/mine` on a 69,00€/30% product returned
  `max_creditable_cents: 2070`) -- no bug found, no change needed.
- Verified: the contract pipeline (DRAFT→...→ACTIVE) is staff-only
  (`contracts.review`), never customer self-service beyond document
  upload + IBAN -- confirmed by reading `rbac/models.py` and
  `contracts/router.py`, not assumed.
- `customer-products-panel.tsx` + `product-detail-modal.tsx` redesigned:
  bigger/bolder price and a computed "crediti usabili" euro figure side by
  side, a discount ribbon overlay on the photo, hover zoom/lift/fade-in
  animations, full-width gradient buy button.
- `header-energy.jpg` swapped again for a brighter, more striking aerial
  solar-farm photo, per explicit "più luminose" feedback on the Session 28
  pick.
- New `camera-capture-modal.tsx`: a real live `getUserMedia` camera
  viewfinder for the cashback-redemption upload, replacing the Session 27
  `<input capture="environment">` approach, which silently did nothing on
  desktop browsers (no webcam access) and only worked on some mobile ones.
- `app-shell.tsx` gained a desktop top nav bar (big pill buttons, same
  items as the mobile bottom bar, pinned under the header on every page)
  and larger mobile bottom-bar touch targets -- this was built by a
  parallel agent mid-session (observed via its own task notification,
  reviewed and kept as correct/on-spec rather than re-done) to close a gap
  left after Session 27 only shipped the mobile half of "primary tools as
  big buttons, bottom on mobile / top on desktop."
- Verified: `docker compose build` succeeded for the dashboard (TypeScript
  compiled clean) including both this session's changes and the parallel
  agent's `app-shell.tsx` work together; redeployed and confirmed healthy,
  server-rendered pages return 200/307 as expected (no crash).

## Session 28 — 2026-09-06 (same day, continued) — E-commerce order flow, order-confirmation email, Stripe new-tab checkout, account freeze, brighter header photos

Another multi-part request in one message, all detailed in
`business-rules.md`'s "Store orders vs. Lial Energy contracts" and "Account
freeze" sections (kept current there, not duplicated here) -- summary:

- **E-commerce polish for the DROPSHIPPING/PARTNER store** (explicitly NOT
  Lial Energy contract products, which stay contract-only): a shared
  `product-thumbnail.tsx` (photo or a standard placeholder icon) now
  appears everywhere a product/order shows a picture, including a new
  `OrderRead.product_image_url` field; a new `product-detail-modal.tsx`
  shows the full product page before checkout instead of jumping straight
  from the grid card to payment; a brand-new customer-facing "I miei
  Ordini" tab (`customer-orders-panel.tsx`) lists every order with its
  status and a "Paga ora" action, mirroring the existing admin gestionale
  (`admin-orders-panel.tsx`, which also gained the same thumbnails).
- **Order-confirmation email** (`orders/service.py::_send_order_confirmation_email`,
  fires after `create_order()` already committed): explains exactly how to
  pay -- IBAN+causale for bank transfer, a real freshly-minted Stripe link
  for card, or "nothing to pay" when credit covered it all. Real bug caught
  and fixed by the test suite before this shipped: the first version only
  caught `payments_service.StripeNotConfiguredError` around the Stripe-link
  creation, so a genuine Stripe API error (bad key, outage) propagated
  uncaught and took the whole (already-committed) order creation down with
  it -- broadened to also catch `stripe.error.StripeError`.
- **Stripe checkout now opens in a new tab** (`window.open(...,"_blank")`)
  instead of a full-page redirect, in both the checkout modal and the new
  order list's "Paga ora" -- per explicit request, so a Stripe failure or a
  change of mind never loses the dashboard tab underneath it.
- **Account freeze**: `PATCH /users/{id}/freeze`/`/unfreeze`, a new
  `users.manage_lifecycle` permission (SUPER_ADMIN only, migration 0027,
  same seeding pattern as `organization.manage_payments`).
  `auth/service.py::authenticate()` now checks `users.status` before the
  password and revokes every existing session on freeze -- an
  already-logged-in frozen account is kicked out immediately, not just
  blocked on its next login. Buttons added to both
  `admin-customers-panel.tsx` and `admin-promoters-panel.tsx`, gated on the
  `isSuperAdmin` prop already computed server-side in `app/admin/page.tsx`.
  **"Elimina utente" (hard delete) was explicitly deferred by the user**
  after a clarifying question about the tradeoff (breaking other
  promoters' commission history vs. Italian fiscal retention requirements
  for contracts) -- freeze-only ships this session; delete/anonymize is
  future work.
- **Dashboard header images**: all `SectionBanner` images (previously
  hotlinked from Wikimedia, several dim/dark, "commissions" and "wallets"
  sharing one photo) replaced with brighter, distinct, locally-bundled
  photos (`apps/dashboard/public/images/header-*.jpg`, sourced from
  Unsplash, each one visually inspected before picking it) -- same
  bundle-locally convention `documentation-header.jpg` already used.
  `SectionBanner` itself switched from a raw `<img>` to `next/image` now
  that every source is local.
- **Not done this session**: the cashback-credited email was requested
  again but was already shipped in Session 27 (`invoice_redemptions/
  service.py::confirm_payment`) -- verified still correct, no changes
  needed; product-photo *upload* (as opposed to display) already existed
  from an earlier session (`POST /products/versions/{id}/photo`, wired to
  `PhotoUpload` in the admin product edit form) and needed no changes
  either.
- Verified: full backend suite 154/154 passing (149 + 5 new for freeze/
  unfreeze/self-freeze-guard/cross-org-guard/session-revocation), ruff
  clean; `docker compose build` succeeded for both api and dashboard
  (TypeScript compiled clean); live-verified freeze/unfreeze end-to-end
  against a disposable test user on the real database (login correctly
  423s while frozen, session revoked, unfreeze restores it, test user then
  removed) rather than only against the automated test suite.

## Session 27 — 2026-09-06 — Real Stripe test keys, account gates (email verification/profile completion/promoter OTP), branded emails, nav redesign

A large, multi-part request in one message. Summary by area:

- **Stripe live-tested**: the user's own real TEST-mode publishable/secret
  keys were configured via the existing admin payment-settings endpoint (no
  code changes needed -- the integration built in Session 26 was correct,
  just never exercised with real keys). Verified end-to-end: a real
  Checkout Session URL (`checkout.stripe.com/c/pay/cs_test_...`) was
  generated for a test order, `get_available_payment_methods()` now
  reports `card: True`, order cleanup verified.
- **Invoice-redemption camera capture**: `invoice-redemption-panel.tsx`'s
  single ambiguous `<input capture>` (which forced camera-only on many
  mobile browsers) replaced with two explicit buttons -- "Scatta foto"
  (camera) and "Carica file" (file picker) -- each its own hidden input.
- **"Simula provvigione" removed** from the promoter dashboard's big
  quick-link button grid (`QUICK_LINKS` in `promoter-client-page.tsx`) per
  explicit request -- left untouched in the sidebar (`NAV_ITEMS`), where it
  still works exactly as before.
- **Account gates** (full detail in `business-rules.md#account-gates`):
  mandatory email verification for new registrations (existing accounts
  grandfathered), mandatory fiscal-code/residence profile completion
  (retroactive for everyone), and a collaboration-agreement + emailed-OTP
  gate on "lavora con noi". New tables `email_verification_tokens` and
  `otp_codes` (migration `0026_account_gates_and_promoter_otp.py`, which
  also backfills `email_verified_at` for every pre-existing user). New
  columns on `users` (privacy/fiscal-code/residence) and `agent_profiles`
  (collaboration acceptance). New endpoints: `POST /auth/verify-email`,
  `POST /auth/resend-verification`, `GET/PATCH /auth/me/profile`,
  `POST /network/agents/apply/request-otp`; `GET /auth/me` extended with
  `email_verified`/`profile_complete`/`privacy_accepted`. Frontend:
  `account-gate.tsx` blocks the whole dashboard behind a modal (admin-tier
  roles exempt), `/verify-email` confirmation page, the registration form
  gained a mandatory privacy checkbox, and the "Lavora con noi" card gained
  a two-step modal (accept contract → request OTP → confirm).
- **Admin visibility**: `CustomerRead`/`AgentListItemRead` now carry
  `email_verified`/`privacy_accepted` (and, for agents,
  `collaboration_accepted_at`) via a `users` join in `list_customers()`/
  `list_agents()` -- small ✓/✗ badges added next to each row in
  `admin-customers-panel.tsx`/`admin-promoters-panel.tsx`. No new admin
  screen -- enriching the existing lists was the more contained way to show
  "who accepted what" the user asked for.
- **Branded HTML emails**: `core/email_templates.py` (new) -- one shared
  table-based HTML shell with the logo (`https://lialenergy.it/img/logo.png`)
  and brand color, used by every email below; `core/email.py` gained
  `send_html_email()` (multipart/alternative, HTML + plain-text fallback).
  New sends: registration confirmation link, promoter-application OTP,
  cashback-credited (fires in `invoice_redemptions/service.py::confirm_payment`
  right after the wallet credit), and a new-ticket admin alert (fires in
  `support/service.py::create_ticket`, to
  `Organization.settings.admin_notification_email`, defaulting to
  `info@lialenergy.it` -- a new admin-editable settings field, same
  merge-not-replace pattern as the existing bank/Stripe settings). All
  best-effort: SMTP is already configured in production (Aruba), but every
  send is wrapped in the same `EmailNotConfiguredError`-falls-through-to-log
  pattern as the pre-existing password-reset email, and none of them can
  block the action that triggered them.
- **Navigation**: mobile gained an app-style bottom tab bar (`app-shell.tsx`,
  `lg:hidden`, first 4 nav items + an "Altro" button opening the existing
  drawer for the rest) -- desktop was left as its existing persistent
  sidebar + top header, which already puts the primary tools "in alto" as
  requested; the net-new piece was the mobile bottom bar.
- **Not done / explicitly out of scope this session**: a full visual
  redesign of the customer area ("più professionale, bella, moderna e
  animata") -- the request was open-ended and the highest-leverage,
  bounded changes (nav redesign, account-gate UX, camera capture) were
  prioritized instead of a ground-up restyle; real OCR (unchanged, still
  Session 23's decision).
- Verified: `docker exec`-minted tokens against the **real production
  database** (not demo seed data) confirm `GET /auth/me` correctly reports
  `email_verified: true` / `profile_complete: false` for every real
  pre-existing customer (the exact grandfather behavior asked for), and the
  enriched customer/agent list endpoints return the new fields without
  error against real rows. Full backend suite: 149/149 passing (140
  pre-existing + 9 new, covering profile completion, email verification
  round-trip/expiry, OTP consume-once/expiry, and the promoter
  contract+OTP gate), ruff/mypy clean (same pre-existing rowcount/reports
  false-positives as every prior session). `docker compose build` succeeded
  for api/celery-worker/celery-beat/dashboard (TypeScript compiled clean),
  containers recreated and confirmed healthy against the live stack.
- **Stated limitation**: as in every prior session, no interactive browser
  click-through was available in this headless environment -- the new
  frontend flows (account-gate modal, verify-email page, Lavora-con-noi
  OTP modal, bottom tab bar) were verified via server-render/HTTP checks
  and code review, not a real browser session.

## Session 26 — 2026-09-05 (same day, continued) — Customer self-checkout, Stripe card payments, marketplace category tabs

Closes the last gap in the cashback/orders project: a customer can now buy
a DROPSHIPPING/PARTNER product themselves (not just an admin on their
behalf), and pay the residual with a card via Stripe, not just bank
transfer. Full detail in `docs/cashback-partner-invoices-plan.md`
(kept current, not duplicated here) -- summary:

- Two architecture questions put to the user before writing code (integrate
  Stripe now vs. later; open self-checkout vs. keep admin-only) given the
  cost of guessing wrong: **both yes** -- Stripe now (keys configurable,
  activatable later), self-checkout now.
- `orders` extended with `payment_method` (BANK_TRANSFER/CARD) and
  `stripe_checkout_session_id`; `create_order()` validates the payment
  method only when there's a residual to pay, and only accepts a method
  that's actually configured -- server-side enforcement of "the button
  isn't just disabled, it doesn't exist if not configured."
- New `payments` domain: creates a real Stripe Checkout Session for exactly
  the residual (never the full price), and a per-organization webhook
  (`POST /payments/stripe/webhook/{organization_id}`, deliberately
  unauthenticated -- the Stripe signature IS the auth) marks an order PAID
  automatically on `checkout.session.completed`.
- `organizations` extended with `bank_transfer_instructions` (free text
  admins can set) and a new, stricter permission
  `organization.manage_payments` (SUPER_ADMIN only, unlike the bank IBAN's
  `organization.manage` which also includes ORGANIZATION_ADMIN/ADMIN) --
  the user's own framing: whoever touches card payments is a smaller circle
  than whoever touches where bonifico money goes. Stripe secret/webhook
  keys are never echoed back in full by any endpoint, only "configured
  yes/no" + last 4 chars.
- New self-checkout endpoints (`/orders/quote/mine`, `/orders/mine` GET+POST,
  `/orders/mine/{id}/checkout-session`) open to any authenticated user,
  `customer_user_id` always forced to the caller, same rule as
  `POST /wallets/transfer`.
- Frontend: new `product-checkout-modal.tsx` (credit slider pre-filled to
  the max usable amount, payment method buttons that simply don't render
  when unavailable, then either a success message, bank transfer
  instructions, or a Stripe redirect); "Acquista" button added to
  `customer-products-panel.tsx` for non-INTERNAL products, only in the
  customer's own Shop view (not the promoter's referral-sharing view of the
  same component); Stripe settings card in the admin settings panel, shown
  only when `isSuperAdmin` (computed server-side in `app/admin/page.tsx`
  from the session JWT's roles -- a UX nicety, the real enforcement is the
  backend permission).
- Real IBAN configured in production per the user's own message:
  `IT66W0883330410000000015702`, "Lial Energy Srl" -- saved via the admin
  settings panel, not `.env`.
- Two test products created on explicit request (not throwaway
  verification data -- left in the catalog): `PARTNER-TEST-01` "Zaino
  Outdoor Partner (TEST)" (69,00E, 30% credit discount) and
  `DROPSHIP-TEST-01` "Power Bank 20000mAh (TEST)" (39,00E, 0% credit
  discount -- always full bank transfer or card).
- Customer Shop also got category tabs (Lial Energy / Prodotti Partner /
  Dropshipping) in the same session, filtering `customer-products-panel.tsx`
  by `Product.category` with a per-tab count.
- Verified live via real HTTP calls: self-checkout quote correctly reports
  payment-method availability; a BANK_TRANSFER self-checkout order
  succeeds; the same order with CARD is correctly rejected while Stripe is
  unconfigured; ADMIN gets 403 on the payment-settings endpoints (only
  SUPER_ADMIN passes); setting/clearing test Stripe keys correctly flips
  `card_available`; the `stripe` Python library (v15) was smoke-tested
  against a fake key/signature to confirm it raises the expected error
  types before writing production code against it. Full backend suite:
  139/139 passing, ruff/mypy clean (same pre-existing rowcount
  false-positives as before).
- **Stated limitation**: verified server-rendered HTML for the new pages
  (no crash, every new tab/nav item present) using real authenticated
  sessions built from minted tokens, but did NOT do a full interactive
  browser click-through -- no browser tool was available in this headless
  session, and resetting a real customer's password just to test was
  judged not worth the risk. The business logic is thoroughly covered by
  the automated tests and direct HTTP calls above instead.
- Not done: real Stripe keys (the panel works, verified with test keys, but
  no live keys entered yet), invoice-redemption duplicate detection, real
  OCR (unchanged from Session 23's decision).

## Session 25 — 2026-09-05 (same day, continued) — PWA home-screen icons, scheduled DB backups, admin-editable company IBAN

Three independent items, none touching the cashback/orders work itself.

- **Real bug found and fixed**: `.env`'s `COMPANY_BANK_HOLDER=Lial Energy`
  (added Session 23, unquoted) breaks any script that `source`s `.env` as
  bash rather than parsing it as a real dotenv file -- bash reads `Energy`
  as a command to run and errors out, aborting the whole script under
  `set -e`. Confirmed live: this silently prevented `scripts/backup.sh`
  from ever completing. Fixed by quoting the value; documented the
  constraint in a comment on that script so it doesn't happen again with a
  different value later.
- **Daily backups scheduled**: `scripts/backup.sh` already existed
  (`pg_dump` + gzip) but was never in crontab -- only `renew-cert.sh` was.
  Added `scripts/backup.sh dev >> ./backups/backup.log` at 04:00 daily (the
  `dev` compose file is what's actually running in production on this
  server -- confirmed by checking which containers exist; `production`'s
  compose file is unused). Also added retention (`find -mtime +14 -delete`)
  to the script itself, since it previously kept every dump forever. Still
  NOT sufficient disaster recovery on its own -- same disk as the database,
  no off-server copy -- see the script's own header comment and
  `docs/deployment.md`.
- **PWA icons for "Aggiungi a schermata Home"**: neither site had a
  favicon/apple-touch-icon/manifest at all, so mobile browsers fell back to
  a page screenshot or a generic globe instead of the Lial logo. Generated
  proper square, white-padded icons (32/16/180/192/512px) from the existing
  marketing-site logo (Pillow, one-off, not a recurring build step) and
  wired them into both sites: the marketing site via manual `<link>` tags +
  `site.webmanifest`, the dashboard via Next.js's file-based convention
  (`app/icon.png`, `app/apple-icon.png`, `app/manifest.ts`). Also fixed a
  real nginx MIME-type gap while verifying this: `.webmanifest` has no
  entry in nginx's stock `mime.types`, so it was served as
  `application/octet-stream` -- some browsers silently ignore a manifest
  served with the wrong content-type. Added an explicit `types {}` block.
- **Company IBAN is now admin-editable from the dashboard**, not just an
  `.env` value requiring server access + a container restart. New
  `GET`/`PATCH /organizations/me/settings` (new `organization.manage`
  permission, same three roles as `wallet.manage`) reads/writes a typed
  subset of the already-existing `Organization.settings` JSONB column (no
  migration needed for the column itself, just the permission). New admin
  tab "Impostazioni". `GET /invoice-redemptions/payment-info` now reads the
  DB value first, falling back to `.env`'s `COMPANY_BANK_IBAN` only as a
  bootstrap default for a server nobody has configured yet. Verified live:
  set via the API, reflected immediately in payment-info, then cleared
  (test value, not a real account).
- Backend suite 134/134 passing (2 new tests for the settings merge
  behavior), ruff clean, mypy clean (same pre-existing rowcount
  false-positives, nothing new).

## Session 24 — 2026-09-05 (same day, continued) — Cashback Phase 4: spending credits on orders

Closes the loop opened in Session 23: credits could be earned (invoice
redemption) but not spent. Full detail in
`docs/cashback-partner-invoices-plan.md` (kept current, not duplicated here)
-- summary:

- New `orders` domain (checkout for DROPSHIPPING/PARTNER products only,
  never INTERNAL) -- deliberately not `Contract`, whose `supply_point_id` is
  NOT NULL by design. `AWAITING_PAYMENT -> PAID` (or straight to `PAID` if
  credit covers 100%), `CANCELLED` reachable from `AWAITING_PAYMENT` and
  refunds the exact credit applied. Admin-only for now (confirmed with the
  user: no self-checkout yet).
- `wallets`: new `PURCHASE_DEBIT` transaction type (mirror of `ADMIN_CREDIT`
  -- `to_wallet_id` NULL, money leaves a wallet to pay for an order) and
  `debit_wallet_for_purchase()`. Extended `reverse_transaction()` to
  correctly refund a `PURCHASE_DEBIT` (no recipient wallet to claw back
  from, only a credit-back to the buyer) -- this case would previously have
  silently mis-handled the reversal (tried to debit a NULL `to_wallet_id`,
  always raising `InsufficientBalanceError`).
- **Real bug found and fixed during testing**: `create_order()` originally
  flushed the `Order` row, then attempted the wallet debit, planning to
  `db.rollback()` on `InsufficientBalanceError`. That rollback broke the
  test suite's SAVEPOINT-based session fixture (same class of issue already
  documented on `debit_and_transfer`'s identical insufficient-balance path).
  Fixed by checking the wallet balance *before* creating the order row at
  all, so no rollback is ever needed -- matches the existing codebase
  convention exactly instead of reinventing it worse.
- Two architecture questions were put to the user before writing any of
  this (new `orders` domain vs. extending `Contract`; admin-only vs.
  self-checkout) rather than assumed, given the cost of guessing wrong at
  this scope -- both confirmed as designed above.
- Verified live via real HTTP calls: an 80,00E product at 25% credit
  discount, customer with 30,00E balance, order applying the full 20,00E
  cap left a 10,00E balance and a 60,00E residual; confirm-payment moved it
  to PAID. Cap/balance rejections, the straight-to-PAID 100%-credit case,
  cancel-refund, double-action guards, and the INTERNAL-category rejection
  all verified. Full backend suite 132/132 passing, ruff clean, mypy clean
  (same pre-existing Result.rowcount stub false-positives as before, one
  more instance from the new debit function, not a new class of issue).

## Session 23 — 2026-09-05 (same day, continued) — Partner-invoice cashback (Phases 0-2), wallet transfer default-deny

Full implementation of the cashback design scoped out earlier the same
session (Session 22's note, and the artifact "Cashback Circolare"). Complete
technical detail, what's built vs. not, and open decisions all live in
`docs/cashback-partner-invoices-plan.md` (kept as a living resumable status
file, not duplicated here) -- summary only:

- **New domains**: `partners` (external supplier anagrafica, e.g. Eviso) and
  `invoice_redemptions` (a customer/promoter redeems part of what they paid a
  partner supplier as internal wallet credit: upload proof → admin verifies
  the real amount → customer pays 3% by bank transfer → admin confirms →
  wallet credited 100%+3%, as two separate ledger rows, never one combined
  row). New migrations `0020`/`0021`.
- **Product categorization**: `Product.category` (INTERNAL/DROPSHIPPING/
  PARTNER) + `ProductVersion.credit_discount_percentage`, enforced server-side
  to stay 0 for INTERNAL regardless of what's requested. Checkout itself
  doesn't read these yet -- see "Not done" in the plan doc, this is Phase 4.
- **Unrelated same-session request, same wallets domain**: peer-to-peer
  wallet transfer (`POST /wallets/transfer`) is now denied by default for
  every wallet and enabled individually per promoter (`Wallet.can_transfer`,
  migration `0019`) -- enabled today for Alessandro Pantano and Marco Web
  only. Admin toggle in "Anagrafiche Promoter".
- **Verified live end-to-end via real HTTP calls** (multipart upload
  included, not just service-layer calls): submit → verify → confirm-payment
  produced an exact 82,40E credit (80E base + 2,40E bonus) as two distinct
  wallet_transactions sharing one `reference_invoice_redemption_id`; permission
  gating, validation, and the double-confirm guard all confirmed. Test data
  created during verification was fully cleaned up (no leftover fake
  partners/redemptions or altered balances).
- **Deliberately not built**: real OCR (manual amount entry + human
  verification only, by design -- see the plan doc for why), the checkout
  spend side (Phase 4), and an automatic duplicate-invoice check.

## Session 22 — 2026-09-05 — Real domain (lialenergy.it), SMTP, public marketing site, promoter dashboard crash fix

Picked up from a previous session that had gotten stuck mid-work: the `api`
image had been left stale (built before the Session 21 wallets migration was
committed) while the database had already been stamped to that migration's
revision — `alembic upgrade head` on every `api`/`celery-worker`/`celery-beat`
restart failed with `Can't locate revision identified by 'c9a1e4b6d2f3'`.
Fixed by rebuilding all three images from current `main` and recreating the
containers; no code or migration content was wrong, only the image was out of
date.

- **SMTP wired for real**: `noreply@lialenergy.it` (Aruba-hosted mailbox) via
  `smtps.aruba.it:587` STARTTLS, verified with a live login + a real send
  through `core/email.py` before considering it done. See
  `server-migration-guide.md §4.6` (env var reference) and `§.env` section for
  the exact values.
- **Real domain replaces the temporary Hetzner rDNS hostname**, split into two
  separate sites behind two separate Let's Encrypt certs:
  - `lialenergy.it` / `www.lialenergy.it` — new static marketing/landing page
    (client-supplied HTML/CSS/JS, now under `infrastructure/marketing-site/`,
    served directly by nginx, no proxying). Added an "Accedi" nav button
    (desktop + mobile menu) linking to `https://app.lialenergy.it/login` —
    the two sites are deliberately separate, this link is the only connection
    between them.
  - `app.lialenergy.it` — the actual management app; `NEXT_PUBLIC_APP_URL` /
    `PUBLIC_APP_BASE_URL` repointed here from the temp hostname.
  - `infrastructure/nginx/nginx.conf` restructured into two `server { listen
    443 ssl; }` blocks (marketing site with its own `root`, app block kept as
    `default_server` with the old temp hostname and `_` as aliases so direct-IP
    and old-hostname access keep working). Full write-up and the current
    two-cert layout: `server-migration-guide.md §4.6`.
  - Real-world gotcha hit twice during DNS cutover: Aruba's own authoritative
    nameservers (`dns.technorail.com`, `dns2.technorail.com`,
    `dns3.arubadns.net`, `dns4.arubadns.cz`) took a while to sync a newly
    added record across their own replicas — some public resolvers (1.1.1.1,
    9.9.9.9) showed a cached positive answer for `app.lialenergy.it` well
    before any of the four authoritative servers would answer it, and Let's
    Encrypt's own validation (which queries authoritative directly) failed
    with NXDOMAIN during that window. `dig +trace` (or querying each
    authoritative NS by name directly) is the only reliable way to check
    real DNS state during a cutover like this — public-resolver results and
    third-party propagation checkers can show a false positive.
- **Real bug found and fixed**: `nginx.conf`'s `http {}` block never had
  `include mime.types;` / `default_type` — harmless while nginx only proxied
  to Next.js/FastAPI (which set their own `Content-Type`), but now that it
  also serves the marketing site's static files directly, everything
  (`.css`, `.js`, images) was served as `text/plain`, so browsers silently
  refused to apply the stylesheets — page loaded but completely unstyled.
  Fixed by adding both directives.
- **Real bug found and fixed**: `GET /api/network/mine`
  (`domains/network/router.py`) hand-built its `AgentProfileRead` response and
  never set `user_id` — a field the Session 21 wallets work had just made
  required on that schema (see Session 21's note on `CustomerRead`/
  `AgentProfileRead`), but missed updating this one call site. Broke the
  screen for every promoter (or customer-who-is-also-promoter) login with a
  Pydantic `ValidationError: Field required` surfaced to the user as "Qualcosa
  è andato storto" on switching to the promoter dashboard. Fixed by passing
  `user_id=agent.user_id` (and `is_blacklisted=agent.is_blacklisted`, also
  present on the model but not passed) — verified by re-running the exact
  query + construction for the two agent IDs seen failing in the API logs.
- Removed the "Area Demo & Test" role-autofill panel and its
  `fillTestCredentials()` helper from `apps/dashboard/app/login/page.tsx` —
  cosmetic/security cleanup for a login page real customers now see, not tied
  to any of the above.
- **Not done / left for later**: DKIM/SPF/DMARC records for `lialenergy.it`
  (mail deliverability to Gmail/Outlook inboxes rather than spam — Aruba's
  default hosted-mailbox setup was used as-is, no DNS records added for this);
  the marketing site has no analytics/tracking wired up; the vestigial
  `static.164.127.225.46.clients.your-server.de` Let's Encrypt cert still
  renews via cron but is no longer referenced by any active nginx config.
- **Also this session, design-only, zero code written**: a cashback system
  was scoped out (customer redeems a partner supplier's invoice, e.g. Eviso,
  as internal wallet credit, spendable at a configurable discount % on
  external/dropshipping/partner products only, never on internal Lial
  products). Full design + open decisions + phased plan:
  `docs/cashback-partner-invoices-plan.md` — read that file first if asked to
  continue this work, it has its own resume instructions.

## Session 21 — 2026-09-04 — Internal EUR wallet (cashback, peer transfers)

New `wallets` domain: every user (customer or promoter) gets an internal EUR
wallet with a crypto-style address (`0x` + 40 hex chars), a balance, and a
global append-only transaction ledger. Full design rationale in
`business-rules.md §Internal wallet` and `database-model.md §9` -- summary:

- **Schema**: `wallets` (`user_id` unique, `address` unique, `balance_cents`
  with a `CHECK >= 0` -- the first CHECK constraint in this codebase) and
  `wallet_transactions` (one row per transaction, not double-entry;
  `from_wallet_id`/`to_wallet_id` both nullable with a CHECK that at least
  one is set -- NULL `from` means an admin credit, NULL `to` means a
  reversal of one; `type` ADMIN_CREDIT/TRANSFER/REVERSAL;
  `reverses_transaction_id` self-FK for corrections, never mutating the
  original row; `idempotency_key` unique). Migration `0018_wallets`, new
  permission `wallet.manage` seeded for `SUPER_ADMIN`/`ORGANIZATION_ADMIN`/
  `ADMIN` only.
- **Concurrency**: a debit (peer transfer, or reversing a credit) uses an
  atomic compare-and-swap `UPDATE ... WHERE balance_cents >= :amount`,
  checked via affected-row-count -- not `SELECT ... FOR UPDATE`, matching
  this codebase's sole existing concurrency pattern (DB constraint + catch
  `IntegrityError`, see `commission_movements.idempotency_key`) rather than
  introducing pessimistic locking as new territory.
- **Endpoints**: self-service `GET /wallets/me`, `GET
  /wallets/me/transactions`, `POST /wallets/transfer` (rate-limited 20/60s
  per IP) need no permission beyond authentication -- the caller's own
  wallet is always the source/target, resolved from their own `user_id`.
  Admin: `GET /wallets/admin` (all balances), `GET /wallets/admin/{user_id}`
  (+`/transactions`) -- deliberately does NOT lazily create a wallet just by
  viewing, `POST /wallets/admin/topup` (cashback/recharge, optionally linked
  to the purchase contract via `reference_contract_id`), `GET
  /wallets/admin/transactions` (global ledger, filterable), `POST
  /wallets/admin/transactions/{id}/reverse`.
- **Frontend**: new `wallet-panel.tsx` (shared by customer and promoter
  dashboards -- balance, address with copy-to-clipboard, send form,
  transaction history) and `admin-wallets-panel.tsx` (global balances +
  ledger table, CSV export, modeled on `admin-commissions-panel.tsx`). A
  "Wallet" section (balance + "Ricarica" mini-form) was added inside the
  existing customer detail modal in `admin-customers-panel.tsx`. New
  notification types `CASHBACK_RECEIVED`/`WALLET_TRANSFER_RECEIVED`.
- **Additive fix along the way**: neither `CustomerRead` nor
  `AgentProfileRead` exposed `user_id` to the frontend before this session,
  but the admin wallet panel needs it to link a customer/promoter record to
  their wallet. Added `user_id: uuid.UUID | None` to both schemas (and their
  dict-building service functions) rather than inventing a parallel
  customer-id/agent-id-keyed wallet API surface.
- **Real bug found and fixed during testing**: the insufficient-balance and
  reversal-insufficient-balance code paths called `await db.rollback()`
  after a CAS `UPDATE` matched zero rows -- but that UPDATE is not a DB
  error (nothing was written), so the rollback was both unnecessary and
  actively broke the test suite's SAVEPOINT-based session fixture
  (`sqlalchemy.exc.MissingGreenlet` on the next query in the same test).
  Fixed by removing the rollback calls -- a business-logic check that
  changed nothing needs no undo, unlike the `except IntegrityError:` blocks
  elsewhere in this same file, which correctly do roll back a real aborted
  DB transaction.
- **Verification**: 9 new tests (`tests/test_wallets.py`) covering lazy
  creation, credit + notification, transfer happy path, insufficient
  balance (both wallets provably untouched), self-transfer rejection,
  cross-organization wallet lookup (not found), idempotency-key replay, and
  reversal (including "cannot reverse a REVERSAL"). Full backend suite:
  120/120 passing. `ruff`/`mypy` clean (one pre-existing, unrelated
  `Result.rowcount` stub false-positive, also present in
  `notifications/service.py`). Dashboard `pnpm typecheck`/`pnpm lint`/`pnpm
  build` all clean. Verified live: migration applied, `wallet.manage`
  confirmed granted to exactly `SUPER_ADMIN`/`ORGANIZATION_ADMIN`/`ADMIN` via
  direct SQL, all 9 routes present in the live OpenAPI schema and
  auth-gated (401, not 404) before login. No interactive browser
  click-through was performed this session (no browser tool available, and
  this environment holds real user data -- minting/deleting throwaway
  wallet transactions against it was judged not worth the risk for a
  session that already had strong automated + live-routing coverage).

## Session 20 — 2026-08-17 to 2026-09-04 — Go-live wipe, root promoter creation, self-service promoter activation, per-rank commission tokens, automatic monthly rank evaluation

Catch-up entry covering several working sessions that shipped without a
matching write-up here (commits `2ee7367`..`d5c52d7`, plus this session's
uncommitted work) — `business-rules.md` and `docs/server-migration-guide.md`
already had some of this, this consolidates it into the session log.

- **Login redirect + dashboard build fix (2026-08-17, `2ee7367`)**: post-login
  redirect now routes by the user's real role (from the login response), not
  a guess based on the email string. Also fixed a dashboard Docker build
  crash loop: Next's standalone output-file tracing was pruning
  `@swc/helpers` (injected by Turbopack, not a static import), causing
  `MODULE_NOT_FOUND` at container start on every fresh build — worth
  remembering if a future `docker compose build dashboard` crash-loops with
  that exact error (see `docs/server-migration-guide.md §8` for the running
  list of already-solved deployment bugs).
- **Go-live data wipe (2026-08-26)**: all demo/test data removed (contracts,
  customers, network, commissions, notifications, audit log, referral data,
  a stray test-artifact tenant) ahead of onboarding real Lial Energy users.
  Kept: the org, RBAC roles/permissions, ranks + commission plan, product
  catalog. The two real admin logins (`admin@lialenergy.it`,
  `superadmin@lialenergy.it`) had their passwords rotated that day. This is
  also the point after which `app.seed`/`app.seed.expand_demo` (§4.4/4.7 of
  the migration guide) should be treated as dev/staging-only, never run
  against the real org again.
- **Self-service "lavora con noi" promoter application (`b314fb9`,
  2026-08-25)**: a customer can request to become a promoter from their own
  dashboard; per explicit business decision this now **auto-activates**
  immediately (ACTIVE, rank S1, placed under whoever's referral link they
  registered through) instead of the old suggest-then-approve
  (PENDING_APPROVAL) flow. The only path still requiring manual admin
  approval is an agent an admin has explicitly **blacklisted**
  (`agent_profiles.is_blacklisted`, migration `0016`) re-applying. Admin
  promoter panel gained "Disattiva"/"Blacklist" (on ACTIVE agents) and
  "Riattiva"/"Rimuovi blacklist" (on TERMINATED/SUSPENDED) actions;
  `update_agent()` now syncs the PROMOTER role automatically on every status
  change — any future code touching `AgentProfile.status` directly would
  silently break that sync.
- **New "root promoter" creation endpoint**: registration is invite-only by
  design (every signup needs an existing promoter's referral code), which
  left no way to create the first, parentless promoter for a brand-new
  independent network branch. `POST /api/network/agents/root`
  (`network.approve`-gated) creates a login + ACTIVE root `AgentProfile` +
  working referral link in one step, exposed as "+ Promoter Radice" in the
  admin Promoter panel — use this (not "+ Nuovo Promoter") whenever a new
  root branch is needed.
- **Session reliability fixes**: access tokens expire in 15 minutes; silent
  refresh was missing, so any proxied call could 401 mid-task. `lib/session.ts`
  `refreshSession()` plus the `[...path]` proxy route now auto-refresh and
  retry once transparently using the 30-day refresh token embedded in the
  session cookie. Separately, raw backend JSON error bodies (`{"detail":...}`)
  were being shown verbatim in the UI; `lib/api-error.ts`
  (`friendlyApiError`/`translateErrorDetail`) is now wired into every
  fetch-based component — extend its `KNOWN_MESSAGES`/`PERMISSION_LABELS`
  maps when a new backend error string needs a friendlier phrasing, don't
  show `res.text()`/`.detail` raw.
- **Documentation/news feed**: new `documentation` domain — admin-authored
  posts (title, text, optional image/PDF/video-link attachment) published to
  CUSTOMER, PROMOTER, or BOTH, gated by `documentation.manage` (same tier as
  `products.manage`). Admin UI: "Documentazione" tab; read-only
  `documentation-feed.tsx` shared by customer/promoter dashboards, own
  "Documentazione" nav tab. Attachments live in the public `lial-media`
  bucket (marketing/training material, not sensitive documents). New table:
  `documentation_posts` (migration `0015`).
  `apps/dashboard/public/images/documentation-header.jpg` is a deliberately
  bundled local asset (not hotlinked like every other `SectionBanner` image).
- **Promoter name split**: `agent_profiles` gained `first_name`/`last_name`
  (migration `0017`) — every promoter form used to be a single "Nome e
  Cognome" field, matching how `customers` already worked was requested
  explicitly. `display_name` is now a derived "first last" string, never
  edited directly; `create_agent()`/`update_agent()` take `first_name`/
  `last_name`, not `display_name` (a real, recurring source of stale test
  helpers — see the bug fixed this session below). Any new
  promoter-name-touching form/endpoint must collect the two fields
  separately.
- **Customer/promoter dual-role UX**: a person can hold both CUSTOMER and
  PROMOTER roles at once. `GET /api/auth/me` returns LIVE roles from the DB
  (deliberately not the access token's own baked-in roles, which lag up to
  15 minutes behind an auto-activation). `AreaSwitcher`, mounted in the
  persistent app header, polls this and renders an "Area Cliente / Area
  Promoter" toggle only when both roles are present; `d5c52d7` (2026-09-03)
  added a second entry point for the same switch in the account dropdown
  menu, sharing the same `useDualRoleAreas` hook so both stay in sync
  without a re-login.
- **Per-rank commission tokens on products (`9583914`, 2026-09-03)**:
  `ProductVersion.commission_tokens` (migration `0014`) lets a product
  override the org-wide personal gettone per rank, editable from the admin
  product form. Admin catalog panel also gained "duplica" (prefills a new
  product from an existing one, including its fee/token overrides) and
  "delete" (confirmation modal, server-refused if the product already has
  contracts).
- **Automatic monthly rank evaluation (this session, uncommitted as of
  2026-09-04)**: new `commissions/services/rank_evaluation.py` — a strict,
  single-calendar-month re-evaluation of every ACTIVE agent's rank
  (promotes AND demotes, unlike the cumulative/promotion-only
  `rank_progress.py` display), run automatically by Celery Beat on day 1 of
  each month at 02:00 UTC, or on demand via `POST
  /commissions/rank-evaluation/run` (`commissions.evaluate_ranks`, migration
  `0013`). Every change is recorded in `agent_rank_history` and `audit_log`,
  and the affected agent gets a notification. See
  `business-rules.md §Automatic monthly rank evaluation` for the full
  design rationale (placeholder thresholds, same caveat as the rest of the
  career plan — `docs/open-questions.md`).
- **Real bug, found and fixed while verifying the above**: the new
  `tests/test_rank_evaluation.py` (and, once run, nine pre-existing test
  files: `test_branch_summary`, `test_commission_engine_integration`,
  `test_contract_renewal`, `test_network_isolation`, `test_registration`,
  `test_documents`, `test_contract_producer_validation`,
  `test_notifications_and_approval`, `test_rank_progress`,
  `test_promoter_reassignment`) all called
  `network_service.create_agent(display_name=...)`, a signature removed by
  the promoter name-split refactor above. Because the API container image
  has no `pytest` baked in and there is no CI, this had silently broken 52
  of the suite's tests for over a week without anyone noticing. Fixed by
  updating every call site to `first_name`/`last_name`; full suite now
  passes (105/105). **Action item**: `pytest`/the `dev` extra should be
  either baked into a dedicated test image or run in CI so this class of
  regression is caught immediately instead of by accident during an
  unrelated feature session — tracked as an open gap, not fixed this
  session.
- **`docs/database-schema.sql` regenerated (2026-09-04)**: the previous dump
  predated the `documents`, `notifications`, and now `documentation_posts`
  tables (49 tables total, up from the 46 the guide previously described) —
  it was stale independently of this session's own changes. Now dumped with
  `--no-owner --no-privileges` for portability across servers with a
  different Postgres username, regenerable via the new `scripts/dump-schema.sh`.
- **Multi-agent code review + real bugs fixed (2026-09-04)**: a full review of
  this session's diff (`/code-review high`) surfaced several real,
  independently-confirmed issues, all fixed and covered by new tests
  (`tests/test_promoter_self_service.py`):
  - **Approval-gate bypass**: `PATCH /network/agents/{id}` is gated on
    `network.manage`, which a plain `ADMIN` holds (deliberately not
    `network.approve` -- see `docs/security-model.md`). Nothing stopped that
    ADMIN from setting `status=ACTIVE` on their own `PENDING_APPROVAL`
    suggestion through this endpoint, silently granting themselves the
    PROMOTER role for it and completely bypassing the dedicated
    `network.approve`-gated `approve_agent()`. Fixed: `update_agent()` now
    refuses a `PENDING_APPROVAL -> ACTIVE` transition
    (`AgentApprovalError`, 400) -- only `approve_agent()` may perform it.
    Reactivating a SUSPENDED/TERMINATED agent ("Riattiva") is unaffected,
    still allowed under plain `network.manage`.
  - **Suspension bypass via self-service reapply**: `apply_as_promoter()`'s
    duplicate-application guard only special-cased `is_blacklisted`; an
    agent an admin set to SUSPENDED (a real, reachable status via the agent
    edit form's "Stato" dropdown -- distinct from the "Disattiva"/"Blacklist"
    buttons, which both use TERMINATED) could silently self-reactivate by
    just reapplying through "Lavora con noi," undoing the admin's suspension
    with zero admin involvement. Fixed: SUSPENDED now routes through the
    same manual PENDING_APPROVAL path as blacklisted. TERMINATED reapplying
    still auto-reactivates, unchanged -- that's the intended "Disattiva"
    behavior.
  - **`app.seed.expand_demo` crash**: same `create_agent(display_name=...)`
    signature drift as the test files above, in the actual demo-expansion
    seed script this time -- `python -m app.seed.expand_demo` (the
    documented workflow, `server-migration-guide.md §4.4`) would have raised
    `TypeError` on its very first agent. Fixed the same way.
  - **Documentation image/PDF upload cross-contamination**:
    `set_post_image()`/`set_post_pdf()` both called
    `upload_documentation_attachment()` against the SAME combined
    images-or-PDF allow-list, so a PDF uploaded through the image slot (or
    vice versa) was accepted and stored in the wrong URL field, silently
    breaking the feed's `<img>` rendering. Fixed: the function now takes an
    explicit `allowed_content_types` per call site (images-only for
    `image_url`, PDF-only for `pdf_url`).
  - **Audit trail gap**: `update_agent()`'s audit record captured
    `status`/`current_rank_id` but silently dropped `is_blacklisted` --
    blacklisting/un-blacklisting a promoter left no trace of *that specific
    change* in `audit_log`. Fixed: both are now included in
    `previous_value`/`new_value`.
  - **Wasted round-trips**: `pay_all_for_contract()` (new this session)
    looped a `db.refresh()` per movement after commit, unnecessary since the
    app's session factory already runs `expire_on_commit=False` -- removed.
  - **Known limitations documented, not fixed this session** (lower
    severity/probability, would need a larger refactor across many
    `create_agent()` callers to address safely): `create_root_promoter_with_login()`
    and `apply_as_promoter()`'s reactivation branch each call functions that
    commit internally *before* a later step (PromoterCode row / audit
    record) that could still fail -- a failure there leaves a real,
    already-committed login without its one-time password ever having been
    returned, or without the PROMOTER role granted. `rank_evaluation.py`
    issues several unbatched queries per agent (fine at current org size,
    would need batching before an org reaches hundreds of active agents).
    `apply_as_promoter`'s floor rank is hardcoded to code `"S1"` rather than
    derived from the ladder -- same category as the other rank-table
    placeholders in `docs/open-questions.md`.

## Session 19 — 2026-07-27 — Ticket search/filter, delete-when-resolved, and a proxy 204 bug found along the way

- **Ticket search & filter**: `AdminTicketsPanel` gained a free-text search
  (subject + opener name) and a category filter, alongside the existing
  opener/status filters -- all client-side over the already-fetched list
  (see `business-rules.md §Support tickets §Search, filter, and deletion`).
- **Ticket deletion, gated on RESOLVED status**: a new `DELETE
  /support/tickets/{id}` endpoint (`tickets.delete` permission, migration
  0012, granted to `SUPER_ADMIN`/`ORGANIZATION_ADMIN`/`ADMIN` only --
  deliberately not `BACK_OFFICE_OPERATOR`, same narrowing pattern as
  `network.approve`) deletes a ticket and its messages in one transaction,
  but only if `status == RESOLVED`; any other status raises
  `TicketDeletionError` -> `400`. The frontend disables the trash-icon
  button (in both the ticket list row and the detail view) for any
  non-resolved ticket and always shows a confirm dialog naming the ticket
  before calling the endpoint -- there is no direct-delete path.
- **Real bug, found and fixed**: the shared BFF proxy
  (`app/api/proxy/[...path]/route.ts`) built every response as `new
  NextResponse(body, {status: apiRes.status})`, including for a 204 No
  Content. The Fetch spec throws when a 204/205/304 response is
  constructed with a non-null body -- even `""` counts as non-null -- so
  every no-content response 500'd inside the proxy despite the upstream
  call already succeeding. This was invisible until now because the DELETE
  endpoint added this session was the **first ever 204 response** returned
  by any endpoint reachable through this proxy. Confirmed live: a ticket
  delete removed the row from the database while the UI reported
  "Impossibile eliminare il ticket." Fixed by special-casing
  204/205/304 to `new NextResponse(null, ...)`. Re-verified live after the
  fix: delete now both removes the ticket server-side and reflects it
  correctly in the UI.

## Session 18 — 2026-07-27 — Hide Organization ID from login/forgot-password

- User asked what the "ID Organizzazione" field on login/forgot-password and
  the UUIDs shown elsewhere actually are, whether they're needed, and
  whether the platform is really one organization per reseller company or
  one per individual promoter. Answer: the data model is genuinely
  multi-tenant (`organizations` table, `User` has a
  `UniqueConstraint("organization_id", "email")` -- deliberately allows the
  same email across different orgs), but only ONE organization ("Lial
  Energy Demo") exists today, confirmed live against the database. An
  organization is a whole reseller company that could license this
  platform, never an individual promoter -- promoters are just agents
  inside one org's network.
- Given that today there is exactly one org and no near-term plan for a
  second, hardcoding it in the frontend was the lowest-friction fix with no
  backend/security change. Added `apps/dashboard/lib/config.ts` exporting
  `DEFAULT_ORGANIZATION_ID`; removed the "ID Organizzazione" field from
  `login/page.tsx` and `forgot-password/page.tsx`, both now silently send
  the constant. The backend endpoints are untouched -- they still require
  `organization_id` in the request body, so multi-tenant capability is
  fully preserved. If a second organization is ever onboarded, this
  shortcut must be reverted in favor of an org picker or server-side
  resolution from the email (noted directly in `config.ts`'s comment).
  Verified live with Playwright: both pages render with no Organization ID
  field, a real login and a real forgot-password submission both succeed.

## Session 17 — 2026-07-28 — In-app notifications, promoter suggest-then-approve workflow, promoter dashboard quick-links, rebuilt commission statement

- **New promoter approval workflow**: `POST /network/agents` (admin,
  org-wide) and `POST /network/agents/recruit` (a promoter enrolling their
  own direct collaborator) now only ever create `PENDING_APPROVAL` agents,
  never immediately `ACTIVE` -- a plain `ADMIN` can "suggest" a collaborator
  but only `SUPER_ADMIN`/`ORGANIZATION_ADMIN` (the "amministratore
  principale") can turn that into a real, contract-producing agent, via new
  `PATCH /network/agents/{id}/approve`/`/reject` endpoints gated on a new
  `network.approve` permission deliberately not granted to plain `ADMIN`
  (who already holds the broader `network.manage`). Rejecting is soft
  (`TERMINATED` + a kept reason), never a hard delete. See
  `business-rules.md §New promoter suggest-then-approve workflow`.
- **New in-app notifications domain** (`app/domains/notifications/`): a
  bell icon in the header (all three dashboards, shared `app-shell.tsx`)
  with an unread badge and dropdown, plus a small unread dot on whichever
  sidebar nav item is actually relevant to a given notification (each
  `NavItem` opts in via a `notificationTypes` array, so e.g. a promoter
  approval request only lights up "Anagrafiche Promoter", never "Tutti i
  Contratti"). Clicking a notification marks it read and navigates to the
  matching tab. Polled every 25s, no WebSockets. Wired into: contract
  creation, ticket creation, both promoter-approval creation paths, and
  every commission movement generated (notifies the specific beneficiary's
  linked user, if they have a login). See `database-model.md §7` and
  `business-rules.md §Notifications` for the full fan-out design (one row
  per recipient, never per role; the triggering actor is excluded from
  their own event's notifications).
- **Promoter dashboard: quick-link buttons + rebuilt "Estratto Conto
  Provvigioni"**. Added the same large quick-access button grid the admin
  Panoramica already had (Rete Commerciale, Prodotti da Condividere,
  Movimenti Provvigioni, Simulatore, Supporto) to the promoter's own "La
  mia Azienda" landing tab. `MyCommissions` (`my-commissions.tsx`) was a
  bare list of type/amount/status before this session -- rebuilt on a new
  `GET /commissions/mine/detailed` endpoint (reuses the admin ledger's
  `admin_ledger.get_commission_movements()`, hard-scoped to the caller's
  own `agent_id`, gated on `commissions.read_own` not `commissions.approve`)
  to show, per movement: customer name, product, and a plain-language
  "provenienza" ("Prodotto da te" / "Da un tuo diretto" / "Da N livelli
  sotto di te" -- `depth_from_producer` is already relative to the viewer
  when the row is their own), with a click-to-expand full breakdown
  (contract value, base token, already-distributed-below, the same
  human-readable explanation the admin ledger shows) -- the exact same
  traceability the admin gets, just permission-scoped to "yours only".
- **Real bug fixed while building this**: the admin contract "Recensisci"
  dropdown listed every one of the 14 contract statuses regardless of the
  contract's actual current status, so picking anything the state machine
  didn't allow from that status (e.g. `DRAFT` → `ACTIVE`) always 400'd with
  "Cannot transition contract from X to Y" -- confusing since nothing in
  the UI hinted which choices were valid. Fixed by mirroring
  `state_machine.py::ALLOWED_TRANSITIONS` as a frontend constant and
  filtering the dropdown to the contract's real valid next-states; a
  contract already in a terminal state (`REJECTED`/`CANCELLED`) now shows a
  clear "reached a final state" message instead of a dropdown with no
  valid choices.

Backend: 93 tests passing (was 87 -- 6 new: PENDING_APPROVAL creation,
approve/reject + idempotent re-decision rejection, notification fan-out
excludes the actor and only reaches the right role, mark-read/mark-all-read,
contract creation notifies staff). Frontend: clean tsc/eslint/next build.
Verified live over HTTPS with a headless browser end to end: admin creates a
promoter → PENDING_APPROVAL confirmed via API → SUPER_ADMIN sees the bell
badge and the "Anagrafiche Promoter" sidebar dot → clicking the notification
navigates there and marks it read → clicking "Approva" through the real UI
flips the agent to ACTIVE; a plain ADMIN's approve attempt correctly 403s;
the promoter dashboard's quick-links and the rebuilt commission statement
(including row expansion) all render real data correctly.

## Session 16 — 2026-07-27 (same day, continued) — Clickable KPI cards, admin commission traceability + payment tracking, CSV export

- Every KPI card on the admin Panoramica is now clickable and navigates to
  the relevant tab pre-filtered to exactly the rows that produced that
  number (`Contratti attivi` → contracts list filtered `ACTIVE`, `In attesa
  di approvazione` → the same status set `reports/service.py` already sums
  for that KPI, `Respinti / cessati` → a new combined `REJECTED`+`CANCELLED`
  filter value, `Promoter attivi`/`Clienti attivi` → their respective lists
  filtered to active, `Provvigioni maturate/pagate` → the new Provvigioni
  tab pre-filtered by status).
- New admin "Provvigioni" tab + `GET /commissions/movements`
  (`commissions/services/admin_ledger.py`, gated on `commissions.approve`
  -- org-wide, so it must NOT reuse `commissions.read_branch`, which
  `TEAM_LEADER`/`PROMOTER` also hold for their own branch only): full
  traceability per commission movement -- contract, customer, promoter,
  their depth below the contract's producer, rank at calculation vs. now,
  and the exact breakdown -- all of it already computed by
  `CommissionCalculationStep` at calculation time but never exposed by any
  endpoint before this. Plus `GET /commissions/movements/by-level` for a
  per-network-level rollup (contracts/revenue/commission at each depth).
- New `PATCH /commissions/movements/{id}/pay`: the missing write path for
  `commission_movements.status`/`paid_date`, present in the schema since
  migration 0001 but never set to anything but `ACCRUED` by any code path --
  "Provvigioni pagate" had always shown €0,00 for exactly that reason.
  Rejects re-paying an already-`PAID` movement.
- CSV export (`lib/csv-export.ts`, client-side, no backend endpoint needed)
  added to Tutti i Contratti, Anagrafiche Clienti, Anagrafiche Promoter, and
  the new Provvigioni tab.

Backend: 87 tests passing (was 83 -- 4 new). Frontend: clean tsc/eslint/next
build. Verified live: KPI clicks land pre-filtered correctly; a movement was
marked paid through the real UI and the "Provvigioni pagate" total updated.

## Session 15 — 2026-07-27 (same day, continued) — Rank promotion progress ("what's missing for the next qualification")

Requested, then explicitly authorized this session ("procurati quei criteri
qualifica e falli tu" -- go get those criteria and set them yourself) after
being told the real promotion thresholds were never defined anywhere
(`open-questions.md #1`). `ranks.personal_volume_threshold_cents`/
`group_volume_threshold_cents` existed in the schema since migration 0001
but were always 0, never read anywhere -- populated with reasonable,
ascending, demo-scale placeholder figures (migration 0010 +
`seed/ranks.py`), explicitly documented as not confirmed Lial Energy policy.
New `GET /network/agents/{id}/rank-progress` compares an agent's cumulative
(lifetime, not evaluation-windowed) contract value against the next rank's
thresholds -- personal (self-produced) and group (entire downline including
self) -- surfaced as two progress bars in `PromoterAziendaPanel`, shared by
both the promoter's own "La mia Azienda" tab and the admin's per-promoter
"Apri Rete" drill-down. An agent already at the top rank shows "qualifica
massima raggiunta" instead. Also fixed in this session: the promoter header
box showed the raw rank UUID instead of the rank code (backend never
returned `rank_code` on `GET /network/mine`) and was narrower than the
content below it.

Backend: 83 tests passing (was 79 -- 4 new). Frontend: clean tsc/eslint/next
build. Verified live: migration applied, real threshold figures on all 12
ranks, correct progress data for both a mid-tier and a max-tier agent.

## Session 14 — 2026-07-26 (same day, continued) — Sensitive document uploads (private storage), contract IBAN, demo data expanded to 12 full levels, network tree click-through popup

Continuation of another large multi-part request. All items below were built,
tested, and verified live:

- **Sensitive contract documents, built end-to-end** (identity, fiscal code,
  utility bill, and — for companies/condominiums — chamber-of-commerce
  registration). New `documents` domain (`app/domains/documents/`): a
  `Document` model with an explicit state machine
  (`PENDING_REVIEW → APPROVED/REJECTED`), org- and contract-scoped everywhere,
  snapshotting the uploader's role at upload time (same "frozen at the moment
  it happens" pattern used elsewhere in this project). Endpoints:
  `POST /contracts/{id}/documents` (multipart, customer-own-contract-or-staff),
  `GET /contracts/{id}/documents` (one row per *required* type for that
  customer's kind, `null` if not yet uploaded — so the UI can show "missing"
  as a first-class state, not just absence of data), `GET
  /documents/{id}/url` (short-lived presigned view link), `PATCH
  /documents/{id}/review` (admin/back-office only, approve or reject with a
  note). Required types are `IDENTITY`/`FISCAL_CODE`/`UTILITY_BILL` for
  everyone, plus `CHAMBER_OF_COMMERCE` for `COMPANY`/`CONDOMINIUM` customers.
  Both the customer (their own contract) and admin/back-office (any contract,
  e.g. "the customer emailed me the file, I'm uploading it for them") can
  upload; only admin/back-office can review. New RBAC permissions
  `documents.upload` (also granted to `CUSTOMER`) and `documents.review`,
  seeded via an idempotent data migration (`0009`) using the same
  `on_conflict_do_nothing()` pattern as migration `0006` — declaring a
  permission in code alone never reaches an already-seeded live database.
- **Private document storage — the actual security requirement driving this
  feature**: the user was explicit that these files must never be reachable
  by search engines or anyone outside the organization, "solo dall'amministratore",
  with a real protected storage design, not just "don't link to it". Built as
  a *second*, entirely separate MinIO bucket (`lial-documents`) alongside the
  existing public `lial-media` bucket from Session 13 — this one gets **no
  bucket policy at all** (MinIO buckets are private-by-default; the fix here
  was writing *less* code, not more). The only access path is a server-side,
  time-limited (5-minute) presigned SigV4 URL
  (`storage.py::generate_presigned_document_url()`), generated after the
  `documents.download`/ownership check already ran — never a direct or
  guessable link. New nginx location `/lial-documents/` reverse-proxies to
  MinIO with a **hardcoded** `Host: minio:9000` header (not `$host`) — SigV4
  signatures are computed over the exact host the signing client used
  (MinIO's internal Docker name), so forwarding the public domain's Host
  instead would make every presigned URL fail with `SignatureDoesNotMatch`
  regardless of validity; this is the same "static `proxy_pass` target,
  documented trade-off" pattern used for `/backend/` and `/media/` in earlier
  sessions. Verified live, all three ways: (1) a valid presigned URL returns
  the real file (200), (2) the identical path with the signature query
  string stripped off returns MinIO's own `403 AccessDenied`, and (3) listing
  the bucket directly also 403s. No indexable, guessable, or unauthenticated
  path to a sensitive document exists anywhere in this design.
- **Real bug found and fixed — every PATCH-based save in the app had been
  silently broken since the feature it belonged to was first built**: the
  BFF's generic proxy (`app/api/proxy/[...path]/route.ts`) only ever
  implemented `GET` and `POST` handlers. Discovered while wiring the new
  `PATCH /documents/{id}/review` endpoint, which 405'd through the proxy;
  checked whether this was a new regression by hitting `PATCH
  /api/proxy/customers/{id}` directly — also 405, confirming this had been
  broken for customer edit, promoter edit, product edit, supply-point label
  edit, and (from this same session) contract IBAN update, the entire time
  those "save" buttons existed. Fixed by extracting a shared
  `proxyWithBody()` helper and adding real `PATCH`/`PUT`/`DELETE` handlers
  alongside the existing `POST`. Verified live, before and after: `PATCH
  /api/proxy/customers/{id}` went from 405 to 200 with the fix in place.
- **Contract IBAN**: `contracts.iban` column (migration `0009`, basic format
  validation — `^[A-Z]{2}[0-9A-Z]{13,32}$`, not a full mod-97 checksum),
  editable by the customer on their own contract or staff on any contract via
  `PATCH /contracts/{id}/iban`. Added to the admin's new-contract form and to
  an inline editor on the customer's own contract card.
  `ContractDocumentsPanel` (new shared component) renders the
  required-document checklist with upload/view/approve/reject, wired into
  both the customer's contract card (upload-only) and the admin's contract
  review modal (adds approve/reject with a note).
- **Demo data expanded to a real, fully-branching 12-level tree**: the live
  network had already reached depth 12 from earlier ad-hoc testing, but as
  two bare, single-file chains (2 people at most depths) — not a tree anyone
  could look at and understand. An additive script
  (`app/seed/expand_demo.py`, run once against the *existing* live
  organization, never a fresh seed) added 30 more agents broadening every
  level from 0 to 12 (new root branches, extra siblings at mid-tree and
  deep-tree nodes) and 50 more customers with contracts spread across the
  whole tree (old and new agents alike) in a realistic status mix — active,
  draft, submitted, under review, rejected, cancelled, and
  `DOCUMENTS_PENDING` (some with a partial document upload, some with none at
  all, to demonstrate the "missing documentation" flow end-to-end). Resulting
  live totals: 71 agents across 13 depth levels (0–12), 56 customers, 57
  contracts, 90 documents (85 approved, 5 still pending review). Every row
  this script creates is tagged for easy removal before production —
  `promoter_code` starting with `DEMO-`, customer email domain
  `@demo-expansion.lial`, contract notes containing the literal
  `[DEMO-EXPANSION]` — see `server-migration-guide.md` for the deletion
  queries keyed off these markers.
- **Network tree: click-through detail popup**. Every node in both the
  admin's org-wide tree and a promoter's own branch view now has a clickable
  name + info icon (propagated through `TreeNodeRenderer` via a new
  `onNodeClick` prop) that opens `NetworkNodeDetailModal`, showing: people
  below that node, levels below, contract counts by bucket (in progress,
  closed, rejected), total value created, and a per-contract table
  (customer, product, status, value). This reuses the existing
  `get_branch_summary`/`get_branch_contracts` service functions rooted at
  *whichever* node was clicked, not just the branch root — no new backend
  concept needed, since the existing ABAC check (`_assert_branch_access`)
  already permits any ancestor to query any descendant's branch. One
  genuinely new piece: **"provvigione presa da me per quel contratto"** — the
  commission the *specific viewing user* earned from each contract, which is
  different from that contract's total commission across every beneficiary
  in the multilevel plan. `get_branch_contracts()` now accepts an optional
  `viewer_agent_id` and returns a `my_commission_cents` field per contract
  (`null`, not `0`, when the viewer has no agent profile at all — e.g. an
  org admin browsing someone else's branch, who was never a commission
  beneficiary; distinguishing "not a beneficiary" from "earned zero" was
  deliberate). Verified live: a promoter viewing a contract 12 levels down
  their own tree correctly saw their own smaller cut (e.g. €25 of a €95
  total commission payout), while an org admin viewing the same contract saw
  `my_commission_cents: null`.
- Backend: 79 tests passing (was 65 at the end of Session 13 — new tests for
  the documents domain: required-document-types-per-customer-kind, upload +
  read-back, unknown-document-type rejection, approve/reject, presigned-URL
  properties, and org-scoping). Frontend: clean `tsc --noEmit`, clean
  `eslint`, clean `next build`. Verified live over HTTPS: the full
  document-upload → presigned-view → approve round trip (both as the
  uploading customer and as the reviewing admin), the private bucket
  rejecting every unsigned/public request, IBAN update from both the
  customer and admin side, the expanded 12-level tree's real counts via the
  live API, the tree popup's branch-summary/branch-contracts data for both
  an admin and a promoter viewer (including the `my_commission_cents`
  difference above), and that pre-existing isolation still holds — a
  customer still gets 403 on another customer's contract documents, a
  promoter still gets 403 on a branch they're not an ancestor of.

## Session 13 — 2026-07-26 (same day, continued) — Network tree bug fix, password reset, photo uploads (customer/promoter/product), promoter reassignment, security hardening, three real nginx/MinIO bugs found and fixed

Continuation of another large multi-part request. All items below were built,
tested, and verified live:

- **Real bug fixed -- network tree navigation**: `network/service.py::get_branch()`
  had no `ORDER BY` and the frontend (`branch-visualizer.tsx::buildTree()`)
  assumed the flat row list came back in pre-order traversal order to
  reconstruct the parent/child hierarchy. Postgres never guarantees that for a
  plain `WHERE id IN (...)`, so whenever it didn't, most of the tree silently
  failed to attach to its real parent -- exactly the reported symptom ("only
  see the first name, opening a level shows nothing"). Fixed by joining
  `network_nodes.direct_parent_agent_id` into `BranchMemberRead` as
  `parent_agent_id` and rebuilding the tree strictly from that field via a
  map, never row order. Also changed `TreeNodeRenderer` so each level starts
  collapsed by default (only the root/level-1 boundary starts open), giving
  real "open one level, then the next" navigation instead of one giant
  all-levels-expanded dump -- `forceOpen` still cascades for the admin's
  "espandi tutto"/search.
- **Referral share link display bug fixed**: the `/r/[code]` landing page read
  the `product` query param (a raw UUID) for "Offerta consigliata" display --
  the share button had always set BOTH `product` (id) and `product_name`
  (the actual name) but the landing page only ever read the former. Now shows
  the name prominently with the id small below, matching the "name
  prominent, id small below" rule applied everywhere else.
- **Password confirmation** added to the referral registration form
  (client-side match validation) and to the new reset-password form.
- **Password recovery, built end-to-end**: `password_reset_tokens` table
  (migration `0007`), `POST /auth/forgot-password` (always enumeration-safe)
  and `POST /auth/reset-password` (single-use, 60-min expiry, revokes every
  session on success), `/forgot-password` and `/reset-password` pages. Real
  SMTP delivery when configured (`core/email.py`, new `SMTP_*` settings);
  when not configured, the reset link is logged to the API process log only
  -- deliberately never to `audit_log` or anywhere a web-UI role could read
  it (that would let staff take over any account). Verified live: request →
  log fallback → reset → new password works → old password rejected → token
  correctly single-use.
- **Rate limiting** (`core/rate_limit.py`, Redis fixed-window per client IP,
  fails open) on login/register/forgot-password/reset-password. Required
  fixing uvicorn to run with `--proxy-headers --forwarded-allow-ips` so
  `request.client.host` reflects the real visitor behind nginx instead of
  nginx's own container IP -- previously every request looked like it came
  from the same source, silently defeating both rate limiting and
  `audit_log.ip_address`. Verified live: 11th login attempt in a window
  correctly 429s.
- **`/backend/docs` gating**: `ENABLE_API_DOCS` setting (default true, keeping
  today's behavior) controls whether `/docs`/`/redoc`/`/openapi.json` exist at
  all -- set false for a real production deployment.
- **Baseline nginx security headers**: `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Strict-Transport-Security`. No CSP
  yet (would need a nonce-based policy to not break Next.js's inline
  hydration scripts -- tracked as a follow-up, not guessed at).
- **Real bug found and fixed -- `/backend/*` returned 500 on every request**:
  discovered while verifying the docs-gating control actually worked.
  `location /backend/` combined a `rewrite ... break` with a VARIABLE in
  `proxy_pass` -- a genuine nginx bug (confirmed live, not theoretical),
  distinct from the prefix-stripping behavior a variable-based `proxy_pass`
  actually has (it forwards the ORIGINAL unstripped URI, which was the first,
  also-broken fix attempt). Resolved with a static `proxy_pass` target for
  this location specifically (trading the dashboard proxy's zero-downtime
  re-resolution for simplicity, acceptable since `/backend/` is developer
  convenience, not the app's own request flow).
- **Photo uploads, built end-to-end** for customers, promoters, and products:
  new public-read MinIO bucket `lial-media` (`core/storage.py`), separate
  from the private documents bucket, auto-created with its anonymous-read
  policy on API startup. Served to browsers via a new nginx `location
  /media/` proxying directly to MinIO (MinIO itself isn't internet-reachable).
  New `photo_url` columns on `customers`/`agent_profiles` (migration `0008`),
  upload endpoints (`POST .../photo`, multipart), a shared `PhotoUpload`
  React component (preview, fallback person icon when no photo), wired into
  the customer edit modal, a brand-new promoter edit modal (promoters were
  not editable in the admin UI at all before this), and the product edit
  modal (alongside the existing paste-a-URL field, with a live thumbnail
  preview).
  - **Two real infrastructure bugs found and fixed while wiring this up**:
    (1) `S3_ACCESS_KEY`/`S3_SECRET_KEY` in `.env` were NOT actually identical
    to `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` (same length, different
    values -- silently wrong since nothing had ever authenticated against
    MinIO with them before this session). (2) MinIO had no `MINIO_REGION`
    set (defaults to `us-east-1`) while the app signs requests for
    `eu-central-1`, breaking SigV4 signature verification regardless of
    credentials. Both fixed; documented in `server-migration-guide.md §8` so
    a fresh server setup doesn't reintroduce either.
  - The BFF's generic proxy route (`/api/proxy/[...path]`) needed a fix too:
    it unconditionally read every POST body as text and forced
    `Content-Type: application/json`, which would have corrupted a multipart
    upload's binary body and dropped its boundary. Now branches on the
    incoming content-type.
- **Admin: customer edit graphically improved** (photo upload section) and
  a working "Riassegna Promoter" control wired to a new
  `POST /customers/{id}/reassign-promoter` endpoint
  (`referral/service.py::reassign_customer_promoter()`) -- the customer
  keeps *some* promoter always; reassignment is rejected if there's no
  existing attribution to correct, or if the target is the same promoter
  already attributed. Writes an `attribution_corrections` row (a
  pre-existing, previously-unused schema table, same story as
  `customer_attributions` before Session 10).
- **Admin: customer view -- contract summary table** added (product, supply
  point, status color-coded green/amber/red/grey, expiry date), clicking a
  row expands an inline detail (created/activated dates, notes, id) --
  simpler than a second stacked modal, still gets to "click through to the
  contract's detail" without a dedicated contract-detail route that doesn't
  exist yet.
- Backend: 57 tests passing (was 46 at the end of Session 12 -- new tests for
  the `get_branch()` parent-linkage fix, the password reset flow, and
  promoter reassignment). Frontend: clean `tsc --noEmit`, clean `eslint`,
  clean `next build`. Verified live over HTTPS: photo upload for all three
  entity types (with the uploaded object confirmed publicly fetchable
  through nginx), promoter reassignment both directions with the audit trail
  confirmed in the database, the full password-reset round trip, and the
  rate limiter actually triggering a 429.

## Session 12 — 2026-07-26 (same day, continued) — Contract expiry/renewal, supply point labels, support tickets, network stats + drill-down, admin-to-promoter notes, font + section banners

Continuation of another large multi-part request. All items below were built,
tested, and verified live (not deferred):

- **Contract renewal bug fix**: `RENEWED` was a dead-end state in
  `contracts/state_machine.py` (empty `ALLOWED_TRANSITIONS` set) -- a renewed
  contract could never be renewed again the following year, suspended,
  cancelled, or left to expire. Since energy contracts renew every year of
  their life, not once, this was a real defect, found by reading
  `business-rules.md §Renewals` before writing any code. Fixed: `RENEWED` now
  has the same onward transitions as `ACTIVE`; `EXPIRED → RENEWED` also added
  (reviving a lapsed contract).
- **Contract term/expiry**: `product_versions.contract_duration_months`
  (nullable, no ORM-level default -- see the "real bug found by a test" note
  below), `contracts.activated_at`/`expires_at` (migration `0005`). Set/reset by
  `transition_contract()` on every entry into `ACTIVE`/`RENEWED`, computed via a
  stdlib `_add_months()` helper (no dateutil dependency). Existing live
  ACTIVE contracts backfilled from their real `contract_status_history`
  timestamp, not an approximation.
  - **Real bug found while writing the test for "product with no duration
    leaves expires_at null"**: the model had `mapped_column(..., default=12)`.
    SQLAlchemy's Python-side column default fires even when the ORM
    constructor is given an *explicit* `None` -- it can't distinguish "field
    omitted" from "field explicitly nulled" once the value reaches Core's
    insert-defaults processing. This would have silently turned every
    DIGITAL/PHYSICAL product's "no renewal" `None` into `12`. Fixed by
    removing the model-level default entirely; "12 unless told otherwise"
    now lives only in `ProductCreate`/`ProductVersionCreate` (the Pydantic
    layer, where omitted vs. explicit-null are still distinguishable).
- **Supply point labels**: `supply_points.label`, auto-computed from
  energy_type + address when not given explicitly (e.g. "Energia elettrica -
  Via Roma 12, Milano"), always editable after. Generalizes the "name
  prominent, id small below" rule that already applied to customers/products/
  network agents to the one remaining raw-ID display the user pointed out
  (POD/PDR codes shown bare).
- **Contract list enrichment**: `ContractRead` gained `product_name` and
  `supply_point_label` (denormalized, populated by a new
  `contracts/service.py::to_read_dicts()` bulk join) so every contract list in
  the app shows names, not raw UUIDs, without each caller re-deriving it.
- **Admin contract list**: expiry/renewal column with urgency color-coding
  (red if past due, amber if <30 days), year filter dropdown for "storico
  separato per anni".
- **New `support` domain**: `Ticket`/`TicketMessage` models (migration `0006`,
  which also seeds the new `tickets.create`/`tickets.respond` permissions and
  grants them to existing roles in the live DB -- a genuine data migration,
  not just schema). Customer/promoter open tickets and see only their own
  (`tickets.create`); staff see and reply to every ticket in the org
  (`tickets.respond`), and a staff reply on an `OPEN` ticket auto-transitions
  it to `IN_PROGRESS`. Replaced the previous fake "Supporto & Assistenza" form
  in the customer page (generated a random ticket number client-side, did
  nothing real) with the real thing.
- **Promoter/admin network + contract statistics**: `get_branch_summary()`'s
  `totals` gained `contracts_closed`/`contracts_rejected`/`contracts_pending`/
  `contracts_in_progress`/`levels_below`/`people_total`/`contracts_by_status`.
  New `get_organization_network_levels()` (whole-org headcount per depth-from-
  own-root -- no single root_agent_id exists for a whole org, unlike a
  promoter's branch) powers a new admin-only `GET /network/organization/levels`
  endpoint. Promoter "La mia Azienda" panel got a recharts bar chart + clickable
  per-level drill-down; admin overview got an analogous whole-company widget.
- **Admin notes surfaced to promoters**: `get_branch_contracts()` now also
  returns the latest non-null `contract_status_history.notes` per contract
  (`admin_note`) -- what an admin wrote when moving a contract to e.g.
  `DOCUMENTS_PENDING` now shows directly under that contract in the promoter's
  network-contracts table, folded into the "Contatta" mailto body too.
- **Font**: replaced Outfit with Inter (`next/font/google`) across the whole
  dashboard -- a more standard, professional admin/dashboard typeface.
- **Section header banners**: new reusable `SectionBanner` component, one
  small (h-20/h-24) themed decorative image per major tab across
  admin/promoter/customer dashboards (energy, customers, network, products,
  commissions, support), sourced from Wikimedia Commons (same method used
  earlier for product photos) with a dark gradient overlay for contrast.
  Purely decorative -- degrades silently if the image is slow/unreachable.
- Backend: 46 tests passing (was 14 at the start of this session -- 5 new test
  files/additions covering the renewal chain, expiry computation, supply point
  label defaults, the support ticket domain, and the network stats). Frontend:
  clean `tsc --noEmit`, clean `eslint`, clean `next build`. Verified live over
  HTTPS with real authenticated sessions (admin/promoter/customer demo logins)
  for every new endpoint.

## Session 11 — 2026-07-26 (same day, continued) — Promoter "azienda" view, referral sharing + invite-only registration, real contract creation form, product types

Large, multi-part user request. Scoped deliberately: built the concrete,
safely-implementable pieces in full (tested, verified live); explicitly
deferred the full PIN/email-verification registration refinement rather than
fake it, since this project has no email-sending infrastructure at all yet.

**Header/logo overlap bug (also user-reported).** Root cause: the top header
was a full-width block using left *padding* to visually clear the sidebar, but
its semi-transparent background still extended under the sidebar at `z-40`
(above the sidebar's `z-30`), covering the logo. Fixed with `margin-left`
instead of padding, so the header's box genuinely starts after the sidebar
instead of merely indenting its content.

**Promoter "azienda" dashboard (new default landing tab).** New backend
aggregations in `network/service.py`: `get_branch_summary()` (per-agent and
per-level contract-count/commission-total rollup across a promoter's whole
downline, using the existing branch/closure data -- no new tables) and
`get_branch_contracts()` (flat, contract-level rows linking customer name/
email, product name, status, and commission earned -- the "collegamento tra
cliente/prodotto/stato/guadagno" the request asked for). Both reuse the same
branch-ownership ABAC check as the existing `/branch` endpoint (factored into
a shared `_assert_branch_access()` helper). New `PromoterAziendaPanel`: KPI
cards, per-level table, per-agent table (contracts total/processed/in-progress/
problem, commission), and a contract list with a **Contatta** button
(`mailto:`, pre-filled subject/body for problem contracts) so a promoter can
act on "documenti mancanti" without leaving the page.

**Referral link sharing.** `promoter_codes`/`referral_events`/
`referral_sessions`/`customer_attributions` existed since Session 1 but had no
live write path beyond the public click-resolver -- orphaned tables. Added
`referral_service.get_or_create_promoter_code()` (reuses the agent's existing
`promoter_code` as the referral code, created lazily on first request) and a
new authenticated `GET /referral/mine` endpoint (on a **separate** router from
the public `GET /r/{code}` -- `/r/mine` would otherwise collide with
`/r/{code}` where `code="mine"`). `CustomerProductsPanel` gained an optional
`referralCode`/`organizationId` prop: when set, each product card gets a
**Condividi** button that copies a link straight to that product, pre-attributed
to the sharing promoter. The promoter dashboard header also has a generic
"Condividi il tuo link" button.

**Invite-only public registration.** New `POST /auth/register`
(`auth/service.py::register_with_referral()`): validates the referral code
*first* (before creating anything, so an invalid/expired code never leaves a
half-created account), then creates the User + role grant + Customer +
profile/company + `CustomerAttribution` in one transaction, one commit --
closed circuit enforced at the data layer, not just the UI ("nessuno può stare
senza promoter che lo invita"). New public page `/r/[code]` (reads `org` +
optional `product`/`product_name` query params) with a single-step
email+password+profile form, and two public (no session) BFF proxy routes.
**Explicitly not built**: PIN-via-email verification, forced profile
completion on first login, promotion memory across logins, multi-activation
with location choice -- this project has zero email-sending infrastructure
today, and faking "email sent" or skipping verification silently would be
dishonest; this is real, scoped follow-up work, not cut corners.

**Real contract creation form.** Previously four raw UUID text inputs typed
by hand. New `AdminCreateContractPanel`: toggle between an existing customer
(dropdown, then a dropdown of *that* customer's supply points) or a new one
(kind, fiscal code/VAT, first+last name or company name, email, mobile, PEC,
plus inline supply-point address fields -- creates the customer and supply
point via the existing endpoints, then the contract), a dropdown for the
offer (not a UUID), a dropdown for the promoter/venditore, and an optional
free-text note. `notes` added to `Contract` (new column, migration `0004`)
and `pec` added to `Customer` (same migration) -- both exposed end-to-end
(schemas, service, create form, edit form, detail popup).

**Product types.** `Product.energy_type` was `NOT NULL`, meaning every
product had to pretend to be an energy contract. Added `Product.product_type`
(`ENERGY_CONTRACT`/`DIGITAL`/`PHYSICAL`/`SUBSCRIPTION`, default
`ENERGY_CONTRACT` for every existing row) and relaxed `energy_type` to
nullable (migration `0004`, same one as notes/pec). Admin create/edit forms
show the energy-type field only when `product_type=ENERGY_CONTRACT`. Catalog
badges (admin grid, customer/promoter shop) show the right label for either
case.

**Tests.** 7 new tests, all against real Postgres: 5 for registration
(valid referral succeeds and attributes correctly, invalid code rejected with
no half-created account, duplicate email rejected, expired code rejected,
`get_or_create_promoter_code` is idempotent) and 2 for the branch aggregations
(contract counts/commission totals correct per agent, contract-level detail
correctly links customer/product/status/commission). Full suite: **40/40
passing**.

Verified live end-to-end over the real HTTPS deployment: full contract
creation (new customer → supply point → contract with notes) through the BFF
proxy; promoter `branch-summary`/`branch-contracts`/`referral/mine` through an
authenticated promoter session; the public `/r/{code}` page resolving a real
promoter code and a real registration completing (new user could log in
immediately after); header/logo fix present in rendered HTML.
`tsc`/`eslint`/`next build` clean, full backend test suite green, both images
rebuilt and redeployed.

## Session 10 — 2026-07-26 (same day, continued) — Expired-session crash fix, admin network tree, deep seed, product photos, customer view/edit

**Bug fix (user-reported: "se apro il sito mi dice rebuild pagina"):** `/admin`,
`/promoter`, `/customer` all threw Next.js's generic 500 error page for any
session older than 15 minutes (the access token TTL; no silent refresh yet).
`apiFetch()` throws on a non-2xx response and none of the three pages caught
it. Root cause confirmed live by forging a `Cookie: lial_session=...` header
carrying a token the API actually rejects with 401. Fixed with a new
`apiFetchOrRedirectToLogin()` that redirects to `/login` on 401 instead of
throwing -- first attempt also tried to clear the stale cookie, which threw a
*different* 500 ("Cookies can only be modified in a Server Action or Route
Handler" -- illegal from a plain Server Component render), caught while
testing the fix live and fixed by leaving the stale cookie in place (a
subsequent login just overwrites it).

**Admin network tree restored + rebuilt properly.** The admin dashboard had
no org-wide network view at all (only the flat `AdminPromotersPanel` table) --
Fase 5 from `admin-dashboard-plan.md`, not yet built, which is what the user
was actually missing ("non vedo più l'albero"). Extracted the tree-rendering
pieces from `branch-visualizer.tsx` into a shared `components/network-tree.tsx`
(`TreeNodeRenderer`, `LevelLegend`, depth-color logic) and built a new
`AdminNetworkPanel` on top of it: fetches the existing org-wide
`GET /network/agents` list, builds a full forest client-side from
`direct_parent_agent_id` pointers (multiple independent root branches, not
just one), with search/highlight and expand-all/collapse-all controls (starts
collapsed for a big org tree, matching "navigare la rete nei vari livelli").
New "Rete Commerciale" tab + a quick-link button on the overview panel.

**Network depth extended to 12 levels with real agents at every level.** The
existing demo network topped out at depth 5 and was a pure linear chain (one
agent per level, no branching) -- neither satisfied "albero a 12 livelli" nor
"ogni livello deve avere uno o più clienti". Seeded 19 new agents directly via
`network_service.create_agent()` (same code path the API uses): one sibling
added at each of levels 1-5 (so those levels have 2+ agents instead of 1), and
7 new levels (6-12) added below the existing leaf, 2 agents per level. Verified
live: `network_closure` now shows depth 0-12, every level with ≥2 agents,
41 agents total org-wide (was 22).

**Product renames + real photos.** "Gas Semplice" -> "Luce Family", "Luce
Flex" -> "Luce Company" (both via the existing `PATCH /products/versions/{id}`
-- note: this only renames the display name, the underlying `energy_type`
column on `Product` has no update endpoint, so "Luce Family" is still
technically a GAS-typed product under the hood; flagged, not silently
pretended otherwise). All 5 active products got a real, free, theme-matched
photo sourced from Wikimedia Commons (public domain / CC-licensed, no API key
needed, verified reachable before use): glowing Edison bulbs for Luce
Semplice, a solar-roofed house for Luce Family, a glass office tower for Luce
Company, an offshore wind farm for Luce Green 100%, a mixed solar+wind
building for Energia Circolare PMI.

**Customer admin CRUD: view/edit icons.** `AdminCustomersPanel` rows gained a
"Mostra" icon (popup with full customer detail -- addresses, supply points,
fiscal data, via the existing `GET /customers/{id}`) and a "Modifica" icon
(edit form via the existing `PATCH /customers/{id}`, previously wired
backend-side with no UI). Deliberately did NOT add a delete action: no soft-
delete concept exists on `Customer` (no status column, unlike `AgentProfile`/
`Product`) and no delete endpoint exists; a real delete would either need a
new schema concept or risk orphaning `contracts`/`supply_points` FKs --
inventing one silently would violate "no fake buttons without real
functionality." Verified RBAC already correctly restricts `customers.update`
to ADMIN/BACK_OFFICE_OPERATOR-tier roles -- PROMOTER/TEAM_LEADER only have
`customers.read`/`customers.create`, matching "solo amministratore può
editare" (no code change needed there, confirmed by reading `rbac/models.py`).

Verified live end-to-end over the real HTTPS session for every piece above.
`tsc`/`eslint`/`next build` clean.

## Session 9 — 2026-07-26 (same day, continued) — Names above IDs, product edit + VAT, shop as customer home

User-driven: lists showing raw UUIDs must show the real associated name above
the (still-present, small) id; the shop needs real electricity examples and a
proper create/edit flow with photo/price/VAT; the customer's home should be
the shop, not the contract list.

- [x] Admin contract list and the transition modal now show the customer's
  real name (fetched via a `customers` lookup, same pattern as
  `AdminPromotersPanel`'s sponsor lookup) with the UUID kept small underneath,
  instead of two raw UUID columns.
- [x] Customer's own contract cards now show the product's real name (from a
  `product_version_id -> name` lookup built off `GET /products`) as the
  heading, with the contract UUID demoted to small mono text below it.
  `AdminCustomersPanel`/`AdminPromotersPanel` already led with real names
  (verified, no change needed).
- [x] Backend: `ProductVersion.tax_configuration` (existing, previously-unused
  JSONB column) now carries a `vat_percentage`, exposed as a top-level field
  via `ProductVersionRead.from_version()` (a `from_attributes=True` model
  can't compute a field out of a JSONB blob, so this replaces `model_validate`
  at all 4 call sites) and accepted on create/update. No migration needed --
  the column already existed, unused.
- [x] `AdminProductsPanel` gained a real Edit flow (`PATCH
  /products/versions/{id}`, already existed backend-side but had no UI) --
  same form fields as create, refactored into a shared `ProductFormFields`
  component. VAT % field added to both create and edit.
- [x] Shop now has 3 real, distinct electricity offers (`LUCE-STD`/"Luce
  Semplice", plus two new ones created live via the API: `LUCE-FLEX`/"Luce
  Flex" -- indexed/variable rate, and `LUCE-GREEN`/"Luce Green 100%" --
  renewable, 12-month fixed price). The `TEST-SMOKE` product created as a
  throwaway artifact during Session 8's live verification was retired
  (`status="RETIRED"`) so it no longer appears in admin or customer views.
- [x] Customer app: "Shop" (the products panel) is now the first nav item and
  the default landing tab, per "l'home dei clienti deve mostrare lo shop" --
  previously "I miei Contratti" was both first and default.

Verified live: customer session shows exactly 3 ACTIVE electricity products
with correct prices/VAT through the real BFF proxy path; admin session's
`/customers` lookup returns real display names that the frontend map resolves
correctly. `tsc`/`eslint`/`next build` clean, dashboard rebuilt and redeployed.

## Session 8 — 2026-07-26 (same day, continued) — Commission-trigger audit + fixes, admin quick-links, orange brand pass

Two independent pieces of work, done back to back.

**1. Full audit of "paid contract → commission distribution", per explicit user
request.** Report: `docs/paid-contract-commission-audit.md`. Method: read the
actual running code first, then compared against `docs/business-rules.md` and
`docs/commission-engine-specification.md` to find real gaps rather than assuming
the docs were accurate.

Confirmed correct (no changes needed): the producer's ancestor chain is built
from real `network_snapshot_nodes` data frozen at activation (no placeholders);
all N levels are walked (no hardcoded cap -- the finite 12-rank ladder makes any
cap moot); the entrepreneurial-difference algorithm is incremental and correctly
tested (7 unit tests, all green); `PaymentConfirmed` (the `PAID` transition) does
**not** trigger commission calculation, only `ContractActivated`/`ContractRenewed`
do -- this matches `business-rules.md` line 55-56 exactly and is intentional, not
a bug.

Five real problems found and fixed:
- [x] **Problem #1 (critical)**: `create_contract()` accepted `producer_agent_id`
  from the client with zero validation. An invalid/nonexistent id produced an
  empty network snapshot, which made `run_calculation_for_contract()` silently
  `return None` -- no error, no record, no audit entry, event marked processed
  as if nothing was wrong. A contract could activate and pay nobody, forever,
  with no trace. Fixed: `create_contract()` now verifies the agent exists,
  belongs to the organization, and is `ACTIVE`, raising `InvalidProducerAgentError`
  (→ HTTP 400) otherwise. Defense in depth: an empty ancestor chain at
  calculation time (any other cause) now writes a `CommissionCalculation` with
  `status="FAILED"` plus an audit log entry instead of silently skipping.
- [x] **Problem #2 (serious)**: `process_pending_outbox_events()` had no
  try/except around the calculation call -- one failing event (a "poison pill")
  aborted the whole batch, blocking every *other* unrelated contract's
  commissions too, retried (and re-blocking) every minute forever. Fixed: each
  event is now processed in isolation (event data extracted to plain values up
  front, since a rollback after a failure expires the whole session's identity
  map and a later bare attribute read on another event's ORM object would itself
  crash with `MissingGreenlet` -- hit this for real while writing the isolation
  test, see below); a failure is logged, audited, and the loop continues.
- [x] **Problem #3 (medium)**: the `(contract_id, trigger_event_id)` idempotency
  check in `run_calculation_for_contract()` was application-level only
  (SELECT-then-INSERT), with a real race window on overlapping dispatches.
  Fixed: DB-level `UniqueConstraint` (migration `0003`) plus explicit
  `IntegrityError` handling at the actual insert point (the `db.flush()` right
  after `db.add(calculation)`, not just the later `db.commit()` -- the first
  attempt at this fix only wrapped the commit and missed the real conflict
  point, caught by the concurrency test below).
- [x] **Problem #4 (medium)**: nothing surfaced a contract stuck at `PAID` or
  `ACTIVATION_PENDING` -- money collected, commissions not yet triggered, and
  two more manual clicks required with no prompt. Fixed: the admin "Richiede
  attenzione" widget now also flags these, with a 2-day threshold (shorter than
  the 7-day review-queue threshold, since money already changed hands) and a
  distinct reason message.
- [x] **Problem #5 (low)**: `commission-engine-specification.md`'s test matrix
  claimed the 33% branch-cap rule was "Implemented now" -- verified false:
  `apply_branch_cap()` exists and is unit-tested in isolation but is never
  called from `calculate_chain()`/`run_calculation_for_contract()`. Corrected the
  doc. Not wired in this session: `business-rules.md` marks the cap percentage
  as PLACEHOLDER and `open-questions.md` #6 leaves the "qualifying group
  production" denominator undefined -- implementing against a guessed
  definition would trade an honest gap for a silently wrong one.

Tests added (all against a real Postgres, not mocks):
`apps/api/tests/test_contract_producer_validation.py` (4 tests: unknown agent,
cross-org agent, non-active agent, valid agent happy path) and 3 new tests in
`test_commission_engine_integration.py` (empty-chain → FAILED record, not
silent skip; dispatcher isolates a poisoned event from a healthy one in the
same batch; a **real** concurrency test using two independent DB connections
racing via `asyncio.gather` -- not the shared savepoint-rollback fixture, which
cannot exercise genuine concurrency -- confirmed the DB constraint actually
fires under a real race and is handled gracefully). Fixed one pre-existing
regression from Session 7 along the way: `test_network_isolation.py` still
unpacked `network_service.get_branch()`'s old tuple return shape. Full suite:
**33/33 passing.**

Also fixed live, not just in tests: reused the Session 7 nginx fix to verify
`create_contract` now rejects a bogus producer with a real HTTP 400, then ran a
full contract through every transition to `ACTIVE` against the live API and
confirmed real `PERSONAL_TOKEN`/`ENTREPRENEURIAL_DIFFERENCE` movements landed
in the ledger for the right agents.

**2. Admin quick-links + orange brand pass (user-requested, same session).**
- [x] `AdminOverviewPanel` gained a row of large "pulsantoni" (Contratti, Nuovo
  Contratto, Clienti, Promoter, Prodotti) above the KPI cards, wired to the same
  tab-switching the sidebar uses -- the most common destinations are now one
  click away without hunting in the sidebar, per explicit user request.
  Also caught two leftover violet/cyan spots in this file (the time-filter
  active state, the chart line/bar colors) that Session 7's brand pass had
  skipped, and remapped the two former-cyan KPI card accents to sky (not amber)
  to avoid colliding with the "In attesa di approvazione" card, which was
  already amber.

## Session 7 — 2026-07-26 (same day, continued) — Network tree readability, customer marketplace, nginx root-cause fix

Three user-driven fixes, done live between Fase 2 and Fase 3 of the admin
dashboard plan (not itself a numbered phase):

**Network tree: real names + per-level colors.** `GET
/network/agents/{id}/branch` returned only `(agent_id, depth)`, so the tree/
table UI rendered raw truncated UUIDs -- unusable for a non-technical user
trying to read their own downline. The endpoint now joins `agent_profiles`/
`ranks` and returns `display_name`, `promoter_code`, `status`, `rank_code`.
`BranchVisualizer` shows "Nome C." (given name + surname initial) per node and
gives each depth (0=root, 1-12=career-plan levels) a distinct color (left
rail + badge chip) with a legend at the top, so levels are recognizable at a
glance. `BranchTable` got the same underlying fields.

**Customer-facing product catalog ("ecosystem").** The admin could create
products/versions but customers had no way to see them -- the customer app
only had "I miei Contratti" and "Supporto". Added `image_url` to
`product_versions` (migration `0002_product_version_image_url`, first
migration since the initial schema) and a `ProductCatalogRead` schema that
pairs each product with its current version's display fields (name,
description, photo, price) so `GET /products` serves both the admin catalog
grid and the new customer marketplace from one call, no N+1 detail fetch.
`products.read` granted to the `CUSTOMER` role (previously only
`contracts.read`/`documents.download`) -- patched into the live DB the same
way as prior new-permission sessions. New `CustomerProductsPanel` ("Prodotti
& Servizi" tab): ecommerce-style cards, photo/name/description/price, filtered
to `ACTIVE` products only. Admin's `AdminProductsPanel` gained a photo-URL
field on the create form and the same card styling. No purchase/checkout flow
was added -- this is read-only catalog visibility for an already-registered
customer, distinct from the still-deferred Fase 10 (public, invite-only
marketplace for anonymous visitors).

**Real bug found and root-cause fixed: nginx stale upstream IP on container
recreation.** After rebuilding/recreating the `dashboard` container, nginx
kept proxying to the *old* container IP (`connect() failed (111: Connection
refused)`, 502s on every route) until manually reloaded -- `upstream {
server dashboard:3000; }` blocks resolve the hostname once, at nginx
startup/reload, and never again. This is the same class of bug as Session 3's
"Docker bind mount points at an orphaned inode," just for DNS instead of
filesystem, and it will keep recurring on every future deploy that recreates
a container. Root-cause fixed instead of just working around it this time:
`infrastructure/nginx/nginx.conf` now uses `resolver 127.0.0.11 valid=10s;`
(Docker's embedded DNS) with a `set $upstream ...; proxy_pass
http://$upstream;` pattern instead of static `upstream {}` blocks -- this
forces nginx to re-resolve the container's current IP on every request
(bounded by the 10s TTL), so container recreation no longer requires a manual
`nginx -s reload`. Verified by force-recreating the dashboard container (IP
changed `172.18.0.7` -> `172.18.0.6`) and confirming the live HTTPS site kept
working with zero nginx intervention.

Verified end-to-end: live curl with real JWTs (branch endpoint returns real
names, CUSTOMER role can read `/products`, other roles still can't reach
admin-only catalog actions), full browser-session path over HTTPS for both
the network tree and the customer marketplace, `tsc`/`eslint`/`next build`
clean, alembic migration applied to the live DB before the new api image was
deployed.

## Session 6 — 2026-07-26 — Admin dashboard expansion, Fase 2: summary dashboard

The user requested a full enterprise admin/promoter management overhaul (contracts,
promoters, commission network, settlements, audit log, public marketplace, etc.) --
scoped and sequenced into `docs/admin-dashboard-plan.md` (written and committed
first, per the user's own requested process: plan → implement one phase at a time →
verify before continuing). This session completed **Fase 2 — Dashboard riepilogativa**
only; Fasi 3-10 remain planned, tracked in that document's status table.

**Backend — new `reports` domain, read-only aggregations over existing tables:**
- [x] `GET /reports/dashboard-summary?period_from=&period_to=` -- contract counts
  by status (total/active/pending-approval/rejected/cancelled/suspended/expired,
  mapped from the real `state_machine.py` status set, not guessed), commission
  totals by status (accrued/payable/paid/reversed, summed in cents), active
  promoter and active-customer counts, period-scoped new-contracts and
  new-commissions figures. Defaults to the last 30 days if no range is given.
- [x] `GET /reports/attention-items` -- contracts sitting in a review-queue status
  (`SUBMITTED`/`DOCUMENTS_PENDING`/`UNDER_REVIEW`) for more than 7 days. Contracts
  have no `updated_at` column by design (state changes are append-only history,
  see `contract_status_history`), so "time in current status" is derived from
  that contract's latest status-history row via a window function, not a
  denormalized timestamp on the contract itself.
- [x] `GET /reports/recent-activity?limit=` -- last N rows from the existing
  append-only `audit_log`, no new table.
- [x] `GET /reports/contracts-timeseries?months=` and
  `GET /reports/commissions-timeseries?months=` -- monthly counts/sums for the
  last N months (zero-filled for months with no activity), source data for the
  new frontend charts.
- [x] New `reports.read` permission (distinct from the pre-existing
  `reports.export`), granted to SUPER_ADMIN/ORGANIZATION_ADMIN/ADMIN/
  ACCOUNTING_OPERATOR/SALES_MANAGER/AUDITOR in `rbac/models.py` **and** patched
  directly into the live `permissions`/`role_permissions` tables (seeded data,
  same pattern as Session 5's new permissions) -- confirmed with a live 403 test
  using the CUSTOMER-role demo account before touching the frontend.
- [x] No new tables. Everything reads existing `contracts`, `commission_movements`,
  `agent_profiles`, `customers`, `audit_log`, `contract_status_history`.

**Frontend:**
- [x] `AdminOverviewPanel` -- new default landing tab ("Panoramica") in the admin
  sidebar: 8 KPI cards (contracts total/active/pending/rejected, commissions
  accrued/paid, active promoters, active customers), a time-range filter
  (oggi/7gg/mese/trimestre/anno) that re-queries `dashboard-summary` with the
  matching date range, two Recharts charts (12-month contract volume area chart,
  12-month commission value bar chart), an "richiede attenzione" list and a
  recent-activity feed. Built with `useQuery` from the start (the pattern Session
  5 had to retrofit into three panels after hitting React's `set-state-in-effect`
  lint rule).
- [x] `recharts` added as a dependency (first use in this codebase; MinIO and
  Recharts were the two dependencies flagged as not-yet-installed in the plan doc).

**Honest data note:** "Provvigioni pagate" (paid_cents) legitimately reads 0 today
-- the commission engine only ever writes `ACCRUED` movements right now; the
`PAYABLE`/`PAID` lifecycle transitions are Fase 7 (Liquidazioni/Pagamenti), not yet
built. This is real current behavior, not a placeholder.

Verified end-to-end: curl against the live API with a real JWT (dashboard-summary,
both timeseries endpoints, attention-items, recent-activity all returned correct
data derived from the actual seeded database), a live 403 confirming RBAC is
enforced server-side, then the full browser path (login → BFF session cookie →
`/api/proxy/reports/*` → FastAPI) over the real HTTPS domain. `tsc --noEmit`,
`eslint`, and `next build` all clean before the image rebuild/redeploy.

## Session 5 — 2026-07-26 — Admin CRUD (customers/promoters/products), recruiting, top bar

The user asked for: a persistent top bar with a corner icon cluster (day/night
toggle moved there, "classic dashboard" style); full admin management of customer
records, promoter/agent records, and marketplace products; promoters managing
their own network and enrolling their own recruits; and confirmation the network
view supports the full 12-level career-plan depth.

**Backend — three new CRUD surfaces, all org-scoped and RBAC-gated:**
- [x] `customers` domain gained a real `service.py`/`router.py` (previously only
  `models.py` existed, used internally by `contracts`): list/get/create/update,
  plus `POST /customers/{id}/supply-points` since a customer isn't usable in a
  contract without one. `PRIVATE`/`SOLE_PROPRIETOR` create a `CustomerProfile`,
  `COMPANY`/`CONDOMINIUM` create a `Company`, in the same transaction as the `Customer`.
- [x] `network` domain gained org-wide agent management: `GET/POST /network/agents`,
  `PATCH /network/agents/{id}` (rank changes write `AgentRankHistory`, matching
  the existing manual-qualification-change pattern), gated by `network.manage`
  (admin-level, org-wide) -- deliberately separate from the already-existing
  branch-scoped `network.read_branch`.
- [x] `POST /network/agents/recruit` -- lets a promoter enroll a new *direct*
  collaborator under themselves specifically (parent is resolved server-side from
  the caller's own agent, never client-supplied), gated by a new `network.recruit`
  permission distinct from `network.manage` so a promoter can grow their own
  branch without being able to place agents anywhere else in the tree.
- [x] `catalog` domain gained `service.py`/`router.py`: product+first-version
  created together (a product with zero versions can't be sold), later versions
  only ever added (never mutate a version live contracts already point to,
  per `docs/business-rules.md`), `products.read`/`products.manage` permissions.
- [x] `GET /commissions/ranks` -- reference data (the 12-rank ladder, S1-S3/TL1-4/MD1-5)
  needed by the new agent-creation forms and already used by the simulator;
  gated by authentication only, not a specific permission (harmless read).
- [x] RBAC: 3 new permission codes (`network.recruit`, `products.read`,
  `products.manage`), granted per role in `rbac/models.py` **and** patched
  directly into the running database's `role_permissions` table (seeded data,
  not a schema migration) so the existing deployment didn't need a full reseed.
- [x] All 26 existing tests still pass; new endpoints smoke-tested live over
  HTTPS (create customer/product, admin agent list, promoter recruit landing at
  depth 1, ranks list returning exactly 12 rows) before touching the frontend.

**Frontend:**
- [x] `AppShell` restructured: a persistent top bar (not just the old mobile-only
  one) now spans every screen size, sitting to the right of the desktop sidebar.
  Page title on the left, theme toggle + an avatar button (opens a small
  email/role/logout menu, click-outside-to-close) in the top-right corner --
  "classic dashboard" layout. The sidebar footer lost the theme toggle and user
  card it used to carry (moved to the top bar) and now just shows the role label.
- [x] Three new admin sidebar sections, each a self-contained panel component:
  `AdminCustomersPanel` (search, table, create modal with kind-conditional
  fields), `AdminPromotersPanel` (table showing rank/sponsor/status resolved
  from the agent list, create modal with a parent-agent and rank dropdown),
  `AdminProductsPanel` (card grid, create modal with EUR-to-cents conversion).
- [x] `RecruitForm` -- a promoter-facing "+ Aggiungi Collaboratore" button in the
  Rete Commerciale tab, calling the scoped recruit endpoint; triggers
  `router.refresh()` on success so the branch view (a server-fetched prop)
  updates without a full reload.
- [x] Confirmed (by reading the code, not assuming) that `BranchVisualizer` and
  `BranchTable` have no hardcoded depth cap -- the closure table and the UI both
  already support arbitrary depth, so "12 livelli" was a labeling/badge
  addition (`Profondità massima: N / 12 livelli`), not a new capability to build.

**Bugs found and fixed while building this:**
- [x] All three new admin panels originally fetched data with a raw
  `useEffect(() => { loadX() }, [])` -- React's newer lint rules correctly flag
  calling `setState` (even indirectly, through an async function) inside a plain
  effect. Refactored to `useQuery`/`useQueryClient` (already the established
  pattern in this codebase via `my-commissions.tsx`), which is both lint-clean
  and gives free caching/invalidation instead of manual refetch plumbing.

Verified end-to-end over the live HTTPS deployment after rebuilding both the
`api`/`celery-*` and `dashboard` images: all three new admin sections render
with live data, the promoter recruit flow adds a real depth-1 descendant, and
the top-bar theme toggle/avatar menu are present in the rendered HTML.

## Session 4 — 2026-07-26 — App shell, sidebar navigation, light/dark theme

The user pulled a redesign from GitHub (glassmorphism UI, admin contract
management, promoter network visualizer + commission simulator) and asked to
run it, then asked for a further redesign: a persistent left sidebar
("strumento di lavoro moderno") and a working light/dark toggle.

- [x] `lib/theme.tsx` — `ThemeProvider` + `useTheme()`, persisted to
  `localStorage`, defaults to system `prefers-color-scheme` on first visit. An
  inline script (`themeInitScript`, injected in `app/layout.tsx`'s `<head>`
  before hydration) sets `data-theme` on `<html>` pre-paint to avoid a flash of
  the wrong theme.
- [x] `app/globals.css`: added `@custom-variant light` (Tailwind v4) so `light:`
  prefixed classes apply only under `[data-theme="light"]` — dark stays the
  unprefixed default, matching the existing design's starting point. `.glass-card`
  / `.glass-input` and all core CSS variables now flip via this attribute.
- [x] `components/theme-toggle.tsx` — sun/moon switch, in the sidebar and on
  the login page.
- [x] `components/app-shell.tsx` — the actual "sidebar with everything": fixed
  desktop sidebar / mobile drawer, logo, role-scoped nav items, user card +
  theme toggle + logout at the bottom. Replaces each dashboard's old sticky
  header + horizontal tab bar; the existing tab sections (promoter:
  Rete/Provvigioni/Simulatore, admin: Contratti/Nuovo, customer:
  Contratti/Supporto) became sidebar nav items 1:1 -- no new fake nav items
  invented for sections that don't exist yet.
- [x] Applied the light theme across every existing component (~2000 lines):
  ran an automated pass (regex substitution with strict word-boundary
  matching, not naive sed) to append `light:` variants to every hardcoded dark
  Tailwind class, then manually reviewed and fixed ~9 false positives it
  introduced -- cases like button text sitting on a *solid* colored badge
  (e.g. `bg-violet-600`), which must stay white in both themes and should
  never have gotten a `light:text-slate-900` override.
- [x] Hoisted `QueryProvider` to the root layout (was being remounted, and its
  cache lost, every time a dashboard's internal tab changed).
- [x] Fixed a real, live RBAC bug surfaced by the new promoter-facing
  simulator tab: `PROMOTER` had no `commissions.simulate` permission, so the
  new UI 403'd. Added it (read-only, never touches the ledger) to
  `rbac/models.py` and to the running database's `role_permissions` table
  directly (seeded data, not a schema migration).
- [x] Fixed 3 real lint/correctness issues surfaced by `eslint`'s
  React Compiler rules while rebuilding: unescaped apostrophes/quotes in JSX
  text (`react/no-unescaped-entities`), `Math.random()` called during render
  in the customer support-ticket confirmation (moved into the submit handler
  so the ticket number is stable instead of changing on every re-render), and
  a justified (commented, suppressed) exception for syncing theme state from
  a pre-hydration DOM attribute in a `useEffect`.
- [x] Verified end-to-end over the live HTTPS URL after rebuilding both the
  `dashboard` and `api`/`celery-*` images: login, sidebar navigation and theme
  attribute present in all three dashboards, and the promoter's commission
  simulator returning real 200 results post-fix.

## Session 1 — 2026-07-25

### Phase A — Analysis & documentation ✅
- [x] Repository analysis (repo was empty — greenfield build, no existing stack,
      no `Allegato_A_Piano_Carriera_Regolamento_Provvigionale.pdf`)
- [x] `docs/architecture.md`, `docs/database-model.md` (+ ER diagram),
      `docs/business-rules.md`, `docs/commission-engine-specification.md`,
      `docs/open-questions.md`, `docs/security-model.md`, `docs/network-model.md`,
      `docs/ai-architecture.md` (design only), `docs/deployment.md`,
      `docs/adr/0001..0005`

### Phase B/C/D/E — Vertical slice ✅ (verified working end-to-end)

**Monorepo & infra**
- [x] pnpm workspace (`apps/api`, `apps/dashboard`; `apps/worker` shares the api image)
- [x] `docker-compose.dev.yml` (postgres, redis, minio, api, celery-worker,
      celery-beat, dashboard, nginx) — actually run with `docker compose up --build`
      on the target server (Docker installed this session); all 8 containers
      healthy, demo data seeded, full login flow verified through the public
      nginx entrypoint. Three real bugs found and fixed in the process (see below).
- [x] `docker-compose.production.yml`, multi-stage `Dockerfile`s (non-root users,
      healthchecks) for api and dashboard
- [x] `.env.example`, `.gitignore`, `scripts/{deploy,backup,restore,health-check,migrate,rollback}.sh`

**Backend (FastAPI, verified against a real local Postgres 18 instance)**
- [x] `auth`: Argon2id hashing, JWT access tokens, rotating refresh tokens in a
      `sessions` table, single/all-session revocation, account lockout, identical
      error message for unknown-email vs wrong-password (enumeration mitigation)
- [x] `organizations`, `users`, `rbac` (roles/permissions/ABAC-ready), `audit`
      (append-only)
- [x] `network`: `agent_profiles`, `network_nodes`, `network_edges`,
      `network_closure` (with reflexive rows + composite indexes),
      `network_assignment_history`, `network_snapshots`/`network_snapshot_nodes`;
      transactional `move_agent()` (cycle prevention, whole-subtree relocation,
      closure table maintenance) and `create_snapshot_for_contract()`
- [x] `referral`: promoter codes, referral events/sessions (hashed cookie tokens),
      customer attribution
- [x] `catalog`, `customers`, `contracts`: explicit state machine
      (`state_machine.py`, `assert_transition_allowed`), status history, ownership
      link (`customers.user_id`) for customer self-service
- [x] `outbox`: transactional outbox table + dispatcher (ADR 0005) — commission
      calculation triggers only on `ContractActivated`/`ContractRenewed`, never on
      creation/submission
- [x] `commissions`: pure-function calculator (`calculators/entrepreneurial_difference.py`),
      isolated 33%-rule policy (`policies/branch_cap.py`), orchestration service with
      idempotency (`(contract_id, trigger_event_id)` + unique `idempotency_key`),
      append-only `commission_movements` ledger, read-only simulator
- [x] Ownership-scoped endpoints: `GET /contracts/mine` (customer), `GET /network/mine`
      + `GET /network/agents/{id}/branch` (promoter, ABAC-checked against the
      closure table), `GET /commissions/mine`
- [x] Celery app (`app/celery_app.py`) reusing the same domain code; beat schedule
      polls the outbox every minute

**Database**
- [x] Alembic migration `0001_initial_schema` — 43 tables, generated via
      autogenerate and applied cleanly to a real Postgres instance
- [x] Fixed a real bug found during verification: bare `datetime` columns defaulted
      to naive `TIMESTAMP` (no `timezone=True`), causing
      `can't compare offset-naive and offset-aware datetimes` the first time a
      loaded value was compared against `utcnow()`. Fixed at the `Base` level via
      `type_annotation_map`.
- [x] Fixed a real bug: `network_nodes` had a hard unique constraint on
      `(organization_id, agent_id)`, which made a second (historical) row for the
      same agent impossible — broke every `move_agent()` call. Replaced with a
      partial unique index (`WHERE effective_to IS NULL`).

**Docker Compose — actually run on the target server, 4 more real bugs found and fixed**
- [x] `apps/dashboard/Dockerfile` created a group/user at gid/uid 1000, but
      `node:22-slim` already ships a `node` user at that exact id → build failure.
      Fixed by reusing the image's own `node` user instead of creating one.
- [x] Corepack fetched pnpm `latest` (11.x) inside the build, whose stricter
      default blocks native postinstall scripts (`sharp`, `unrs-resolver`) unless
      explicitly approved → build failure. Fixed by pinning
      `"packageManager": "pnpm@9.15.9"` in the root `package.json` so the container
      uses the exact version the lockfile was generated with.
- [x] `apps/dashboard/public/` didn't exist (never created) → `COPY` in the
      Dockerfile failed. Created an (empty, `.gitkeep`) directory.
- [x] `celery-beat` tried to write `celerybeat-schedule` into `/app`, which is
      root-owned (only files explicitly `COPY --chown`'d are not) → permission
      denied, crash loop. Fixed by pointing `--schedule` at `/tmp`.
- [x] `celery-worker`/`celery-beat` inherited the api image's `HEALTHCHECK`
      (`curl localhost:8000/health`), which is meaningless for a process with no
      HTTP server → both reported "unhealthy" even though they worked fine. Fixed
      with a real `celery inspect ping` check for the worker and `disable: true`
      for beat.
- [x] The dashboard's Next.js standalone `server.js` was binding to the
      container's own interface IP instead of the wildcard address, so anything
      probing `localhost:3000` from inside the same container (the healthcheck)
      got `ECONNREFUSED` even though the app was reachable fine from other
      containers via the `dashboard` service name. Fixed by setting `HOSTNAME=0.0.0.0`.
- [x] **The most consequential one**: nginx's `location /api/` forwarded straight
      to FastAPI, silently swallowing the dashboard's own BFF routes at
      `/api/auth/login` and `/api/proxy/*` — login appeared to "work" (no error)
      but never actually went through the BFF, so no session cookie was ever set
      and every protected page redirected back to `/login`. Fixed by moving direct
      backend access to `/backend/` and leaving `/api/*` exclusively to the
      dashboard, matching the BFF pattern the architecture actually calls for.

**Seed data** (`python -m app.seed`)
- [x] 1 organization, 7 demo logins (`SUPER_ADMIN`, `ADMIN`, `BACK_OFFICE_OPERATOR`,
      `ACCOUNTING_OPERATOR`, `SALES_MANAGER`, plus a real `PROMOTER` login linked to
      agent `MD5-ROSSI` and a real `CUSTOMER` login linked to a seeded customer, so
      every dashboard is actually logins-testable, not just role-labeled)
- [x] 20 agents, 2 parallel top-level branches, 6 levels deep in Branch A —
      demonstrates branch isolation (a promoter cannot read the parallel branch)
- [x] Ranks S1–S3/TL1–4/MD1–5 (placeholder figures, see `open-questions.md`)
- [x] 3 products (luce, gas, Energia Circolare/PMI), customers of 3 kinds, contracts
      in ACTIVE / DRAFT / REJECTED / CANCELLED states
- [x] Commission ledger populated by the real engine — verified by hand: chain
      `S1(4000)→S2(+500)→S3(+500)→TL2(+1000)→TL4(+1000)→MD5(+2500)` sums correctly
      to the top rank's token, no duplicated differential

**Tests** (26 passing — pure-function + Postgres-integration, see test list below)
- [x] `apps/api/app/domains/commissions/tests/test_entrepreneurial_difference.py` —
      producer-only, single/multiple ascendants, equal/lower rank ⇒ zero,
      full S→MD chain sums correctly, empty chain
- [x] `apps/api/app/domains/commissions/tests/test_branch_cap.py` — under/at/over the
      33% cap, multiple branches, zero production, no branches
- [x] `apps/api/tests/test_auth.py` — login success, enumeration-safe failure,
      lockout after N attempts, refresh token rotation/revocation
- [x] `apps/api/tests/test_network_isolation.py` — parallel-branch isolation, closure
      depth correctness, move-agent cycle prevention, whole-subtree relocation,
      multi-tenant isolation
- [x] `apps/api/tests/test_commission_engine_integration.py` — activation generates
      the expected movements, re-processing the outbox never duplicates them,
      calculations are organization-scoped

**Frontend (Next.js 16, verified with real installs/builds)**
- [x] BFF pattern: HttpOnly/Secure/SameSite=Lax session cookie holding the API
      access+refresh tokens; browser never sees either token
- [x] `proxy.ts` (Next 16's post-middleware convention) gates `/customer`,
      `/promoter`, `/admin` behind session presence; backend still re-checks
      authorization regardless (frontend is never the security boundary)
- [x] Login page, 3 role dashboards (customer: own contracts; promoter: own agent
      profile + branch table via TanStack Table + own commissions via TanStack
      Query against a same-origin proxy route; admin: org-wide contracts +
      status breakdown)
- [x] `pnpm typecheck`, `pnpm lint`, `pnpm build` all pass with zero errors

### Verification method (be explicit about what was and wasn't run)
This machine is the actual target server (a Hetzner VM, public IP
`46.225.127.164`), not a disposable sandbox. Verification happened in two passes:

1. **Host-level**, before Docker was installed: `postgresql`, `nodejs`/`npm`/`pnpm`
   installed directly; backend migrated/seeded/tested against a real local
   Postgres; frontend installed/typechecked/linted/built with real `next build`;
   both servers driven directly (`uvicorn`, `next dev`) via `curl` through the
   actual BFF login flow.
2. **Full Docker Compose**, once Docker was installed at the user's request:
   `docker compose -f docker-compose.dev.yml up --build` — all 8 containers
   (postgres, redis, minio, api, celery-worker, celery-beat, dashboard, nginx)
   came up healthy after fixing the 6 bugs listed above. Demo data was seeded
   into the running stack (`docker compose exec api python -m app.seed`), and the
   full login → session cookie → protected dashboard flow was verified through
   the **public IP** (`http://46.225.127.164/`), not just localhost — including
   confirming unauthenticated requests to `/admin` still redirect to `/login`
   when hit from outside the server.

**Caveat**: this is HTTP only (no TLS/certbot wired yet, Phase H), and the current
`.env` was generated with strong random secrets but the running stack still uses
**seed/demo data** — do not treat this as production-ready as-is. See "Next
recommended session" for the concrete gap list before this should be treated as
more than a live demo.

### Explicitly NOT in this session's scope (tracked for later phases)
- Payments beyond the `PaymentProvider` interface (no `MockPaymentProvider` class
  yet — the contract state machine supports the states, but there's no payment
  webhook handler in this slice)
- Document upload/storage (MinIO is wired in Docker Compose; no `documents` domain
  code yet)
- Notifications (Celery beat + outbox infra exists; no notification templates/tasks)
- Reporting/CSV export, reversals/renewals calculators (Energia Circolare bonus,
  reversal proration -- extension points documented, not implemented)
- AI/pgvector (design doc only, `docs/ai-architecture.md`)
- CI/CD pipeline, automated backup retention/off-server copy, monitoring stack
  (Prometheus/Grafana/Loki), MFA enforcement, full GDPR tooling
- Rest of the Hypothesis property-based test matrix from
  `commission-engine-specification.md`

### Known risks / assumptions
See `docs/open-questions.md`: rank thresholds, network move self-approval, Energia
Circolare formula, reversal proration formula, GDPR retention, 33% cap denominator,
MFA/lockout policy — all placeholders pending the real business-rules document.

### Next recommended session
1. ~~Wire HTTPS~~ — done in Session 3, see below. If a *permanent* domain
   replaces the temporary Hetzner rDNS hostname, redo the certbot procedure in
   `docs/server-migration-guide.md` §4.6 for the new name.
2. Decide whether this server should keep running the demo/seed stack publicly or
   be reset before real customer data ever touches it — seed data and demo
   credentials (`DemoPass123!` for every seeded user) are live on the public
   internet right now.
3. Phase F: notifications (Celery tasks + templates) and a minimal reports domain.
4. Phase D hardening: `documents` domain (MinIO upload/download with signed URLs)
   and a real `PaymentProvider` + `MockPaymentProvider`.
5. Wire CI (lint/typecheck/test/build) — the repo now has a remote
   (`github.com/raphaelcodeart/energy-webapp`, branch `main`), so this is unblocked.

## Session 3 — 2026-07-25 (same day, continued) — HTTPS wired

The user tried logging in over plain HTTP and hit exactly the security behavior
`docs/security-model.md` describes: the browser silently discards the `Secure`
session cookie on a non-HTTPS connection, so login looked like it did nothing
(no visible error, page just reloads to `/login`). The correct fix was never to
weaken the cookie — it was to actually wire the TLS termination this project had
deferred to "Phase H".

- [x] Real Let's Encrypt certificate issued for the server's temporary Hetzner
  rDNS hostname (`static.164.127.225.46.clients.your-server.de`), via certbot in
  webroot mode, non-standard config dir (`./certbot/`, not `/etc/letsencrypt`)
  so it lives alongside the project rather than in host-global state.
- [x] `infrastructure/nginx/nginx.conf`: HTTP (80) now serves only the ACME
  challenge and 301-redirects everything else to HTTPS; HTTPS (443) terminates
  TLS and proxies exactly as before (`/backend/` → API, everything else →
  dashboard).
- [x] `docker-compose.dev.yml`: nginx now publishes 443, mounts
  `./certbot/conf` (read-only) and `./certbot/www` (read-only, ACME challenge
  webroot).
- [x] `scripts/renew-cert.sh` + a crontab entry (daily at 03:00) — **the
  certbot package's own systemd renewal timer does NOT cover this certificate**
  because it uses a non-default config directory; without this script, the
  cert would silently expire in 90 days.
- [x] `.env`'s `NEXT_PUBLIC_APP_URL` updated to the `https://` hostname.
- [x] `certbot/` added to `.gitignore` — it holds private keys, must never be committed.
- [x] Verified end-to-end over the real HTTPS URL: HTTP→HTTPS redirect, real
  cert served (not self-signed), login issues a cookie the browser will
  actually keep, and the admin dashboard renders live data through it.

Two more real bugs found and fixed while wiring this (bringing the running
total to 9 — see `docs/server-migration-guide.md` §8 for the full list with
symptoms, so they're recognized immediately if hit again on a future server):
- Certbot refuses to issue a certificate into a `live/<domain>` directory that
  already exists (even if it's just a manually-placed bootstrap/dummy cert) —
  has to be removed first.
- A Docker bind mount established before a host directory is `rm -rf`'d and
  recreated stays attached to the old (now-orphaned) inode; the container sees
  an empty directory even though the host has fresh files. `nginx -s reload`
  doesn't fix this — the container itself must be recreated.

## Session 2 — 2026-07-25 (same day, continued)

- [x] Pushed the full repository to `git@github.com:raphaelcodeart/energy-webapp.git`
  (branch `main`), via a dedicated deploy-key SSH identity generated on this server.
- [x] `docs/server-migration-guide.md` — step-by-step server rebuild/migration
  runbook: prerequisites, `.env` generation, data migration from an existing
  server (`scripts/backup.sh` output restored into a fresh Postgres), domain/TLS
  setup, a code map, and the full list of the 7 real deployment bugs found in
  Session 1 (so they're not rediscovered from scratch on a new server).
- [x] `docs/database-schema.sql` — ground-truth schema dump (`pg_dump
  --schema-only`) of the actual running database, 43 tables, generated from the
  live stack rather than hand-written. `docs/database-model.md` now points to it
  explicitly as the authority in case of drift.
- [x] `docs/user-guide.md` (Italian) — end-user guide for the three dashboards as
  they exist today, written to match actual behavior rather than aspirational
  scope (explicitly lists what each dashboard does *not* yet do).
