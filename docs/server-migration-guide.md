# Guida alla Migrazione del Server / Ricostruzione da Zero

Questo documento serve a un solo scopo: permettere a chiunque (umano o AI) di
ricreare **esattamente** questa piattaforma su un nuovo server, partendo da zero,
senza dover indovinare nulla. Se stai leggendo questo perché il server attuale è
stato perso, compromesso, o semplicemente vuoi migrare altrove — segui questa
guida nell'ordine in cui è scritta.

Non duplica `README.md` o `docs/architecture.md` — li presuppone. Qui ci sono solo
le informazioni operative specifiche per un trasloco/ricostruzione: cosa
installare, in che ordine, quali bug reali sono già stati trovati e corretti (per
non doverli riscoprire), e come verificare che tutto funzioni.

## 1. Cos'è questo progetto, in breve

Gestionale Lial Energy: FastAPI (backend) + Next.js 16 (frontend/BFF) + PostgreSQL
16 + Redis + Celery + MinIO, orchestrato con Docker Compose, dietro nginx. Vedi
`docs/architecture.md` per il quadro completo, `docs/implementation-progress.md`
per cosa è realmente implementato e cosa no.

Repository: `git@github.com:raphaelcodeart/energy-webapp.git`, branch `main`.

## 2. Server di riferimento (quello su cui questo progetto gira oggi)

Utile per dimensionare un eventuale nuovo server in modo equivalente:

| | |
|---|---|
| Provider | Hetzner Cloud (datacenter nbg1 — Norimberga) |
| Hostname | `lialenergy-4gb-nbg1-2` |
| OS | Ubuntu 26.04 LTS |
| CPU | 2 vCPU |
| RAM | 3.7 GiB |
| Disco | 38 GB (di cui ~9 GB usati con lo stack attivo + dati demo) |
| IP pubblico | vedi il pannello Hetzner del progetto — cambia se si ricrea il server |

Un nuovo server con specifiche pari o superiori (2 vCPU / 4 GB RAM / 40 GB disco
minimo) è sufficiente per l'intero stack in questa fase (dati demo, traffico
basso). Se il volume di contratti/agenti cresce di ordini di grandezza, rivedere
il dimensionamento di Postgres in particolare.

## 3. Prerequisiti sul nuovo server

Sistema operativo Ubuntu 24.04+ o equivalente (Debian-based). Da installare:

```bash
apt-get update
apt-get install -y docker.io docker-compose-v2 git openssl
systemctl enable --now docker
```

Verifica:
```bash
docker --version          # atteso: Docker version 27+ (qualsiasi versione recente va bene)
docker compose version     # atteso: Docker Compose version 2.x
```

Non serve installare Python, Node, PostgreSQL, Redis o MinIO direttamente
sull'host: girano tutti dentro i container Docker. (Se invece vuoi sviluppare o
fare debug SENZA Docker, vedi `docs/deployment.md` e il `README.md` per
l'installazione locale di `postgresql`, `nodejs`/`npm`/`pnpm` — utile solo per
verifica/debug, non necessaria per l'esecuzione normale.)

## 4. Passo per passo: ricostruzione completa

### 4.1 Clona il repository

```bash
cd /opt   # o dove preferisci
git clone git@github.com:raphaelcodeart/energy-webapp.git lialenergy
cd lialenergy
```

Serve una chiave SSH autorizzata sul repo GitHub (deploy key o chiave
dell'account). Se non ce l'hai già configurata sul nuovo server:

```bash
ssh-keygen -t ed25519 -C "nuovo-server-deploy" -f ~/.ssh/id_ed25519_github -N ""
cat ~/.ssh/id_ed25519_github.pub
# aggiungi questa chiave pubblica su GitHub:
# github.com/raphaelcodeart/energy-webapp -> Settings -> Deploy keys -> Add deploy key
# (spunta "Allow write access" solo se questo server deve anche fare push)
cat >> ~/.ssh/config <<'EOF'

Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_github
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
ssh -T git@github.com   # deve rispondere "successfully authenticated"
```

### 4.2 Crea il file `.env`

**Non è nel repository** (per design — vedi `.gitignore`). Deve essere ricreato
da zero su ogni server. Usa `.env.example` come riferimento della lista completa
delle variabili, poi genera segreti reali:

```bash
cp .env.example .env

# genera segreti forti al posto dei placeholder:
python3 -c "
import secrets
print('POSTGRES_PASSWORD=' + secrets.token_hex(24))
print('JWT_SECRET_KEY=' + secrets.token_hex(32))
print('MINIO_ROOT_USER=lial_minio_admin')
print('MINIO_ROOT_PASSWORD=' + secrets.token_hex(24))
print('S3_ACCESS_KEY=lial_minio_admin')
print('S3_SECRET_KEY=' + secrets.token_hex(24))
"
# incolla questi valori dentro .env al posto dei placeholder corrispondenti
```

Variabili che vanno adattate al nuovo server (non generate a caso):
- `NEXT_PUBLIC_APP_URL` — l'URL pubblico con cui si accederà (`http://IP-NUOVO-SERVER`
  o `https://tuodominio.it` se hai già DNS+TLS pronti)
- `API_INTERNAL_URL` — lascialo `http://api:8000` (è interno alla rete Docker, non
  cambia mai tra server)

**Mai committare `.env` nel repository.** È già in `.gitignore`; se `git status`
lo mostra come modificabile, fermati e controlla prima di fare qualsiasi `git add`.

### 4.3 Costruisci e avvia lo stack

```bash
docker compose -f docker-compose.dev.yml build
docker compose -f docker-compose.dev.yml up -d
```

Le migrazioni Alembic girano **automaticamente** all'avvio del container `api`
(vedi il `command` del servizio `api` in `docker-compose.dev.yml`) — non serve
lanciarle a mano la prima volta.

Verifica che tutti gli 8 container siano `healthy` (aspetta 30-60 secondi):

```bash
docker compose -f docker-compose.dev.yml ps
```

Se qualcosa non diventa `healthy`, guarda la sezione 6 ("Problemi noti già
risolti") prima di improvvisare un fix — è quasi certamente uno dei 6 bug già
scoperti e corretti in questo stesso processo la prima volta.

### 4.4 Popola i dati

**Scenario A — nuovo server, dati demo (nessuna migrazione dati reali):**
```bash
docker compose -f docker-compose.dev.yml exec api python -m app.seed
```
Salva l'`Organization ID` stampato in output — serve per fare login.

**Scenario B — stai migrando dati reali dal vecchio server:** vedi sezione 5
("Migrare i dati da un server esistente") invece di eseguire il seed.

### 4.5 Verifica

```bash
scripts/health-check.sh dev
curl -s http://localhost/login   # deve rispondere 200
```

Poi prova il login vero (vedi `docs/user-guide.md` per la procedura completa
lato utente) con le credenziali del seed (`DemoPass123!`) o le credenziali reali
migrate.

### 4.6 Dominio e HTTPS (se applicabile)

Se il nuovo server deve rispondere su un dominio invece che sul solo IP:

1. Aggiungi un record DNS **A** che punti il dominio all'IP pubblico del nuovo server.
2. Aggiorna `server_name` in `infrastructure/nginx/nginx.conf` (attualmente `_`,
   cioè "accetta qualsiasi host") con il dominio reale, se vuoi essere restrittivo.
3. Aggiungi certbot (Let's Encrypt) per il TLS — **non ancora presente in questo
   progetto** (vedi `docs/implementation-progress.md`, è lavoro di Fase H). Finché
   non è wired, il sito resta solo HTTP.
4. Aggiorna `NEXT_PUBLIC_APP_URL` in `.env` con il nuovo dominio e riavvia
   `docker compose -f docker-compose.dev.yml up -d dashboard`.

## 5. Migrare i dati da un server esistente (non solo il codice)

Se il vecchio server è ancora raggiungibile, **non ripartire dal seed** — porta i
dati veri:

```bash
# Sul VECCHIO server:
cd /opt/lialenergy
scripts/backup.sh dev
# produce ./backups/lial_energy_dev_TIMESTAMP.sql.gz

# copia il file sul nuovo server, es:
scp ./backups/lial_energy_dev_*.sql.gz nuovo-server:/opt/lialenergy/backups/

# Sul NUOVO server, DOPO aver fatto girare `docker compose up -d` (serve postgres attivo):
cd /opt/lialenergy
gunzip -c backups/lial_energy_dev_TIMESTAMP.sql.gz | \
  docker compose -f docker-compose.dev.yml exec -T postgres psql -U lial lial_energy
```

Questo restituisce SOLO i dati Postgres (utenti, rete, contratti, provvigioni,
ecc.). Se ci sono documenti caricati su MinIO (attualmente non ancora
implementato in questa versione — vedi `docs/implementation-progress.md`, dominio
`documents` non ancora costruito), andrebbero sincronizzati separatamente con
`mc mirror` o equivalente quando quella funzionalità esisterà.

**Non usare `scripts/restore.sh`** per questo scenario — quello script è pensato
per ripristinare un backup nello **stesso** ambiente dopo un disastro (crea un
database `_restoring` separato per sicurezza). Per una migrazione a database
vuoto su un server nuovo, il comando diretto sopra è più semplice e corretto.

## 6. Struttura completa del database

La fonte di verità assoluta è **`docs/database-schema.sql`** in questa stessa
cartella — è un dump reale (`pg_dump --schema-only`) del database in esecuzione,
non una ricostruzione a memoria. Contiene tutte le 43 tabelle con tipi esatti,
vincoli, indici, foreign key.

La spiegazione **concettuale** (perché ogni tabella esiste, come si collegano,
diagramma ER) è in `docs/database-model.md` — leggila insieme allo schema SQL,
non al posto suo.

Il modo **corretto e canonico** per ricreare lo schema da zero non è applicare
`database-schema.sql` a mano: è lasciare che Alembic lo faccia, che è esattamente
quello che succede automaticamente al primo avvio del container `api` (vedi
4.3). Il file `.sql` serve come:
- riferimento per capire esattamente cosa esiste, senza dover leggere tutti i
  file `app/domains/*/models.py` uno per uno
- verifica: se un giorno lo schema reale e questo file divergono, è un segnale
  che qualcuno ha modificato il database a mano bypassando Alembic — da
  correggere subito
- materiale di partenza se, in un contesto di emergenza estremo, Alembic stesso
  non fosse disponibile e servisse ricreare lo schema con `psql -f
  docs/database-schema.sql` direttamente (funziona, essendo SQL puro, ma poi non
  far girare `alembic upgrade head` sopra uno schema già creato così, o l'idempotenza
  delle migration passate va verificata a mano)

Elenco delle 43 tabelle per dominio (dettagli in `docs/database-model.md`):

```
Identità/tenancy:  organizations, users, roles, permissions, role_permissions,
                    user_roles, sessions, audit_log
Rete commerciale:  agent_profiles, network_nodes, network_edges,
                    network_closure, network_assignment_history,
                    network_snapshots, network_snapshot_nodes
Referral:          promoter_codes, referral_events, referral_sessions,
                    customer_attributions, attribution_corrections
Catalogo/clienti:  products, product_versions, customers, customer_profiles,
                    companies, addresses, supply_points
Contratti:         contracts, contract_status_history, contract_events,
                    contract_attributions
Provvigioni:       ranks, agent_rank_history, commission_plan_versions,
                    commission_rule_versions, commission_calculations,
                    commission_calculation_steps, commission_movements,
                    commission_adjustments, commission_offsets,
                    commission_reversals
Outbox:            domain_outbox
Alembic:           alembic_version (gestita automaticamente, non toccare a mano)
```

## 7. Mappa del codice (per orientarsi velocemente)

```
apps/api/app/
  core/            config, connessione DB, sicurezza (hashing, JWT), dipendenze FastAPI
  domains/<nome>/  un dominio di business per cartella: models.py, schemas.py,
                   service.py, router.py (+ calculators/policies per commissions)
  celery_app.py    app Celery -- STESSO codice dell'api, non duplicato (vedi
                   apps/worker/README.md e docs/adr/0001-modular-monolith.md)
  seed/            dati demo (python -m app.seed)
  main.py          entry point FastAPI, monta tutti i router

apps/dashboard/app/
  login/           pagina di login
  customer|promoter|admin/   le tre dashboard per ruolo
  api/auth/        route handler BFF (login/logout) -- QUESTI, non FastAPI
                   direttamente, sono ciò che il browser chiama su /api/*
  api/proxy/       proxy autenticato per chiamate client-side (TanStack Query)
  proxy.ts         (era middleware.ts in Next <16) protegge le route autenticate

infrastructure/nginx/nginx.conf   reverse proxy: /backend/ -> FastAPI diretto,
                                  tutto il resto -> dashboard (BFF)
docker-compose.dev.yml            topologia completa (8 servizi)
scripts/                          deploy, backup, restore, health-check, migrate, rollback
```

## 8. Problemi noti già risolti (leggi PRIMA di fare debug da zero)

Questi 6 bug sono stati scoperti e corretti eseguendo per davvero
`docker compose up --build` su questo stesso server. Se ricreando lo stack su un
nuovo server incontri sintomi simili, **il fix è già nel codice** — molto
probabilmente il problema è un altro. Documentati per intero in
`docs/implementation-progress.md`; riassunto:

1. **Build del dashboard fallisce su `groupadd`**: `node:22-slim` ha già un
   utente `node` a uid/gid 1000 — il Dockerfile ora lo riusa invece di crearne uno.
2. **`pnpm install` fallisce con `ERR_PNPM_IGNORED_BUILDS`**: corepack scaricava
   pnpm `latest` (11.x), più restrittivo sugli script nativi. Il `packageManager`
   è pinnato in `package.json` alla versione con cui è stato generato il lockfile.
3. **Build fallisce su `apps/dashboard/public` non trovato**: creata la cartella
   (vuota, con `.gitkeep`).
4. **`celery-beat` va in crash loop**: cercava di scrivere il file di schedule in
   `/app` (di proprietà di root). Ora scrive in `/tmp`.
5. **`celery-worker`/`celery-beat` risultano "unhealthy"**: ereditavano
   l'healthcheck HTTP dell'immagine api, inutile per un processo senza server
   HTTP. Sostituito con `celery inspect ping` (worker) e disabilitato (beat).
6. **Il dashboard risulta "unhealthy" anche se funziona**: il server standalone
   di Next si legava all'IP di interfaccia del container invece che al wildcard.
   Risolto con `HOSTNAME=0.0.0.0`.
7. **(Il più insidioso) Login "funziona" ma nessuna pagina protetta si apre**:
   nginx instradava `/api/` direttamente a FastAPI, intercettando anche le route
   BFF del dashboard (`/api/auth/login`, `/api/proxy/*`) che vivono sulla stessa
   porta 80. Risolto spostando l'accesso diretto al backend su `/backend/`,
   lasciando `/api/*` esclusivamente al dashboard.

Se un problema NON è in questa lista, è nuovo — documentalo qui dopo averlo
risolto, per lo stesso motivo per cui questi sette lo sono.

## 9. Cosa NON aspettarsi che funzioni già

Vedi `docs/implementation-progress.md`, sezione "Explicitly NOT in this session's
scope" per l'elenco completo. In breve: pagamenti reali, upload documenti,
notifiche, motore AI/pgvector, CI/CD, backup automatizzati con retention, MFA,
HTTPS. Non sono bug — sono semplicemente fasi successive non ancora costruite.

## 10. Assunzioni di business ancora provvisorie

Le cifre del piano carriera/provvigionale (S1-S3, TL1-4, MD1-5, regola del 33%,
ecc.) sono **placeholder documentati**, non le regole reali di Lial Energy — il
documento `Allegato_A_Piano_Carriera_Regolamento_Provvigionale.pdf` non era
presente nel repository quando questo sistema è stato costruito. Vedi
`docs/open-questions.md` per l'elenco esatto e dove intervenire quando il
documento reale sarà disponibile.
