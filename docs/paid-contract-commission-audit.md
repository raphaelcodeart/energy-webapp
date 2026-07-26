# Audit: dal contratto pagato alla distribuzione provvigionale

Data: 2026-07-26. Perimetro: `apps/api/app/domains/{contracts,commissions,network,outbox}`.
Metodo: lettura diretta del codice sorgente attualmente in esecuzione (non della
documentazione), confrontata poi con `docs/business-rules.md` e
`docs/commission-engine-specification.md` per individuare eventuali scostamenti.

## 1. Stack e componenti coinvolti (per orientamento, non ripetuto altrove)

- Backend: FastAPI (Python 3.12) + SQLAlchemy 2.0 async + PostgreSQL 16, dominio per
  dominio (`app/domains/<nome>/{models,schemas,service,router}.py`).
- Worker asincrono: Celery, stesso codice del backend (nessuna reimplementazione).
- Pattern: transactional outbox (`domain_outbox`) per gli eventi di dominio (ADR 0005).

## 2. Dove cambia lo stato del contratto

Un solo punto di ingresso per **qualsiasi** cambio di stato:
`apps/api/app/domains/contracts/service.py::transition_contract()`, chiamato da
`POST /api/contracts/{id}/transition` (`contracts/router.py`, permesso
`contracts.review`). Non esistono altri endpoint, listener o job che scrivano
`Contract.status` direttamente.

La macchina a stati è esplicita in `contracts/state_machine.py`:

```
... → PAYMENT_PENDING → PAID → ACTIVATION_PENDING → ACTIVE → ...
```

**Non esiste alcun automatismo** che faccia avanzare un contratto da `PAID` ad
`ACTIVATION_PENDING` o da `ACTIVATION_PENDING` ad `ACTIVE`. Ogni transizione,
inclusa quella verso `PAID`, richiede una chiamata esplicita e manuale
all'endpoint di transizione da parte di un operatore autorizzato (permesso
`contracts.review`).

## 3. Conferma pagamento: endpoint, webhook, riconciliazione automatica

- **Endpoint dedicato alla conferma pagamento**: non esiste. La conferma pagamento è
  semplicemente una `POST /contracts/{id}/transition` con `to_status: "PAID"`, lo
  stesso endpoint generico usato per ogni altra transizione (approvazione, rifiuto,
  attivazione...).
- **Webhook da payment provider**: non esiste. Non c'è un dominio `payments`, non
  c'è un `PaymentProvider`/`MockPaymentProvider`, non c'è alcuna route che riceva
  callback esterne. Questo è coerente con `docs/admin-dashboard-plan.md` §7/§10, che
  marca "Liquidazioni/Pagamenti" come Fase 7, non ancora implementata, e il
  provider di pagamento reale come esplicitamente fuori scope.
- **Riconciliazione automatica**: non esiste alcun job schedulato che verifichi
  pagamenti o avanzi automaticamente lo stato di un contratto.
- **Conferma manuale da amministratore**: è l'**unico** meccanismo oggi presente.
  L'interfaccia admin (`admin-client-page.tsx`) espone un'unica modale di
  transizione con un menu a tendina che elenca **tutti** gli stati possibili,
  senza distinguere quali siano validi dallo stato corrente (la validazione avviene
  solo lato server, tramite `assert_transition_allowed`) e senza alcuna indicazione
  che, dopo aver segnato un contratto `PAID`, servano **altre due transizioni
  manuali distinte** (`ACTIVATION_PENDING`, poi `ACTIVE`) prima che le provvigioni
  vengano generate.

## 4. Evento che avvia il motore provvigionale

`transition_contract()` calcola l'evento da emettere tramite
`state_machine.event_name_for(from_status, to_status)`:

| Transizione | Evento emesso |
|---|---|
| `PAYMENT_PENDING → PAID` | `PaymentConfirmed` |
| `ACTIVATION_PENDING → ACTIVE` | `ContractActivated` |
| `ACTIVE → RENEWED` | `ContractRenewed` |

L'evento viene scritto nella stessa transazione del cambio di stato tramite
`outbox_service.enqueue()` (mai emesso prima del commit — outbox transazionale,
ADR 0005). Il worker Celery (`celery_app.py`, beat ogni minuto) chiama
`commissions/tasks/dispatch.py::process_pending_outbox_events()`, che however
**filtra esplicitamente gli eventi**:

```python
COMMISSION_TRIGGER_EVENTS = {"ContractActivated", "ContractRenewed"}
```

**`PaymentConfirmed` non è nell'insieme.** Il pagamento confermato, da solo, non
avvia mai il motore provvigionale — solo l'evento `ContractActivated` (o
`ContractRenewed`) lo fa. Questo è **comportamento intenzionale e documentato**,
non un bug: `docs/business-rules.md` riga 55-56 dichiara esplicitamente "Commissions
are generated exactly once, when a contract transitions into `ACTIVE`". Rispetto
alla domanda posta ("quando un contratto viene confermato come pagato, il sistema
avvia il processo provvigionale") — **la risposta tecnica corretta è: no, non
all'atto del pagamento, ma solo quando il contratto raggiunge `ACTIVE`**, due
transizioni manuali dopo. Vedi §8 per l'implicazione operativa di questo, che è
il problema reale individuato in questo audit.

## 5. Identificazione del produttore del contratto

`Contract.contract_attribution_id → ContractAttribution.producer_agent_id`,
impostato in `contracts/service.py::create_contract()` **direttamente dal payload
client** (`ContractCreate.producer_agent_id`, un semplice `uuid.UUID`), **senza
alcuna validazione** che quell'UUID corrisponda a un `AgentProfile` realmente
esistente, attivo, e appartenente a questa organizzazione. Vedi §8, problema #1 —
questa è la lacuna più grave individuata.

## 6. Recupero della rete commerciale e livelli elaborati

Al momento della transizione verso `ACTIVE` (solo in quel ramo del codice),
`transition_contract()` chiama
`network_service.create_snapshot_for_contract(producer_agent_id=...)`, che:

1. Legge **tutti** gli antenati attivi di `producer_agent_id` dalla closure table
   (`network_closure`, nessun filtro `LIMIT`/`WHERE depth <= N`) — cioè l'intera
   linea ascendente fino alla radice, non un numero di livelli hardcoded.
2. Congela ogni antenato con la sua qualifica **al momento dell'attivazione**
   (`rank_id_at_snapshot`) in `network_snapshots`/`network_snapshot_nodes` —
   immutabile: spostamenti futuri nella rete o cambi di qualifica non alterano mai
   un calcolo già effettuato.

**Non c'è un cap tecnico a 12 livelli**, ma il risultato pratico converge comunque
lì: la scala qualifiche ha un numero finito di gradini (S1→S3, TL1→TL4, MD1→MD5 =
12 ranghi), quindi oltre il livello in cui si raggiunge il rango più alto
qualunque ulteriore antenato riceve automaticamente zero (nessuna differenza
imprenditoriale residua da distribuire). Verificato corretto — non è una lacuna.

## 7. Regole di calcolo utilizzate

`commissions/services/run_calculation.py::run_calculation_for_contract()`:

1. Costruisce la catena (`_build_chain`) da `network_snapshot_nodes`, ordinata per
   profondità crescente, con qualifica e gettone personale **congelati** allo
   snapshot.
2. Delega il calcolo puro a
   `commissions/calculators/entrepreneurial_difference.py::calculate_chain()`:
   - il produttore (depth 0) riceve il proprio gettone personale intero
     (`PERSONAL_TOKEN`);
   - ogni antenato successivo riceve **solo la differenza marginale** fra il
     proprio gettone e quanto già distribuito ai livelli inferiori
     (`ENTREPRENEURIAL_DIFFERENCE`), mai l'importo pieno — questo è esattamente
     l'algoritmo "incrementale" richiesto, verificato da 7 test unitari puri
     (`commissions/tests/test_entrepreneurial_difference.py`), tutti verdi;
   - un antenato con qualifica uguale o inferiore a quanto già distribuito riceve
     zero, con spiegazione testuale registrata (auditabilità).
3. Verificato corretto — algoritmo dell'incremento implementato fedelmente e
   testato.

### Regola del 33% (branch cap) — NON collegata al motore live

`docs/commission-engine-specification.md` (l'algoritmo di riferimento, righe 49-56)
descrive esplicitamente un passo `eligible_amount = apply_branch_cap(...)` seguito
da `diff = min(diff, eligible_amount)`, e la sezione "Test matrix" del medesimo
documento dichiara "two branches, one over the 33% cap → excess excluded, explained"
come **"Implemented now"**.

Verificato che questo non è vero: `apply_branch_cap()`
(`commissions/policies/branch_cap.py`) esiste, è una funzione pura corretta, ed è
testata **in isolamento** (`test_branch_cap.py`) — ma **non viene mai chiamata**
da `calculate_chain()` né da `run_calculation_for_contract()`. Il motore live
distribuisce quindi la differenza imprenditoriale piena, senza applicare alcun
tetto al 33% sulla produzione di un singolo ramo.

Non ho implementato questa integrazione in questa sessione: `business-rules.md`
riga 97-98 marca esplicitamente `single_branch_cap_percentage` come **PLACEHOLDER**
e `docs/open-questions.md` #6 lascia esplicitamente indefinito il denominatore
("qualifying group production") su cui il 33% dovrebbe essere calcolato — cioè su
quale finestra temporale, e su quale insieme di contratti/rami. Implementare
l'integrazione senza questa decisione di business significherebbe inventare una
regola non concordata. Resta un'azione da pianificare esplicitamente (vedi §9).
**Non rientra nei 5 punti esplicitamente richiesti in questo audit** (che
riguardano produttore, rete ascendente, N livelli, calcolo incrementale,
assenza di duplicazioni) mentre il 33% è un tetto aggiuntivo e distinto,
tuttora una domanda di business aperta.

## 8. Come viene evitata la doppia elaborazione

Due livelli di protezione, verificati:

1. **A livello di calcolo**: `run_calculation_for_contract()` verifica prima di
   tutto se esiste già una `CommissionCalculation` per la stessa coppia
   `(contract_id, trigger_event_id)` — se sì, no-op, ritorna il record esistente.
   **Verificato lacunoso**: questo controllo è solo applicativo (SELECT poi
   INSERT), **senza vincolo univoco a livello di database** sulla coppia. Vedi
   problema #3.
2. **A livello di movimento**: ogni `CommissionMovement` ha una `idempotency_key`
   deterministica (`sha256(contract_id:trigger_event_id:agent_id:movement_type)`)
   con **vincolo univoco a livello di database**
   (`uq_commission_movements_idempotency_key`). Questo è il vero argine contro un
   pagamento duplicato reale: anche se il controllo applicativo al punto 1 fallisse
   per una race condition, un secondo tentativo di scrivere lo stesso movimento
   fallirebbe con una violazione di vincolo, e l'intera transazione (che include
   calcolo + step + movimenti in un unico commit) verrebbe annullata. **Verificato
   solido come rete di sicurezza finale.**

Test esistenti che verificano questo comportamento (a livello di dispatch, non di
race condition diretta): `test_reprocessing_outbox_does_not_duplicate_movements` —
verde.

## 9. Problemi individuati (in ordine di gravità)

### Problema #1 — CRITICO: nessuna validazione del produttore alla creazione del contratto

`create_contract()` accetta `producer_agent_id` dal client senza verificare che
esista un `AgentProfile` con quell'id in questa organizzazione. Se l'id è
inesistente o errato:

- `create_snapshot_for_contract()` interroga la closure table per quell'agente e
  non trova nulla → lo snapshot viene creato con **zero nodi**;
- `_build_chain()` in `run_calculation_for_contract()` ritorna una catena vuota →
  la funzione fa semplicemente `return None`, **senza sollevare errori, senza
  scrivere alcun record, senza alcuna voce di audit**;
- il dispatcher (`process_pending_outbox_events`) segna comunque l'evento come
  processato (`mark_processed`), perché non distingue "nessun beneficiario da
  pagare" da "errore nell'identificare il beneficiario".

Risultato: un contratto attivato con un `producer_agent_id` sbagliato **non paga
nessuno, silenziosamente, per sempre**, e nulla nel sistema lo segnala. Questo è
esattamente lo scenario che il punto 1 della richiesta dell'utente chiede di
escludere ("al venditore che ha materialmente prodotto il contratto").

### Problema #2 — GRAVE: un evento non processabile blocca l'intero batch (poison pill)

`process_pending_outbox_events()` non ha alcun `try/except` attorno alla chiamata a
`run_calculation_for_contract()`. Se quella chiamata solleva un'eccezione (per
esempio il ramo `ValueError("Contract has no network snapshot...")`, oggi
teoricamente irraggiungibile per `ContractActivated` ma non per anomalie di dati
future, o qualunque eccezione imprevista), l'eccezione si propaga fuori dal loop
`for event in events`, interrompendo l'elaborazione di **tutti gli altri eventi
non correlati** nello stesso batch, e l'evento incriminato non viene mai segnato
come processato — quindi Celery beat lo ritenterà ogni minuto, fallendo di nuovo
e ribloccando ogni volta l'intero batch. Un singolo contratto con dati anomali può
quindi bloccare la generazione di provvigioni per **tutti gli altri contratti**
dell'organizzazione (e potenzialmente di altre organizzazioni, se coesistono
eventi non correlati nello stesso batch di 100).

### Problema #3 — MEDIO: idempotenza del calcolo non garantita a livello di database

Come descritto al punto 8: il controllo "esiste già un calcolo per questo
`(contract_id, trigger_event_id)`" è solo applicativo. In una race condition
(due dispatch concorrenti dello stesso evento — possibile se un run di Celery
beat impiega più di un minuto e si sovrappone al successivo) potrebbero essere
create due righe `CommissionCalculation` per lo stesso evento. Il vincolo univoco
sui movimenti impedisce un **pagamento** duplicato in quasi tutti i casi, ma non in
quello (raro ma possibile) in cui tutti gli step calcolati abbiano importo zero —
in quel caso non viene scritto alcun `CommissionMovement` e quindi nessun vincolo
la blocca, risultando in righe di calcolo duplicate nello storico (inquinamento
del log contabile, non un doppio pagamento reale ma comunque una violazione della
garanzia di esattamente-una-volta dichiarata nella specifica).

### Problema #4 — MEDIO: nessuna visibilità operativa sui contratti pagati ma non attivati

Come descritto al §3-4, avanzare da `PAID` ad `ACTIVE` richiede due transizioni
manuali distinte, e nulla nella dashboard amministrativa segnala un contratto
fermo a `PAID` o `ACTIVATION_PENDING`. La lista "Richiede attenzione" già presente
nella Panoramica admin (`reports/service.py::REVIEW_QUEUE_STATUSES`) copre solo
`SUBMITTED`/`DOCUMENTS_PENDING`/`UNDER_REVIEW` — esclude esattamente gli stati in
cui un contratto è "soldi incassati, provvigioni non ancora generate".

### Problema #5 — BASSO: la specifica dichiara "implementato" un comportamento che non lo è

`commission-engine-specification.md`'s test matrix elenca la regola del 33% come
"Implemented now" quando in realtà non è collegata al motore live (§7). Questo è
un problema di accuratezza documentale che può indurre in errore chi si fida della
specifica senza verificare il codice — corretto in questa sessione (vedi diff).

## 10. Riepilogo rispetto ai 5 punti della richiesta

| # | Richiesta | Esito verificato |
|---|---|---|
| 1 | Il venditore che ha prodotto il contratto viene pagato | **Lacuna critica trovata e corretta** (Problema #1) — prima di questa sessione poteva fallire silenziosamente |
| 2 | I veri promoter/responsabili nella linea ascendente vengono pagati | **Corretto, verificato** — catena costruita da dati reali (`network_snapshot_nodes`), nessun placeholder |
| 3 | Tutti gli N livelli della rete vengono attraversati | **Corretto, verificato** — nessun cap tecnico, limite naturale dato dalla scala qualifiche finita |
| 4 | Calcolo incrementale della Differenza Imprenditoriale | **Corretto, verificato** — algoritmo fedele alla specifica, 7 test unitari verdi |
| 5 | Nessuna duplicazione/errore/pagamento ripetuto | **Solido ma rafforzato in questa sessione** (Problemi #2, #3) — vincolo DB aggiunto, gestione errori nel dispatcher irrobustita |

## 11. Modifiche implementate in questa sessione

Vedi `docs/implementation-progress.md` per il changelog completo. In sintesi:

1. Validazione di `producer_agent_id` in `create_contract()` — rifiuta la
   creazione con un errore chiaro se l'agente non esiste o non appartiene
   all'organizzazione (Problema #1).
2. `run_calculation_for_contract()` non fallisce più in silenzio a catena vuota:
   scrive una `CommissionCalculation` con `status="FAILED"` e una voce di audit
   log, cosi' l'anomalia e' visibile e interrogabile (difesa in profondità,
   copre anche eventuali anomalie di dati preesistenti).
3. `process_pending_outbox_events()` isola ogni evento in un proprio
   try/except: un evento fallito viene loggato e **non** blocca gli altri
   (Problema #2).
4. Vincolo univoco a livello di database su
   `commission_calculations(contract_id, trigger_event_id)`
   (migrazione `0003`), con gestione esplicita della race condition nel
   dispatcher (Problema #3).
5. La lista "Richiede attenzione" della dashboard admin ora segnala anche i
   contratti fermi a `PAID`/`ACTIVATION_PENDING` (Problema #4).
6. Correzione della specifica per non dichiarare "implementato" il 33% branch
   cap (Problema #5) — resta esplicitamente pianificato, non implementato.

## 12. Non ancora fatto (richiede una decisione di business, non solo codice)

- **Regola del 33%** collegata al motore live: richiede prima una decisione su
  cosa costituisca "qualifying group production" (periodo, insieme di contratti)
  — vedi `docs/open-questions.md` #6. Non implementato per non inventare una
  regola di business non concordata.
- Non è stato aggiunto alcun automatismo che faccia avanzare un contratto da
  `PAID` ad `ACTIVE` automaticamente: l'attivazione resta, per design, un evento
  distinto e controllato (spesso corrisponde allo switch reale del punto di
  fornitura, non semplicemente al passare del tempo dal pagamento). Introdurlo
  senza una richiesta esplicita avrebbe significato cambiare una regola di
  business già documentata e deliberata in `business-rules.md`.
