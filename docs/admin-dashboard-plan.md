# Piano: Dashboard Amministrativa Completa

Documento tecnico richiesto prima di ogni modifica. Non è un contratto rigido —
verrà aggiornato man mano che ogni fase viene implementata e verificata (stesso
pattern di `docs/implementation-progress.md`, a cui questo documento rimanda per
lo stato session-by-session).

## 1. Analisi dello stato attuale

### 1.1 Stack e architettura (invariati, da riusare)
Modular monolith: FastAPI (`apps/api`, domini in `app/domains/<nome>/{models,schemas,service,router}.py`)
+ Next.js 16 App Router BFF (`apps/dashboard`) + PostgreSQL 16 + Celery/Redis. Auth
via cookie di sessione HttpOnly gestito dal BFF, RBAC granulare enforced lato
backend (`require_permission(...)`), mai solo lato frontend. Tutto documentato in
`docs/architecture.md`, `docs/security-model.md`, `docs/database-model.md`.

### 1.2 Domini backend già implementati
`auth`, `organizations`, `rbac`, `audit` (log append-only già esistente),
`network` (closure table, snapshot, move/recruit già implementati),
`referral` (promoter_codes, referral_events/sessions, customer_attributions —
**il modello dati per "iscrizione solo su invito" esiste già**, manca solo il
flusso pubblico che lo usa), `catalog` (prodotti/versioni), `customers`,
`contracts` (state machine esplicita, outbox pattern), `commissions` (motore
deterministico: gettone personale + differenza imprenditoriale + regola del
33%, ledger append-only `commission_movements`, simulatore).

### 1.3 Frontend già implementato
`AppShell` (sidebar + top bar con toggle tema, riusabile per ogni nuova
sezione), tre dashboard per ruolo (`admin-client-page.tsx`,
`promoter-client-page.tsx`, `customer-client-page.tsx`), pannelli CRUD admin
per clienti/promoter/prodotti, visualizzatore rete ad albero
(`branch-visualizer.tsx`, già interattivo espandibile/collassabile, **nessun
limite di profondità hardcoded** — supporta già i 12 livelli), simulatore
provvigioni, form di reclutamento promoter.

### 1.4 Cosa manca (rispetto a questa richiesta)
- Dashboard riepilogativa con KPI aggregati, grafici andamento mensile, filtri
  temporali, feed attività recenti, segnalazioni anomalie.
- Tabella contratti "enterprise": colonne che richiedono join multi-dominio
  (promoter, responsabile di rete, provvigione prevista/maturata, stato
  pagamento), filtri avanzati, azioni massive, drawer di dettaglio con tab.
- Azioni contratto oltre alla semplice transizione di stato: duplica,
  riassegna promoter, note interne, upload documenti (il dominio `documents`
  non esiste ancora), ricalcolo provvigioni on-demand.
- Vista rete "enterprise": ricerca globale nel grafo, navigazione bidirezionale
  (verso il basso e verso l'alto), volume/provvigioni aggregati per nodo.
- **Rettifiche provvigionali** (`commission_adjustments`/`commission_reversals`
  già a schema ma senza service/router), **liquidazioni** (`settlements`,
  entità nuova), **pagamenti** (`payments`, entità nuova — oggi c'è solo lo
  stub di interfaccia `PaymentProvider` menzionato nei documenti, non ancora
  scritto).
- UI per consultare l'audit log (il log esiste ed è scritto ad ogni operazione
  sensibile fin dalla prima sessione; manca solo la schermata per leggerlo).
- Ricerca globale, export CSV, area pubblica marketplace + registrazione
  vincolata al referral.

### 1.5 Un chiarimento terminologico importante — "wallet"
La richiesta parla di "assegnare al wallet di quel promoter". Il progetto ha
**deliberatamente scelto di non creare un wallet finanziario** fin dalla prima
sessione (`docs/business-rules.md`, `docs/commission-engine-specification.md`):
le provvigioni vivono in un **ledger contabile append-only**
(`commission_movements`), non in un saldo mutabile. Questa non è una scelta
stilistica: un wallet con saldo aggiornabile invita a scritture non
atomiche/sovrascritture, mentre il ledger append-only garantisce che ogni euro
sia tracciabile a un movimento specifico, mai sovrascritto. **Il piano sotto
implementa esattamente il comportamento richiesto (calcoli corretti, importi
mai sovrascritti silenziosamente, storico completo) tramite il ledger
esistente**, non tramite un nuovo saldo/wallet. Se in futuro serve davvero un
saldo denaro-disponibile-per-prelievo (es. per un'integrazione di pagamento
automatico), sarà una vista calcolata SOPRA il ledger (`SUM` dei movimenti
`PAYABLE`/`PAID`), mai una tabella scrivibile indipendente — evita la
divergenza tra "quello che dice il wallet" e "quello che dice la contabilità".

## 2. Proposta architetturale

Stessi principi già in uso: un dominio backend per area funzionale, RBAC
sempre lato server, ABAC per la visibilità di ramo, transazioni per ogni
scrittura economica, `idempotency_key` per operazioni ripetibili, audit su
ogni azione sensibile. Nessun nuovo microservizio, nessuna nuova tecnologia di
storage: PostgreSQL resta l'unica fonte di verità.

Nuovi domini backend:
- `documents` — upload/versioning documentale (MinIO, già nello stack Docker
  ma non ancora usato da codice applicativo).
- `settlements` — liquidazioni (`settlements`, `settlement_items`).
- `payments` — registrazione pagamento (non un vero PSP in questa fase:
  interfaccia `PaymentProvider` + implementazione `MockPaymentProvider`, come
  già descritto in `docs/architecture.md`).
- `reports` — endpoint di aggregazione per KPI dashboard + export CSV
  (nessuna tabella propria: legge dagli altri domini).

Estensioni a domini esistenti:
- `commissions`: service/router per rettifiche (`commission_adjustments`) e
  storni (`commission_reversals`) — le tabelle esistono già a schema, manca
  solo la logica applicativa.
- `contracts`: note interne, riassegnazione promoter, duplicazione.
- `referral`: endpoint pubblico di registrazione cliente vincolato a un
  `promoter_code` valido.

## 3. Schema delle pagine (frontend)

```
/admin
  Panoramica              <- NUOVO, home KPI (Fase 2)
  Contratti                <- potenziamento tabella esistente (Fase 3)
    /contratti/[id]         <- drawer o pagina dettaglio con tab (Fase 3)
  Anagrafiche Clienti       <- esiste
  Anagrafiche Promoter      <- esiste, potenziamento scheda dettaglio (Fase 4)
  Rete Commerciale          <- NUOVO, vista enterprise (Fase 5) -- oggi la rete
                               si vede solo dal lato promoter (il proprio ramo)
  Provvigioni               <- NUOVO (Fase 6)
  Liquidazioni              <- NUOVO (Fase 7)
  Prodotti & Marketplace    <- esiste
  Log Attività              <- NUOVO, lettura audit_log (Fase 8)
  Report & Export           <- NUOVO (Fase 9)

/promoter
  (esiste) Rete / Provvigioni / Simulatore -- albero rete da potenziare
  graficamente in Fase 5 (stesso componente riusato da admin e promoter)

/  (pubblico, NUOVO -- Fase 10, fuori da questa richiesta immediata)
  /marketplace              vetrina prodotti (pubblica)
  /r/[code]                 landing referral (endpoint backend già esiste,
                             manca la pagina pubblica che lo consuma)
  /signup?ref=CODE           registrazione cliente vincolata al promoter_code
```

## 4. Schema dei ruoli

I ruoli e i permessi granulari esistono già (`docs/security-model.md`,
`rbac/models.py`). Mappatura richiesta -> ruoli esistenti (nessun nuovo ruolo
necessario, solo nuovi permessi per le nuove azioni):

| Ruolo richiesto | Ruolo nel sistema | Note |
|---|---|---|
| Super amministratore | `SUPER_ADMIN` | già presente |
| Amministratore | `ADMIN` | già presente |
| Contabilità | `ACCOUNTING_OPERATOR` | già presente, da estendere con permessi liquidazioni/pagamenti |
| Responsabile commerciale | `SALES_MANAGER` | già presente |
| Responsabile di rete | `TEAM_LEADER` | già presente, ABAC di ramo già implementato (`network.read_branch` + `is_ancestor`) |
| Operatore | `BACK_OFFICE_OPERATOR` | già presente |
| Revisore | `AUDITOR` | già presente, va collegato alla nuova UI log |
| Promoter | `PROMOTER` | già presente |

Nuovi permessi da aggiungere (stesso pattern delle sessioni precedenti: lista
in `rbac/models.py` + patch dati sul DB live, non una migrazione):
`commission_adjustments.approve`, `settlements.manage`, `settlements.read`,
`payments.read`, `documents.upload`, `documents.download` (già a schema, mai
concesso), `audit.read` (già esiste, va solo collegato), `reports.export`
(già esiste).

## 5. Modelli dati

Tabelle **già esistenti** riusate as-is (nessuna modifica):
`contracts`, `contract_status_history`, `contract_events`,
`contract_attributions`, `agent_profiles`, `network_*`, `commission_plan_versions`,
`commission_rule_versions`, `commission_calculations`,
`commission_calculation_steps`, `commission_movements`, `commission_adjustments`,
`commission_offsets`, `commission_reversals`, `audit_log`.

Tabelle **nuove** necessarie (create via Alembic, non a mano):

```
settlements
  id, organization_id, agent_id, period_start, period_end,
  gross_amount_cents, adjustments_cents, reversals_cents, net_amount_cents,
  status (DRAFT/APPROVED/PAID), created_by, approved_by, paid_at,
  payment_method, payment_reference, notes, created_at

settlement_items
  id, settlement_id, commission_movement_id, amount_cents

payments
  id, organization_id, settlement_id, provider, provider_reference,
  status, amount_cents, receipt_document_id, created_at

documents
  id, organization_id, entity_type, entity_id, category, storage_key,
  original_filename, mime_type, size_bytes, checksum_sha256, version,
  uploaded_by, created_at

internal_notes
  id, organization_id, entity_type, entity_id, author_user_id, body,
  created_at
```

`settlement_items` è la chiave anti-doppio-pagamento: una liquidazione non
somma "tutte le provvigioni PAYABLE di un promoter", collega riga per riga i
movimenti inclusi, così un movimento non può finire in due liquidazioni per
errore (vincolo di unicità su `commission_movement_id`).

## 6. Endpoint necessari (indicativi, dettagliati fase per fase)

```
GET  /api/reports/dashboard-summary?period_from=&period_to=   Fase 2 -- ✅ implementato
GET  /api/reports/attention-items                              Fase 2 -- ✅ implementato
GET  /api/reports/recent-activity?limit=                       Fase 2 -- ✅ implementato
GET  /api/reports/contracts-timeseries?months=                 Fase 2 -- ✅ implementato
GET  /api/reports/commissions-timeseries?months=                Fase 2 -- ✅ implementato

GET  /api/contracts?status=&promoter_id=&...        Fase 3 (potenzia list esistente)
POST /api/contracts/{id}/notes                       Fase 3
POST /api/contracts/{id}/duplicate                   Fase 3
POST /api/contracts/{id}/reassign                    Fase 3
POST /api/contracts/{id}/recalculate-commissions      Fase 3

GET  /api/network/tree?root=&depth=                 Fase 5 (vista enterprise)

POST /api/commissions/{id}/adjust                     Fase 6
POST /api/commissions/{id}/reverse                    Fase 6
GET  /api/commissions?status=&agent_id=&...          Fase 6 (potenzia list esistente)

POST /api/settlements                                 Fase 7
POST /api/settlements/{id}/approve                    Fase 7
POST /api/settlements/{id}/pay                        Fase 7
GET  /api/settlements                                 Fase 7

GET  /api/audit?entity_type=&actor=&from=&to=        Fase 8

GET  /api/reports/export/contracts.csv                Fase 9
GET  /api/reports/export/commissions.csv              Fase 9
```

## 7. Piano di implementazione per fasi

| Fase | Contenuto | Stato |
|---|---|---|
| 1 | Layout amministrativo (AppShell, sidebar, top bar, tema) | ✅ Fatto (sessioni precedenti) |
| 2 | Dashboard riepilogativa (KPI, grafici, filtri temporali, attività recenti) | ✅ Fatto (Sessione 6) |
| 3 | Gestione contratti enterprise (tabella avanzata, dettaglio a tab, azioni) | Parziale (Sessione 11-12): form di creazione reale con cliente inline, `notes`; colonna scadenza/rinnovo con urgenza colorata, filtro per anno, nomi prodotto/punto di fornitura invece di ID grezzi. Mancano ancora: dettaglio a tab, duplicate/reassign/recalculate |
| 4 | Scheda promoter estesa (dati fiscali, coordinate pagamento, tab contratti/provvigioni) | Parziale (Sessione 11-12): la vista "La mia Azienda" copre contratti/provvigioni per persona e per livello, con grafico e drill-down per livello. Mancano ancora: dati fiscali/pagamento del promoter stesso |
| 5 | Vista rete enterprise (ricerca globale, navigazione bidirezionale, aggregati per nodo) | Parziale: vista admin org-wide con ricerca esiste (Sessione 10); aggregati per nodo esistono lato promoter (`branch-summary`, Sessione 11) ed **esposti anche lato admin** come widget "livelli e persone" whole-company (Sessione 12, `GET /network/organization/levels`) |
| 6 | Rettifiche/storni provvigionali (service+router su tabelle già a schema) | Pianificata |
| 7 | Liquidazioni e pagamenti (nuove tabelle, flusso completo) | Pianificata |
| 8 | UI audit log | Pianificata |
| 9 | Report ed esportazioni CSV | Pianificata |
| 10 | Area pubblica marketplace + registrazione vincolata a referral | Parziale (Sessione 11): link di condivisione promoter, pagina pubblica `/r/[code]`, registrazione invite-only reale (email+password, un solo passaggio). Mancano ancora: verifica PIN via email, completamento profilo obbligatorio al primo accesso, memoria della promozione tra login, attivazione multipla con scelta sede -- richiedono un servizio di invio email che il progetto non ha ancora |
| 11 | Sistema di ticket di supporto (cliente/promoter apre, staff risponde) | ✅ Fatto (Sessione 12) -- non era nel piano originale a 10 fasi, aggiunto su richiesta esplicita. Vedi `database-model.md §6` e `business-rules.md §Support tickets` |

Ogni fase: implementazione -> verifica reale (build, typecheck, test, curl
contro il database live) -> commit -> deploy -> smoke test sull'ambiente
HTTPS live -> solo allora fase successiva. Stesso metodo delle sessioni
precedenti (vedi `docs/implementation-progress.md`).

## 8. Rischi tecnici

- **Doppio conteggio provvigioni nelle liquidazioni**: mitigato dal vincolo di
  unicità su `settlement_items.commission_movement_id` (§5).
- **Rettifiche che sovrascrivono importi**: per costruzione impossibile — il
  ledger è append-only, ogni rettifica è un nuovo movimento collegato
  all'originale (pattern già usato per gli storni, vedi
  `docs/commission-engine-specification.md`).
- **Vista rete enterprise su reti grandi**: la chiusura transitiva
  (`network_closure`) regge query indicizzate, ma una vista "tutta la rete in
  un colpo solo" per organizzazioni con migliaia di agenti va paginata lato
  server fin da subito, non ottimizzata dopo.
- **Cicli nello spostamento rete**: già prevenuto (`CycleError` in
  `network/service.py`, testato in `tests/test_network_isolation.py`) — da
  riusare, non reinventare, nella UI di spostamento.

## 9. Dipendenze

Nessuna nuova tecnologia infrastrutturale. Nuova libreria frontend per i
grafici (Fase 2): la spec del progetto (`docs/architecture.md`) indica
Recharts o Apache ECharts. Si è usata **Recharts** (più leggera, integrazione
React idiomatica, sufficiente per andamenti mensili e KPI) — installata e in
uso da Fase 2 (Sessione 6). MinIO è già nello stack Docker per la Fase relativa
ai documenti, ma il codice applicativo che lo usa non esiste ancora.

## 10. Domande ancora aperte

1. **Wallet vs ledger** (vedi §1.5): confermato — si prosegue con il ledger
   append-only esistente, nessun saldo mutabile. Se questa non è
   l'interpretazione voluta, va detto esplicitamente prima della Fase 7.
2. **Registrazione pubblica vincolata a referral**: la persistenza
   dell'attribuzione (cookie referral, finestra temporale) esiste già; manca
   il flusso di **creazione account cliente self-service** (oggi i clienti
   sono creati solo da back-office/admin). Serve definire: verifica email,
   password policy, cosa succede se il cookie referral è scaduto (rifiuto
   della registrazione o registrazione senza attribuzione?).
3. **Pagamenti reali**: questa fase implementa solo `MockPaymentProvider` —
   l'integrazione con un vero PSP (Stripe/Nexi) resta esplicitamente fuori
   scope finché non richiesta, come da `docs/architecture.md`.
4. **Import massivo**: la richiesta lo cita come "struttura predisposta" — in
   questo piano è un placeholder architetturale (endpoint che valida e
   restituisce anteprima/errori), non un'implementazione completa, salvo
   diversa indicazione.

Tutti i placeholder numerici del piano provvigionale restano quelli già
documentati in `docs/open-questions.md` (non duplicati qui).
