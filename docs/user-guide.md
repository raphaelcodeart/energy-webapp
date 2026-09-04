# Guida Utente — Piattaforma Lial Energy

Questa guida spiega come usare la piattaforma **oggi**, nello stato attuale dello
sviluppo (vedi `docs/implementation-progress.md` per il dettaglio tecnico
sessione per sessione di cosa è completo e cosa arriverà nelle prossime fasi).
Non promette funzionalità non ancora costruite.

## 1. Come accedere

Apri il browser su:
```
https://<tuodominio>/login
```

Nella pagina di login servono **tre informazioni**: Organization ID (te lo
comunica chi amministra il sistema), Email, Password.

Se inserisci credenziali sbagliate, il messaggio è sempre lo stesso ("email o
password non validi") sia che l'email non esista sia che la password sia
sbagliata — è una scelta di sicurezza intenzionale (evita che un malintenzionato
scopra quali email sono registrate). Dopo **5 tentativi falliti** l'account
viene bloccato temporaneamente (15 minuti).

Dopo il login resti connesso per un massimo di **15 minuti** di sessione (il
rinnovo automatico non è ancora attivo). Da qui in poi, quando la sessione
scade, vieni riportato automaticamente al login invece di vedere un errore —
prima non era così, era un bug reale corretto.

Puoi passare tra **modalità giorno e notte** dall'icona in alto a destra —
giorno è la modalità di partenza per chiunque apra il sito per la prima volta.

**Password dimenticata?** Link "Password dimenticata?" sotto il campo password
nel login → inserisci Organization ID ed email → ricevi un link per scegliere
una nuova password (valido 60 minuti, utilizzabile una sola volta). Se non
arriva un'email, chiedi a chi amministra il sistema: finché non è configurato
un server SMTP, il link viene generato comunque ma non recapitato via email —
va recuperato manualmente lato server.

## 2. Registrazione: solo su invito

**Non esiste un modulo di registrazione pubblico aperto a chiunque.** Ogni
nuovo cliente entra nel sistema tramite il **link personale di un promoter**
(`https://tuodominio/r/CODICE-PROMOTER?org=...`) — è un circuito chiuso per
design: nessun cliente può esistere senza un promoter che lo ha invitato.

Chi clicca un link di invito vede una pagina con: nome del promoter che lo ha
invitato, l'eventuale offerta consigliata (mostrata per nome, non come codice
tecnico — se il promoter ha condiviso un prodotto specifico), e un modulo con:
tipologia (privato/azienda), nome e cognome (o ragione sociale), telefono,
email, password (richiesta due volte per conferma, per evitare refusi). Alla
conferma, l'account
viene creato **già collegato al promoter che lo ha invitato** — questo
collegamento (in `customer_attributions`) è permanente e non richiede nessuna
azione successiva.

Non è ancora implementato in questa fase (pianificato come sviluppo successivo,
richiede un servizio di invio email che il progetto non ha ancora):
conferma email con PIN via email, primo accesso che obbliga a completare il
profilo, memoria della promozione specifica scelta tra login successivi,
attivazione di più promozioni contemporaneamente con scelta della sede.
La versione attuale è più semplice ma **reale e funzionante**: email+password
in un unico passaggio, attribuzione al promoter garantita e verificata.

## 3. Le tre aree della piattaforma

In base al tuo ruolo, dopo il login vieni indirizzato a una di queste aree.
Ogni ruolo vede **solo i propri dati** — non è una limitazione dell'interfaccia,
è imposta anche lato server, quindi non è aggirabile modificando l'URL a mano.

### 3.1 Area Cliente (`/customer`)

La prima cosa che un cliente vede è lo **Shop** — il catalogo dei prodotti
pubblicati dall'amministrazione (offerte luce, gas, dual fuel, ma anche
eventuali prodotti digitali/fisici/abbonamenti), con foto, descrizione,
prezzo e IVA. Le altre sezioni: **I miei Contratti** (stato tradotto in
italiano, prodotto acquistato mostrato per nome non per codice tecnico, punto
di fornitura mostrato con un nome comprensibile — es. "Energia elettrica - Via
Roma 12, Milano" — non solo il codice POD/PDR, e data di scadenza/rinnovo ben
in evidenza, colorata in ambra quando manca meno di 30 giorni). Ogni contratto
mostra anche il proprio **IBAN per l'addebito** (modificabile in linea) e i
**documenti richiesti** (carta d'identità, codice fiscale, bolletta luce/gas,
e per aziende/condomini anche la visura camerale): per ciascuno vedi se manca,
è in attesa di verifica o è già stato approvato, e puoi caricare/sostituire il
file direttamente da qui — se l'amministrazione segnala "documenti mancanti"
su un contratto, è qui che li aggiungi. **Supporto & Assistenza** — qui puoi
aprire un ticket vero (non solo un modulo che scompare): resta visibile nella
tua area finché non viene risolto, e vedi le risposte dell'amministrazione
direttamente nella conversazione.

Cosa non è ancora disponibile: acquisto/checkout diretto dallo shop (oggi la
vetrina è consultabile, l'attivazione di un contratto passa dall'amministrazione
o dal promoter), storico pagamenti/fatture.

**Documentazione** — feed di sola lettura con annunci e materiale pubblicati
dall'amministrazione (testo, e opzionalmente un'immagine, un PDF o un link
video), specifici per i clienti o condivisi anche con i promoter.

**Lavora con noi** — un cliente può candidarsi a diventare promoter
direttamente dalla propria area (anche dalla scheda "Prodotti", con una
card dedicata). L'attivazione è **immediata**: appena inviata la richiesta,
il cliente diventa promoter attivo (qualifica iniziale S1), agganciato a chi
lo ha originariamente invitato — non è più necessaria un'approvazione
dell'amministrazione, salvo il caso in cui l'account sia stato messo in
"blacklist" da un amministratore (in quel caso serve una nuova approvazione
manuale). Chi ha sia il ruolo Cliente sia quello Promoter vede in cima
all'intestazione (e nel menu account) un selettore **"Area Cliente / Area
Promoter"** per passare dall'una all'altra senza fare logout.

**Wallet** — un portafoglio interno in euro, personale e sempre disponibile,
pensato come un "finto wallet crypto": ha un saldo, un indirizzo univoco
(stile `0x...`, da copiare con un click) e uno storico di tutte le
transazioni. L'amministrazione può accreditare del cashback su questo
wallet dopo un acquisto (o anche solo come ricarica). Da qui puoi anche
**inviare denaro a un altro wallet** conoscendo il suo indirizzo — funziona
come un vero wallet crypto: basta l'indirizzo del destinatario, nessuna
relazione richiesta. Ogni movimento (ricevuto o inviato) resta nello
storico con data, importo e controparte. Il saldo è puramente interno: non
è collegato a conti bancari reali e non si può prelevare.

### 3.2 Area Promoter (`/promoter`)

Pensata per far gestire al promoter la propria rete **come una vera azienda**:

- **La mia Azienda** (schermata di apertura) — statistiche generali in alto:
  persone totali nella tua rete, livelli sotto di te (puoi vedere solo il tuo
  ramo, mai il resto dell'organizzazione), contratti chiusi, rifiutati, in
  attesa (pending) e in lavorazione, provvigioni totali. Sotto, un grafico a
  barre per livello (persone e contratti) e una tabella riepilogativa —
  **clicca un livello per il dettaglio**: persone di quel livello, chiusi, in
  lavorazione, problemi. Più giù: una tabella per persona (contratti
  totali/processati/in lavorazione/con problemi, provvigioni), e l'elenco di
  **tutti i contratti della tua rete** con cliente, prodotto, punto di
  fornitura, venditore, stato e provvigione generata — con un pulsante
  **Contatta** (apre l'email al cliente) per i contratti con problemi, e se
  l'amministrazione ha lasciato una nota (es. "manca il documento di identità")
  la vedi direttamente sotto il contratto interessato.
- **Rete Commerciale** — l'albero visivo della tua rete, colorato per livello
  (fino a 12), con nomi reali (non solo codici), qualifiche. Naviga livello per
  livello: si apre subito il tuo primo livello (i tuoi diretti), poi clicchi
  su una persona per aprire il livello sotto di lei, e così via — non un unico
  elenco con tutto espanso insieme. **Clicca il nome (o l'icona accanto) di
  qualsiasi persona nell'albero** per aprire un popup di dettaglio: quante
  persone ha sotto di sé, quanti contratti e in che stato, il valore
  complessivo generato in quel ramo e — per ogni contratto — **la provvigione
  che HAI guadagnato tu specificamente da quel contratto** (diversa dalla
  provvigione totale pagata a tutta la filiera, perché nel piano multilivello
  ogni persona nella catena prende una quota diversa).
- **Prodotti da Condividere** — lo stesso catalogo che vede il cliente, con un
  pulsante **Condividi** su ogni prodotto: copia negli appunti un link diretto
  a quel prodotto con il tuo codice promoter già incorporato, pronto da inviare
  a un cliente. C'è anche un pulsante **Condividi il tuo link** in alto (link
  generico, senza prodotto specifico).
- **Movimenti Provvigioni** — storico dei gettoni personali e delle differenze
  imprenditoriali maturate.
- **Simulatore Provvigioni** — anteprima di quanto genererebbe un contratto
  ipotetico, senza toccare i dati reali.
- **Supporto** — apri un ticket verso l'amministrazione (es. per un chiarimento
  su una provvigione o un problema con un cliente) e segui la conversazione
  nella tua area finché non è risolto.
- **Documentazione** — lo stesso feed di annunci/materiale che vede il
  cliente, quando l'amministrazione lo pubblica anche (o solo) per i
  promoter.
- **Wallet** — lo stesso portafoglio interno in euro descritto per l'area
  Cliente: saldo, indirizzo personale, invio/ricezione verso qualsiasi altro
  wallet della piattaforma, storico transazioni. È lo stesso wallet
  indipendentemente dal ruolo con cui accedi (se hai sia login Cliente sia
  Promoter, il saldo è unico e condiviso tra le due aree).

Se hai anche un account Cliente collegato allo stesso login, in cima
all'intestazione trovi lo stesso selettore **"Area Cliente / Area Promoter"**
descritto nella sezione precedente.

**Qualifica**: la tua qualifica (S1, S2, ... TL1, ... MD1, ...) non è solo
una progressione — viene **ricalcolata ogni mese** confrontando il tuo
fatturato personale e di gruppo del mese appena chiuso con le soglie della
scala qualifiche: puoi tanto salire quanto **retrocedere** se un mese va a
vuoto dopo un mese forte. Ricevi una notifica in-app quando succede.

### 3.3 Area Amministratore (`/admin`)

Per ruoli di staff (Admin, Back Office, Accounting, Sales Manager, Super Admin
— permessi leggermente diversi tra loro, vedi `docs/security-model.md`).

- **Panoramica** — pulsanti grandi verso le sezioni principali, KPI (contratti
  per stato, provvigioni maturate/pagate, promoter e clienti attivi), la rete
  commerciale **di tutta l'azienda** (persone totali, livelli totali, grafico
  per livello — a differenza della vista del promoter, qui non c'è alcuna
  restrizione di ramo), grafici di andamento a 12 mesi, elenco "Richiede
  attenzione" (contratti fermi in revisione da troppo tempo, o **pagati ma non
  ancora attivati** — quindi con provvigioni non ancora generate), attività
  recente.
- **Tutti i Contratti** — elenco con nome cliente (non solo l'ID), prodotto e
  punto di fornitura con nome comprensibile, colonna scadenza/rinnovo colorata
  per urgenza, filtro per anno (storico separato per anno, utile perché ogni
  anno ci saranno contratti da rinnovare), filtri per stato, azione di
  transizione di stato con motivazione obbligatoria. Il pulsante **Recensisci**
  apre anche i **documenti del contratto** (carta d'identità, codice fiscale,
  bolletta, visura camerale per aziende/condomini): da qui puoi caricare un
  documento per conto del cliente (es. se te lo ha inviato via email) e,
  quando il cliente ha caricato il suo, **approvarlo o respingerlo** con una
  nota — la nota compare automaticamente al promoter nella sua vista di rete,
  cosi sa cosa manca e può contattare il cliente.
- **Nuovo Contratto** — form completo: scegli se cliente nuovo o esistente; per
  un cliente nuovo raccoglie tipologia (privato/azienda), codice fiscale o
  partita IVA, nome e cognome (o ragione sociale), email, cellulare, PEC
  (opzionale) e i dati del punto di fornitura; poi scegli l'offerta, l'IBAN per
  l'addebito (opzionale, puoi aggiungerlo dopo) e il promoter/venditore che ha
  portato la vendita, con una nota libera opzionale (utile per
  l'amministrazione — chi lo ha invitato, con quale promozione, preferenze di
  contatto).
- **Anagrafiche Clienti** — foto profilo (o icona generica se non caricata) in
  ogni riga; icona **Mostra** apre un popup con tutti i dati (indirizzi, punti
  di fornitura, dati fiscali) e in più un **riepilogo contratti**: prodotto,
  stato colorato (verde se attivo/rinnovato, rosso se respinto/cessato,
  ambra se in lavorazione), scadenza — clicca una riga per il dettaglio
  (date esatte, note, id). Lo stesso popup mostra anche il **Wallet** del
  cliente (saldo e indirizzo, se ha già un login) con un mini-modulo
  **"Ricarica"** per accreditare cashback direttamente da qui, subito dopo
  un acquisto o come riconoscimento manuale. L'icona **Modifica** apre una schermata completa:
  carica/cambia la foto profilo, modifica i dati anagrafici, e in fondo
  **Riassegna Promoter** (cambia a quale promoter il cliente è attribuito,
  con motivazione obbligatoria — tracciato come le altre modifiche). Non c'è
  ancora un'azione di eliminazione — un cliente non può essere cancellato
  senza rischiare di orfanizzare i suoi contratti, quindi non è stato aggiunto
  un pulsante che non farebbe nulla di sicuro.
- **Anagrafiche Promoter** — foto profilo (o icona generica) per ogni agente;
  tabella con qualifica e sponsor, e ora anche un'icona **Modifica**: nome
  (nome e cognome separati), foto, qualifica e stato (attivo/sospeso/cessato)
  sono modificabili (il codice promoter no, è incorporato nei link di invito
  già condivisi). Pulsante **"+ Promoter Radice"** per creare un promoter
  senza sponsor (l'inizio di un ramo di rete indipendente) — l'unico modo per
  farlo, dato che la registrazione normale richiede sempre un link di
  invito di qualcun altro. Su un promoter attivo: **Disattiva** (lo sospende,
  può ricandidarsi liberamente) e **Blacklist** (come Disattiva, ma una sua
  eventuale ricandidatura futura tornerà ad aver bisogno di
  approvazione manuale, invece di riattivarsi da sola). Su un promoter
  disattivato/in blacklist: **Riattiva** / **Rimuovi blacklist**. Pulsante
  **"Valuta gradi ora"** avvia manualmente la stessa valutazione mensile
  automatica delle qualifiche (promuove/retrocede ogni promoter attivo in
  base al fatturato del mese) che gira comunque in automatico il giorno 1 di
  ogni mese — utile per rieseguirla o vederne subito l'effetto.
- **Prodotti & Marketplace** — catalogo con foto, prezzo, IVA; pulsante
  **Modifica** su ogni prodotto. Il tipo di prodotto non è più solo "contratto
  energia": puoi scegliere anche Digitale, Fisico o Abbonamento. La foto si
  può sia incollare come link sia **caricare direttamente un file** dalla
  schermata di modifica, con anteprima di quella già presente. La schermata
  di modifica permette anche di impostare un **gettone provvigionale diverso
  per grado specifico di questo prodotto** (in alternativa al valore standard
  uguale per tutti i prodotti). Pulsanti **Duplica** (crea un nuovo prodotto
  precompilato da uno esistente, inclusi eventuali gettoni personalizzati) ed
  **Elimina** (con conferma; rifiutato se il prodotto ha già contratti
  collegati).
- **Documentazione** — crea/modifica/archivia annunci e materiale (testo, più
  opzionalmente un'immagine, un PDF o un link video) da pubblicare per i
  clienti, i promoter, o entrambi — visibili nella rispettiva scheda
  "Documentazione" delle due aree.
- **Rete Commerciale** — a differenza della vista del promoter (limitata al
  proprio ramo), qui vedi **l'intera organizzazione**: tutti i rami, con
  ricerca ed espandi/comprimi. Naviga livello per livello come nella vista
  promoter — "Espandi tutto" o una ricerca forzano l'apertura di tutti i
  livelli in una volta. Come nella vista promoter, **clicca il nome di
  qualsiasi persona** per il popup di dettaglio (persone sotto, contratti,
  valore, provvigioni) — qui però, essendo un ruolo di staff e non un
  promoter con una propria filiera, la provvigione mostrata è quella totale
  del ramo, non "la tua", perché lo staff non è un beneficiario del piano
  provvigionale.
- **Ticket di Supporto** — tutti i ticket aperti da clienti e promoter, con
  filtro per chi li ha aperti e per stato; rispondi e la risposta appare
  subito nell'area del cliente/promoter. Una risposta su un ticket "Aperto" lo
  sposta automaticamente in "In lavorazione"; solo l'amministrazione può
  segnarlo come "Risolto" o "Chiuso".
- **Wallet** — visione d'insieme di tutti i portafogli della piattaforma:
  saldo e indirizzo di ogni cliente/promoter (con ricerca per nome, email o
  indirizzo), più il registro globale di tutte le transazioni (ricariche,
  trasferimenti tra utenti, storni), filtrabile per tipo ed esportabile in
  CSV. Da qui puoi anche **stornare** una transazione fatta per errore (un
  clic su "Storna" con motivazione): non cancella la transazione originale,
  ne registra una di correzione collegata, così lo storico resta sempre
  tracciabile. La ricarica di un singolo cliente si fa più comodamente dal
  suo popup in "Anagrafiche Clienti" (vedi sopra); questa sezione è la vista
  d'insieme su tutta l'organizzazione.

## 4. Cosa succede "dietro le quinte" quando un contratto si attiva

- Creare o inviare un contratto **non genera mai** una provvigione.
- La provvigione viene calcolata **una sola volta**, quando un contratto passa
  allo stato **Attivo** — non quando viene solo pagato (quello è uno stato
  intermedio, "Pagata", distinto da "Attiva"; se un contratto resta fermo lì
  troppo a lungo, l'amministrazione lo vede nell'elenco "Richiede attenzione").
- Il calcolo cristallizza la catena degli sponsor così com'era in quel momento
  — spostamenti successivi nella rete non cambiano mai calcoli già fatti.
- Ogni movimento di provvigione riporta una spiegazione testuale.
- Se il venditore indicato in un contratto non esiste o non è attivo, il
  sistema **rifiuta la creazione del contratto** con un errore chiaro — prima
  poteva capitare che il contratto si attivasse comunque senza pagare
  nessuno, senza nessun avviso; è stato corretto (vedi
  `docs/paid-contract-commission-audit.md`).

## 5. Domande frequenti

**"Ho dimenticato l'Organization ID."**
Non è recuperabile dalla pagina di login — contatta chi amministra il sistema.

**"Vedo 'Nessun profilo agente collegato a questo account' nell'area Promoter."**
Il tuo account utente esiste ma non è ancora collegato a un profilo agente
nella rete commerciale — serve intervento di un amministratore.

**"Il mio contratto non appare nell'area Cliente."**
L'area Cliente mostra solo i contratti collegati al tuo profilo cliente. Se il
profilo non è ancora collegato al tuo login, contatta l'assistenza.

**"Dopo 15 minuti devo rifare il login ogni volta, è normale?"**
Sì, per ora — il rinnovo automatico della sessione (silent refresh) non è
ancora stato implementato nel frontend. Non crasha più però: ti riporta
automaticamente al login.

**"Posso registrarmi da solo senza un link di invito?"**
No, per design. Il sistema è un circuito chiuso: ogni cliente deve arrivare
tramite il link di un promoter.

**"Posso usare il sito da smartphone?"**
Le pagine sono responsive (si adattano allo schermo) ma non è stato fatto un
test approfondito su dispositivi mobili in questa fase.

## 6. Per chi amministra il sistema (non utenti finali)

Operazioni non ancora disponibili da interfaccia (richiedono l'API diretta,
documentazione interattiva su `/backend/docs`, o intervento diretto sul
database): creazione utenti staff, cambio ruoli, liquidazioni/pagamenti
provvigioni, audit log visualizzabile, report esportabili in CSV, gestione
qualifiche/piano carriera dall'interfaccia, applicazione della regola del 33%
sul tetto di produzione per ramo (esiste come funzione pura testata ma non è
collegata al motore live — richiede prima una decisione di business su cosa
conta come "produzione qualificante", vedi `docs/open-questions.md` #6).

Vedi `docs/server-migration-guide.md`, `docs/architecture.md` e
`docs/admin-dashboard-plan.md` per i dettagli tecnici e la roadmap.
