# Guida Utente — Piattaforma Lial Energy

Questa guida spiega come usare la piattaforma **oggi**, nello stato attuale dello
sviluppo (vedi `docs/implementation-progress.md` per il dettaglio tecnico di cosa
è completo e cosa arriverà nelle prossime fasi). Non promette funzionalità non
ancora costruite.

## 1. Come accedere

Apri il browser su:
```
http://<indirizzo-del-server>/login
```
(oppure `https://<tuodominio>` una volta configurato un dominio con HTTPS — vedi
`docs/server-migration-guide.md` sezione 4.6).

Nella pagina di login servono **tre informazioni**:

| Campo | Cosa inserire |
|---|---|
| Organization ID | L'identificativo dell'organizzazione (un codice tipo `9e0a594e-7d7a-...`). Te lo comunica chi amministra il sistema, oppure — in ambiente demo — viene stampato quando si esegue `python -m app.seed`. |
| Email | La tua email registrata nel sistema |
| Password | La tua password |

Se inserisci credenziali sbagliate, il messaggio di errore è sempre lo stesso
("email o password non validi") sia che l'email non esista sia che la password
sia sbagliata — è una scelta di sicurezza intenzionale (evita che un malintenzionato
scopra quali email sono registrate).

Dopo **5 tentativi falliti** l'account viene bloccato temporaneamente (15 minuti).

Dopo il login resti connesso per un massimo di 15 minuti di sessione (poi va
rifatto il login — il rinnovo automatico della sessione non è ancora attivo,
vedi `docs/implementation-progress.md`).

## 2. Le tre aree della piattaforma

In base al tuo ruolo, dopo il login vieni indirizzato a una di queste tre aree.
Ogni ruolo vede **solo i propri dati** — non è una limitazione dell'interfaccia,
è imposta anche lato server, quindi non è aggirabile.

### 2.1 Area Cliente (`/customer`)

Per chi ha un account di tipo cliente. Mostra:
- **I tuoi contratti**, con lo stato attuale tradotto in italiano (Bozza, Inviata,
  In revisione, Approvata, Attiva, Cessata, Respinta, ecc.)

Cosa **non** è ancora disponibile in quest'area (arriverà in fasi successive):
download documenti, storico pagamenti/fatture, gestione consumi, richieste di
assistenza, notifiche.

### 2.2 Area Promoter (`/promoter`)

Per collaboratori/venditori/team leader/manager della rete commerciale. Mostra:
- **Codice promoter** — il tuo identificativo nella rete
- **La tua rete** (diretti e discendenti) — una tabella con ogni agente nel tuo
  ramo e la relativa "profondità" (0 = tu stesso, 1 = i tuoi diretti, 2 = i loro
  diretti, ecc.). Vedi **solo il tuo ramo**: un ramo parallelo (es. quello di un
  collega allo stesso livello) non è visibile, nemmeno modificando l'URL a mano —
  il controllo è fatto dal server, non dal browser.
- **Le tue provvigioni** — l'elenco dei movimenti maturati (gettone personale,
  differenza imprenditoriale, ecc.) con importo, stato e data, più il totale.

Cosa non è ancora disponibile: simulatore provvigioni nell'interfaccia (esiste
lato backend ma non ha ancora una pagina dedicata), storico qualifiche, gestione
richieste di spostamento di ramo, notifiche di cambio qualifica/rinnovo.

### 2.3 Area Amministratore (`/admin`)

Per ruoli di staff (Admin, Back Office, Accounting, Sales Manager, Super Admin —
con permessi leggermente diversi tra loro, vedi `docs/security-model.md`). Mostra:
- **Contratti per stato** — un riepilogo a riquadri di quanti contratti sono in
  ciascuno stato (ACTIVE, DRAFT, REJECTED, CANCELLED, ecc.), su tutta
  l'organizzazione
- **Tutti i contratti** — elenco completo con cliente e stato

Cosa non è ancora disponibile: creazione/approvazione contratti dall'interfaccia
(oggi richiede di chiamare l'API direttamente, vedi `docs/architecture.md` e la
documentazione OpenAPI su `/backend/docs`), gestione rete/qualifiche dall'interfaccia,
report esportabili, gestione utenti, audit log visualizzabile, stato backup/worker.

## 3. Cosa succede "dietro le quinte" quando un contratto si attiva

Anche se non ancora visibile in un'interfaccia dedicata, è utile sapere come
funziona il sistema, perché spiega numeri che potresti vedere:

- Creare o inviare un contratto **non genera mai** una provvigione.
- La provvigione viene calcolata **una sola volta**, nel momento esatto in cui un
  contratto passa allo stato **Attivo**.
- Il calcolo cristallizza la catena dei tuoi sponsor/superiori così com'era in
  quel momento — se in seguito la rete cambia (uno spostamento di ramo, per
  esempio), i calcoli già fatti **non cambiano mai retroattivamente**.
- Ogni movimento di provvigione riporta una spiegazione testuale (es. "Differenza
  tra gettone S2 di 45,00 EUR e quanto già riconosciuto ai livelli inferiori...").

## 4. Domande frequenti

**"Ho dimenticato l'Organization ID."**
Non è recuperabile dalla pagina di login — contatta chi amministra il sistema.
(Il recupero via email non è ancora implementato.)

**"Vedo 'Nessun profilo agente collegato a questo account' nell'area Promoter."**
Il tuo account utente esiste ma non è ancora collegato a un profilo di agente
nella rete commerciale — serve intervento di un amministratore.

**"Il mio contratto non appare nell'area Cliente."**
L'area Cliente mostra solo i contratti collegati al tuo account tramite il tuo
profilo cliente. Se il profilo cliente non è ancora collegato al tuo login,
contatta l'assistenza — è un collegamento che va fatto lato amministrazione.

**"Dopo 15 minuti devo rifare il login ogni volta, è normale?"**
Sì, per ora — il rinnovo automatico della sessione (silent refresh) non è ancora
stato implementato nel frontend. È una limitazione nota, non un errore.

**"Posso usare il sito da smartphone?"**
Le pagine sono responsive (si adattano allo schermo) ma non è stato fatto un
test approfondito su dispositivi mobili in questa fase.

## 5. Per chi amministra il sistema (non utenti finali)

Se hai bisogno di creare nuovi utenti, cambiare ruoli, collegare un profilo
cliente o promoter a un login, gestire la rete commerciale o le qualifiche — in
questa fase queste operazioni si fanno tramite l'API diretta (documentazione
interattiva su `/backend/docs`) o intervenendo sul database, non ancora tramite
un pannello di amministrazione dedicato. Vedi `docs/server-migration-guide.md` e
`docs/architecture.md` per i dettagli tecnici, oppure richiedi supporto a chi ha
sviluppato la piattaforma.
