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
mostra anche il proprio **IBAN per l'addebito** (modificabile in linea).

> **Lato amministratore**, aprendo un contratto compare la sezione
> **Fascicolo Completo** con due pulsanti. **Scarica tutto (ZIP)** produce un
> archivio chiamato *nome cliente-id contratto* con dentro tutti i documenti
> allegati e un **PDF riassuntivo** di contratto e cliente (anagrafica,
> punto di fornitura con POD/PDR, importi con IVA, modalità di pagamento,
> IBAN, promoter, ed elenco degli allegati con il loro stato di verifica) —
> è quello che si manda al fornitore o al commercialista. **Invia su Drive**
> mette le stesse identiche cose in una cartella con lo stesso nome su
> Google Drive; premerlo due volte non crea una seconda cartella, aggiorna
> quella che c'è. Il secondo pulsante funziona dopo aver collegato un
> account Google una volta sola, da *Impostazioni → Google Drive*.

**Attivare contratti: la pratica (Sessions 52–53).** In **I miei Contratti** il
pulsante **"Attiva nuovo contratto"** apre una *pratica di attivazione* a
schermo intero, in quattro passaggi. **1. Dati**: tutto una volta sola —
nome, cognome, email, PEC (facoltativa), IBAN, indirizzo di fornitura — e la
domanda **"Quanti POD hai?"**: scrivi il numero o usa **+** e **−**. **2.
Documenti d'identità**: identità, codice fiscale, visura per le aziende, una
volta sola per tutti i POD (se hai un'unica bolletta con tutti i punti,
caricala qui). **3. Contratti**: trovi **già tutti i POD creati** ("POD 1",
"POD 2"…) e per ognuno scegli il contratto da attivare (pulsante
**"Anteprima"** per leggerlo), oppure "Stesso contratto per tutti i POD". Il
codice POD non serve. Se un POD è a un altro indirizzo, "Indirizzo diverso?"
sotto quel POD; puoi anche allegare la sua bolletta o una foto del contatore.
**4. Riepilogo**: controlli contratti e totale, premi **"Invia la pratica"** e
scegli come pagare: **un solo pagamento** per tutti i contratti — unica
soluzione, oppure 3 o 12 rate con **un solo addebito mensile** sulla carta.
Ogni POD resta **un contratto a sé**, verificato e attivato per conto suo.
Tutto viene salvato mentre compili: una pratica lasciata a metà resta in
elenco come **Bozza** con **"Riprendi"**. Nella lista ogni pratica mostra cosa
manca ("Da pagare", "Mancano documenti per 2 POD", "7/10 attivi") e, aperta,
l'elenco dei suoi POD con stato, contratto, rate, IBAN e documenti. Il
catalogo resta sotto, in **"Scopri i pacchetti"**: "Attiva Contratto" su un
pacchetto apre una pratica con quel contratto già scelto per tutti i POD.

**Come funzionava prima (Session 49), ancora valido per i contratti già
aperti.** L'attivazione di un singolo contratto si faceva in tre passaggi a schermo intero.
**1. Dati**: intestatario (nome e cognome, già compilati dal tuo account ma
modificabili), email, **PEC** (facoltativa), **IBAN per l'addebito** — che
potrai comunque cambiare dopo da "I miei Contratti" — e il punto di
fornitura. In alto vedi il prezzo come canone e come totale: ad esempio
*15,00 € /mese × 12 mesi = 180,00 €* (+ IVA per aziende e partite IVA).
**2. Documenti**: caricali subito, oppure premi **"Vai avanti al pagamento"**
e caricali più tardi. **3. Pagamento**: soluzione unica, 3 rate o 12 rate
mensili addebitate in automatico sulla carta. **Puoi pagare subito, anche se
i documenti mancano o non sono ancora stati approvati.** Appena il pagamento
va a buon fine ricevi il **cashback LialCash dell'intero importo** sul wallet
— con le rate, a ogni rata pagata. Il contratto però diventa **Attivo** (e
partono le provvigioni della rete) solo quando l'amministrazione approva i
documenti: nell'elenco contratti dell'amministratore un contratto pagato in
anticipo ha il badge verde **Pagato**, e approvarlo lo attiva subito.

Finché un contratto è in corso di attivazione, la scheda non mostra più
l'elenco dei documenti in mezzo a tutto il resto: mostra **un solo riquadro**
che dice cosa manca davvero ("Mancano 2 documenti", "Documenti in verifica",
"Scegli come pagare") e un pulsante che apre il contratto **a schermo intero**
— stessa schermata larga dell'attivazione, non più una finestrella. Lì dentro
trovi, uno sotto l'altro, i **documenti richiesti** (carta d'identità, codice
fiscale, bolletta luce/gas, e per aziende/condomini anche la visura camerale;
per le partite IVA la visura è proposta ma **facoltativa**, perché un
professionista non ne ha una) e il **pagamento**. Per ciascun documento vedi
se manca, è in attesa di verifica o è già approvato, e lo carichi o sostituisci
da lì. In fondo c'è **"Aggiungi un altro documento"**: ti chiede prima *cosa*
stai allegando (es. "Carta d'identità retro", "Delega firmata", "Contratto di
locazione") e poi ti fa scegliere il file — così puoi allegare tutto quello che
serve anche se non rientra nelle caselle previste. Quello che carichi resta
salvato: puoi chiudere e riprendere quando vuoi. **Supporto & Assistenza** — qui puoi
aprire un ticket vero (non solo un modulo che scompare): resta visibile nella
tua area finché non viene risolto, e vedi le risposte dell'amministrazione
direttamente nella conversazione.

Lo Shop mostra separatamente le **offerte luce/gas Lial Energy** (voce di menu
dedicata "Contratti Lial Energy" -- attivazione contratto, come sopra) dai
**prodotti Dropshipping/Partner** (gadget e prodotti di terzi): questi ultimi
si acquistano **direttamente dal cliente**, senza passare dall'amministrazione
-- carrello con sconto opzionale in LialCash (se il prodotto lo prevede),
possibilità di richiedere "cashback subito" (paghi un 5% in più e lo riavrai
accreditato a pagamento confermato), e pagamento del residuo con bonifico o
carta (Stripe). Il risultato si vede nella nuova voce **I miei Ordini**: stato
(in attesa/pagato/annullato), filtri, dettaglio, prova di pagamento
caricabile per un ordine a bonifico, possibilità di cambiare metodo di
pagamento o pagare subito con carta un ordine già creato a bonifico.

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

**Wallet** — un portafoglio interno, personale e sempre disponibile, pensato
come un "finto wallet crypto": ha un saldo, un indirizzo univoco (stile
`0x...`, da copiare con un click) e uno storico di tutte le transazioni. Il
saldo e ogni transazione sono mostrati in **"LialCash"**, non in euro --
un'etichetta scelta apposta per non confonderlo mai con un pagamento reale
(quelli, con carta o bonifico, si vedono sempre in euro veri, sia
nell'ordine sia in Contabilità, vedi sotto). L'amministrazione può
accreditare LialCash su questo wallet dopo un acquisto (o anche solo come
ricarica). Da qui puoi anche **inviare LialCash a un altro wallet**
conoscendo il suo indirizzo — funziona come un vero wallet crypto: basta
l'indirizzo del destinatario, nessuna relazione richiesta (funzione
disattivata di default, va abilitata singolarmente dall'amministrazione).
Ogni movimento (ricevuto o inviato) resta nello storico con data, importo e
controparte. Il saldo è puramente interno: non è collegato a conti bancari
reali e non si può prelevare.

**Riscatta Cashback** — hai già pagato una bolletta/fattura a uno dei
fornitori partner di Lial Energy (o a Lial Energy stessa)? Carica la foto o
il PDF e l'importo dichiarato: appena un amministratore verifica il
documento e conferma l'importo reale, ti viene chiesto di pagare solo il 5%
di quell'importo (con carta, subito, o con bonifico indicando il codice
causale mostrato) per riscattare il 100% + un ulteriore 5% di bonus in
LialCash sul tuo wallet.

**Contabilità** (rinnovata in Session 54) — la tua rendicontazione personale.
In alto i **totali**: totale speso (carta + bonifico) e speso nel mese, saldo
LialCash, cashback ricevuto, pagato con carta e con bonifico, quanto hai
pagato per i contratti con le rate già pagate e la **prossima rata**, Shop e
riscatti, LialCash ricevuti e spesi e — se sei anche promoter — le
**provvigioni maturate** (da incassare e pagate). Sotto, tutti i movimenti
**raggruppati per mese**: data e ora in piccolo, titolo del movimento in
grande, descrizione in piccolo, importo ben in evidenza. Puoi **cercare**
(descrizione, prodotto, importo, numero di ordine/riscatto/contratto),
**filtrare** (Pagamenti, Contratti, Cashback, LialCash, Carta, Bonifico,
Entrate, Uscite) e scegliere un **periodo** (dal… al…); con i filtri attivi
vedi subito quanto hai pagato e quanti LialCash hai ricevuto in quella
selezione. **Clicca un movimento** per aprirne il dettaglio: importi, metodo,
riferimenti Stripe o causale del bonifico e una **cronologia con data e ora al
secondo** di ogni passaggio (creato, ricevuta caricata, pagamento confermato da
Stripe o dall'amministrazione, cashback accreditato). Il bottone **"Riscatto
#…" / "Ordine #…" / "Contratto #…"** sulla riga apre quella pratica con tutti i
suoi movimenti collegati, ognuno a sua volta apribile; per un contratto vedi
anche tutte le rate con la data di incasso. Resta il pulsante **Esporta CSV**.

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
- **Miei Clienti → Attiva nuovo contratto** (Session 52) — apre per il tuo
  cliente la stessa pratica di attivazione che vede lui: dati e "quanti POD
  hai?", documenti d'identità, contratto per ogni POD, invio. **Il pagamento lo
  fa il cliente** dal suo account ("I miei Contratti" → "Paga"). Il pulsante
  **Pratiche** accanto a ogni cliente mostra tutte le sue pratiche — anche
  quelle che ha compilato da solo — con cosa manca a ciascuna; una bozza si
  riprende da lì. Ogni punto è un contratto a sé anche per le tue provvigioni.
- **Prodotti da Condividere** — lo stesso catalogo che vede il cliente, con un
  pulsante **Condividi** su ogni prodotto: un link diretto a quel prodotto con
  il tuo codice promoter già incorporato, pronto da inviare a un cliente.
  C'è anche un pulsante **Condividi il tuo link** in alto (link generico,
  senza prodotto specifico).
  - **Dal telefono si apre direttamente il menu di condivisione del
    dispositivo** (WhatsApp, Telegram, SMS, email, e qualsiasi altra app tu
    abbia installata): non devi più copiare il link, uscire dall'app e
    incollarlo. Da computer, dove quel menu non esiste, il link viene copiato
    negli appunti come prima — il pulsante ti dice quale delle due cose è
    successa ("Link condiviso!" oppure "Link copiato!").
- **Invita un amico** — la tua lista personale di invitati, separata dalla
  rete commerciale (vedi sotto, vale identica anche per i clienti).
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
- **Wallet** — lo stesso portafoglio interno (saldo e storico mostrati in
  "LialCash", non euro) descritto per l'area Cliente: saldo, indirizzo
  personale, invio/ricezione verso qualsiasi altro wallet della piattaforma,
  storico transazioni. È lo stesso wallet indipendentemente dal ruolo con
  cui accedi (se hai sia login Cliente sia Promoter, il saldo è unico e
  condiviso tra le due aree).

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
- **Pratiche** (Session 52) — le pratiche di attivazione: filtri rapidi *Da
  verificare*, *Documenti mancanti*, *Non pagate*, *Rate non riscosse*, *In
  compilazione*. Aprendo una pratica vedi intestatario, documenti comuni
  (validi per tutti i punti), tentativi di pagamento con carta, e ogni punto
  come contratto a sé con i pulsanti **Documenti**, **Provvigioni**,
  **Recensisci** e — se paga a rate — **Interrompi addebiti** (toglie solo quel
  contratto dall'addebito mensile, gli altri continuano). **"Approva i N
  contratti in revisione"** mostra l'anteprima provvigioni di ciascuno e li
  approva tutti in un colpo, ognuno con la sua anteprima salvata.
- **Tutti i Contratti** — elenco con nome cliente (non solo l'ID), prodotto e
  punto di fornitura con nome comprensibile, colonna **Origine** (vedi sotto),
  colonna **Importo** con netto / IVA / totale, colonna scadenza/rinnovo colorata
  per urgenza, filtro per anno (storico separato per anno, utile perché ogni
  anno ci saranno contratti da rinnovare), filtri per stato, azione di
  transizione di stato con motivazione obbligatoria. Il pulsante **Recensisci**
  apre anche i **documenti del contratto** (carta d'identità, codice fiscale,
  bolletta, visura camerale per aziende/condomini): da qui puoi caricare un
  documento per conto del cliente (es. se te lo ha inviato via email) e,
  quando il cliente ha caricato il suo, **approvarlo o respingerlo** con una
  nota — la nota compare automaticamente al promoter nella sua vista di rete,
  cosi sa cosa manca e può contattare il cliente.
  - La colonna **Origine** risponde a colpo d'occhio alla domanda "chi ha
    fatto questo contratto?": *Compilato dal promoter — Nome Cognome* quando
    un promoter lo ha completato **al posto** del cliente, *Sottoscritto dal
    cliente* quando è stato il cliente da solo, *Creato da amministrazione*
    quando lo ha inserito lo staff. Sotto, quando diverso, compare anche
    *Segnalato da …*, cioè il promoter che aveva portato quel cliente in
    Lial Energy la prima volta — può essere una persona diversa da chi ha
    compilato il contratto, ed è quella che riceve l'eventuale bonus primo
    segnalatore.
  - La colonna **Importo** mostra il totale del contratto così com'era **nel
    momento in cui è stato firmato**: se domani modifichi il prezzo o l'IVA
    del prodotto, i contratti già esistenti non cambiano. I contratti creati
    prima dell'introduzione di questa colonna mostrano "—": il sistema
    volutamente non inventa un prezzo a posteriori.
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
  collegati). Per un prodotto Dropshipping/Partner puoi anche impostare uno
  **sconto pagabile in LialCash** (percentuale del prezzo) e/o abilitare
  **"cashback subito"**: se attivo, il cliente potrà scegliere in fase di
  acquisto di pagare un 5% in più per farselo riaccreditare in LialCash a
  pagamento confermato. Nessuna delle due opzioni è mai disponibile sui
  prodotti Lial Energy (categoria Interno).
- **Ordini** — la coda di tutti gli ordini Shop (prodotti Dropshipping/
  Partner, creati dal cliente stesso o da un amministratore per suo conto):
  filtro per stato/metodo di pagamento, dettaglio con id prodotto, LialCash
  applicati, eventuale sovrapprezzo cashback, prova di pagamento caricata
  dal cliente (se bonifico). **Conferma bonifico ricevuto** segna l'ordine
  pagato e, se il prodotto lo prevede, accredita automaticamente il
  cashback; un ordine pagato con carta si conferma da solo non appena
  Stripe conferma l'addebito (il bottone manuale è disabilitato in quel
  caso, per non poter mai accreditare cashback senza un pagamento reale
  confermato da Stripe). **Nuovo Ordine** crea un ordine per conto di un
  cliente.
- **Riscatti Fatture** — la coda delle richieste "Riscatta Cashback" dei
  clienti: **Verifica importo** (apri il documento caricato, conferma
  l'importo reale -- da questo momento il cliente sa quanto pagare e può
  farlo con carta o bonifico), **Conferma bonifico ricevuto** (solo se il
  cliente ha scelto bonifico; se ha scelto carta l'accredito è automatico
  alla conferma di Stripe), **Rifiuta** con motivo.
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
- **Wallet** — visione d'insieme di tutti i portafogli della piattaforma
  (saldo e ogni transazione mostrati in "LialCash", non euro): saldo e
  indirizzo di ogni cliente/promoter (con ricerca per nome, email o
  indirizzo), più il registro globale di tutte le transazioni (ricariche,
  trasferimenti tra utenti, storni, debiti d'acquisto ordini, cashback),
  filtrabile per tipo ed esportabile in CSV. Da qui puoi anche **stornare**
  una transazione fatta per errore (un clic su "Storna" con motivazione):
  non cancella la transazione originale, ne registra una di correzione
  collegata, così lo storico resta sempre tracciabile. La ricarica manuale
  di un singolo cliente ("Ricarica") è riservata al **Super Admin**
  (permesso `wallet.credit`, più stretto del resto della superficie
  wallet); si fa più comodamente dal suo popup in "Anagrafiche Clienti"
  (vedi sopra) oppure da questa sezione, che resta la vista d'insieme su
  tutta l'organizzazione.
  - **Se una ricarica dà errore, NON ripeterla alla cieca: ricarica la
    pagina e controlla il saldo prima.** In generale il sistema è ora
    protetto — riprovare la stessa ricarica non accredita due volte, perché
    la richiesta porta con sé una chiave che il server riconosce come "è la
    stessa operazione di prima". Fino a settembre 2026 però esisteva un
    difetto per cui un problema del server di posta faceva comparire un
    errore su una ricarica **già andata a buon fine**, e il secondo clic
    accreditava davvero una seconda volta; è corretto, ma l'abitudine di
    verificare il saldo prima di ripetere un'operazione sui soldi resta
    quella giusta.
- **Contabilità** — tutti i movimenti di tutti i clienti (LialCash, ordini,
  riscatti e, da Session 54, le rate dei contratti), filtrabili per cliente.
  Ogni riga e ogni riferimento "Ordine / Riscatto / Contratto #…" apre lo stesso
  dettaglio che vede il cliente, con la cronologia completa di chi ha fatto
  cosa e quando.

## 4. Cosa succede "dietro le quinte" quando un contratto si attiva

- **Anteprima provvigioni** (Session 50): quando l'amministratore approva un
  contratto (o lo porta comunque verso l'attivazione), la finestra
  *Recensisci* mostra prima **chi riceve cosa**: il promoter del cliente e
  gli sponsor sopra di lui, ciascuno con grado, tipo di provvigione e
  importo; se il cliente paga a rate, quanto parte a ogni rata e fino a
  quando; se non ha ancora pagato, come verrebbero divise nelle tre
  modalità. Il pulsante di conferma si sblocca solo spuntando *"Ho
  controllato l'anteprima"*. L'anteprima accettata resta salvata: la riapri
  dal pulsante **Provvigioni** del contratto, insieme alla tabella delle
  rate (pagata / non riuscita / in attesa, e quando sono partite le relative
  provvigioni). Se Stripe non riesce a incassare una rata e il cliente paga
  in altro modo, lì c'è **"Conferma rata ricevuta"**.
- **Rate**: pagamento unico → le provvigioni partono una volta sola, intere.
  3 o 12 rate → ogni promoter riceve la sua provvigione divisa in 3 o 12
  quote, una per ogni rata effettivamente incassata (la somma delle quote è
  esattamente la provvigione intera).
- Creare o inviare un contratto **non genera mai** una provvigione.
- La provvigione viene calcolata **una sola volta**, quando un contratto passa
  allo stato **Attivo** — cioè quando ci sono **sia** il pagamento **sia**
  l'approvazione dei documenti, in qualunque ordine arrivino — non quando viene solo pagato (quello è uno stato
  intermedio, "Pagata", distinto da "Attiva"; se un contratto resta fermo lì
  troppo a lungo, l'amministrazione lo vede nell'elenco "Richiede attenzione").
- Il calcolo cristallizza la catena degli sponsor così com'era in quel momento
  — spostamenti successivi nella rete non cambiano mai calcoli già fatti.
- Ogni movimento di provvigione riporta una spiegazione testuale.
- **IVA**: un contratto intestato a un **privato non ha IVA**; uno intestato a
  un'**azienda / partita IVA** è prezzo + IVA. Lo decide la tipologia del
  cliente, non il prodotto — il prodotto stabilisce solo *quale* aliquota
  applicare quando l'IVA c'è. Il conteggio viene congelato sul contratto alla
  creazione.
- **Quali contratti vede un cliente**: ogni prodotto di tipo contratto ha un
  "Cliente Target" (*Solo privati* / *Solo aziende* / *Entrambi*, impostabile
  dall'amministrazione in Prodotti). Un cliente vede a catalogo solo i
  contratti compatibili con la propria tipologia — e il sistema li rifiuta
  comunque anche se qualcuno provasse ad aggirare la schermata.
- **Cashback sul contratto** (se attivato dall'amministrazione sul prodotto):
  quando il contratto risulta pagato, al cliente viene accreditata
  automaticamente una percentuale del totale pagato come LialCash sul wallet.
  **Non c'è nessun 5% aggiuntivo da pagare**: quella regola riguarda solo il
  riscatto delle fatture dei partner esterni e gli acquisti nello Shop, non i
  servizi Lial Energy. Di default è disattivato su tutti i prodotti.
- **Bonus primo segnalatore** (se attivato dall'amministrazione sul prodotto):
  un importo extra riconosciuto **una sola volta per contratto** al promoter
  che aveva portato quel cliente in Lial Energy, **in aggiunta** alla
  provvigione normale e mai al posto suo. Non va a tutta la rete, e non va al
  promoter che si limita a compilare il contratto se è una persona diversa.
- Se il venditore indicato in un contratto non esiste o non è attivo, il
  sistema **rifiuta la creazione del contratto** con un errore chiaro — prima
  poteva capitare che il contratto si attivasse comunque senza pagare
  nessuno, senza nessun avviso; è stato corretto (vedi
  `docs/paid-contract-commission-audit.md`).

### "Invita un amico" (tutti: clienti e promoter)

Ogni persona con un accesso — cliente o promoter — ha nella propria area una
sezione **Invita un amico** con:

- **il proprio link personale**, da condividere (dal telefono si apre
  direttamente WhatsApp, Telegram, SMS…);
- **la lista di chi si è iscritto con quel link**, con tre stati: *Iscritto*
  (registrato, nessun contratto), *Contratto in corso*, *Attivo* (contratto
  realmente in forza);
- **il conteggio verso il premio**: ogni **5 amici invitati con un contratto
  attivo** si può richiedere una **gift card da 25 euro**. Il premio si
  ripete: vale a 5, a 10, a 15 e così via, non solo per i primi 5.

Due cose importanti da capire:

1. **Questa lista non è la rete commerciale e non paga provvigioni.** È una
   lista piatta, a un livello solo. Dove finisce in rete la persona che si
   iscrive non lo decide questa lista:
   - se chi invita **è un promoter**, l'iscritto entra nel suo albero, come
     sempre;
   - se chi invita **è un cliente semplice**, l'iscritto entra sotto **il
     promoter di quel cliente**.
   In entrambi i casi l'iscritto compare comunque nella lista di chi lo ha
   invitato.
2. **La gift card non arriva in automatico.** Cliccando "Richiedi" parte una
   richiesta all'amministrazione, che consegna il premio e lo segna; la nota
   scritta dall'amministrazione compare nella tua lista richieste. Questo
   permette di scegliere di volta in volta cosa dare.

Dal lato amministrazione, le richieste si gestiscono in **Omaggi Inviti**.

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
