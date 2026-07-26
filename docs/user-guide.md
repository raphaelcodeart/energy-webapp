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
in evidenza, colorata in ambra quando manca meno di 30 giorni) e **Supporto &
Assistenza** — qui puoi aprire un ticket vero (non solo un modulo che scompare):
resta visibile nella tua area finché non viene risolto, e vedi le risposte
dell'amministrazione direttamente nella conversazione.

Cosa non è ancora disponibile: acquisto/checkout diretto dallo shop (oggi la
vetrina è consultabile, l'attivazione di un contratto passa dall'amministrazione
o dal promoter), download documenti, storico pagamenti/fatture.

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
  elenco con tutto espanso insieme.
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
  transizione di stato con motivazione obbligatoria.
- **Nuovo Contratto** — form completo: scegli se cliente nuovo o esistente; per
  un cliente nuovo raccoglie tipologia (privato/azienda), codice fiscale o
  partita IVA, nome e cognome (o ragione sociale), email, cellulare, PEC
  (opzionale) e i dati del punto di fornitura; poi scegli l'offerta e il
  promoter/venditore che ha portato la vendita, con una nota libera opzionale
  (utile per l'amministrazione — chi lo ha invitato, con quale promozione,
  preferenze di contatto).
- **Anagrafiche Clienti** — foto profilo (o icona generica se non caricata) in
  ogni riga; icona **Mostra** apre un popup con tutti i dati (indirizzi, punti
  di fornitura, dati fiscali) e in più un **riepilogo contratti**: prodotto,
  stato colorato (verde se attivo/rinnovato, rosso se respinto/cessato,
  ambra se in lavorazione), scadenza — clicca una riga per il dettaglio
  (date esatte, note, id). L'icona **Modifica** apre una schermata completa:
  carica/cambia la foto profilo, modifica i dati anagrafici, e in fondo
  **Riassegna Promoter** (cambia a quale promoter il cliente è attribuito,
  con motivazione obbligatoria — tracciato come le altre modifiche). Non c'è
  ancora un'azione di eliminazione — un cliente non può essere cancellato
  senza rischiare di orfanizzare i suoi contratti, quindi non è stato aggiunto
  un pulsante che non farebbe nulla di sicuro.
- **Anagrafiche Promoter** — foto profilo (o icona generica) per ogni agente;
  tabella con qualifica e sponsor, e ora anche un'icona **Modifica**: nome,
  foto, qualifica e stato (attivo/sospeso/cessato) sono modificabili (il
  codice promoter no, è incorporato nei link di invito già condivisi).
- **Prodotti & Marketplace** — catalogo con foto, prezzo, IVA; pulsante
  **Modifica** su ogni prodotto. Il tipo di prodotto non è più solo "contratto
  energia": puoi scegliere anche Digitale, Fisico o Abbonamento. La foto si
  può sia incollare come link sia **caricare direttamente un file** dalla
  schermata di modifica, con anteprima di quella già presente.
- **Rete Commerciale** — a differenza della vista del promoter (limitata al
  proprio ramo), qui vedi **l'intera organizzazione**: tutti i rami, con
  ricerca ed espandi/comprimi. Naviga livello per livello come nella vista
  promoter — "Espandi tutto" o una ricerca forzano l'apertura di tutti i
  livelli in una volta.
- **Ticket di Supporto** — tutti i ticket aperti da clienti e promoter, con
  filtro per chi li ha aperti e per stato; rispondi e la risposta appare
  subito nell'area del cliente/promoter. Una risposta su un ticket "Aperto" lo
  sposta automaticamente in "In lavorazione"; solo l'amministrazione può
  segnarlo come "Risolto" o "Chiuso".

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
