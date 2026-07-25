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

### 4.6 Dominio e HTTPS

**Obbligatorio, non opzionale**: il cookie di sessione (`apps/dashboard/lib/session.ts`)
è marcato `Secure`, quindi i browser lo scartano silenziosamente su una connessione
HTTP — il login sembra "non fare nulla" (nessun errore, ma nessuna sessione viene
salvata). Il sito **deve** girare su HTTPS perché il login funzioni davvero in un
browser reale (curl/Postman non applicano questa regola e possono ingannevolmente
sembrare funzionare anche su HTTP).

Se non hai ancora un dominio vero, un hostname temporaneo funziona benissimo per
Let's Encrypt: Hetzner fornisce automaticamente un rDNS del tipo
`static.<IP-con-i-punti-invertiti>.clients.your-server.de` per ogni IP — verificalo con:
```bash
getent hosts static.X.X.X.X.clients.your-server.de   # sostituisci con il tuo IP
```
Se risolve al tuo server, puoi usarlo subito per ottenere un certificato reale.

**Procedura completa** (questi sono gli stessi comandi eseguiti su questo
server — non teoria, comandi verificati):

```bash
DOMAIN="il-tuo-dominio-o-hostname-temporaneo"

# 1. Installa certbot sull'host (non serve dentro Docker)
apt-get install -y certbot

# 2. Prepara le cartelle (root del progetto)
mkdir -p certbot/www certbot/conf

# 3. Certificato "dummy" temporaneo, SOLO per permettere a nginx di avviarsi la
#    prima volta con un blocco server 443 già configurato (altrimenti nginx non
#    parte proprio, perché il file del certificato reale non esiste ancora):
mkdir -p "certbot/conf/live/$DOMAIN"
openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
  -keyout "certbot/conf/live/$DOMAIN/privkey.pem" \
  -out "certbot/conf/live/$DOMAIN/fullchain.pem" \
  -subj "/CN=$DOMAIN"

# 4. Aggiorna infrastructure/nginx/nginx.conf: imposta ssl_certificate e
#    ssl_certificate_key sul path /etc/letsencrypt/live/$DOMAIN/... (vedi il
#    file attuale come esempio -- il dominio è scritto esplicitamente, non è
#    templatizzato). Aggiorna anche docker-compose.dev.yml: il servizio nginx
#    deve montare ./certbot/conf:/etc/letsencrypt:ro e
#    ./certbot/www:/var/www/certbot:ro, e pubblicare anche la porta 443:443
#    (non solo 80:80). Guarda il diff già applicato su questo server per
#    l'esempio completo.

# 5. Avvia/ricrea nginx con il certificato dummy (deve partire senza errori)
docker compose -f docker-compose.dev.yml up -d nginx --force-recreate
docker exec lial-energy-dev-nginx-1 nginx -t   # "syntax ok" atteso

# 6. IMPORTANTE: rimuovi la cartella live/$DOMAIN dummy PRIMA di chiedere il
#    certificato vero -- se certbot la trova già lì (anche se creata a mano)
#    si rifiuta con "live directory exists for ...". Rimuovi tutto lo stato
#    dummy e riparti pulito:
rm -rf certbot/conf   # sì, tutto -- ricreato al passo successivo da certbot stesso
mkdir -p certbot/conf

# 7. Richiedi il certificato vero via webroot (nginx deve già rispondere sulla
#    porta 80 con la challenge ACME -- lo fa di default col nginx.conf di questo
#    progetto, verifica con un test manuale prima se hai dubbi)
certbot certonly --webroot -w certbot/www \
  -d "$DOMAIN" \
  --config-dir certbot/conf --work-dir certbot/work --logs-dir certbot/logs \
  --register-unsafely-without-email --agree-tos --non-interactive

# 8. IMPORTANTE: se il container nginx è stato avviato PRIMA che questa
#    cartella esistesse/fosse ricreata, il suo bind mount punta ancora al
#    vecchio inode (cancellato) e vedrà una cartella vuota anche se sull'host
#    i file ci sono -- serve ricreare il container, un semplice reload non basta:
docker compose -f docker-compose.dev.yml up -d nginx --force-recreate
docker exec lial-energy-dev-nginx-1 nginx -t   # deve dare "syntax ok" e trovare i file veri

# 9. Verifica
curl -I https://$DOMAIN/login   # atteso: HTTP/2 200, con un certificato reale
```

Poi:
- Aggiorna `NEXT_PUBLIC_APP_URL=https://$DOMAIN` in `.env` e riavvia il dashboard:
  `docker compose -f docker-compose.dev.yml up -d dashboard --force-recreate`
- Aggiungi `scripts/renew-cert.sh` al crontab (i certificati Let's Encrypt
  scadono ogni 90 giorni; il timer systemd installato di default da certbot **non**
  rinnova questo certificato perché usa un percorso di configurazione non
  standard — vedi il commento in cima allo script):
  ```bash
  crontab -e
  # aggiungi:
  0 3 * * * /opt/lialenergy/scripts/renew-cert.sh >> /opt/lialenergy/certbot/renew.log 2>&1
  ```

**Non committare mai `certbot/`** (contiene chiavi private) — è già in
`.gitignore`. Se cambi dominio, ripeti l'intera procedura per il nuovo nome.

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
8. **Login "non fa nulla" su un sito servito in HTTP puro**: il cookie di
   sessione è marcato `Secure`, e i browser reali (non `curl`) lo scartano
   silenziosamente se la pagina non è servita su HTTPS. Non è un bug da
   correggere abbassando il livello di sicurezza (rimuovere `Secure` esporrebbe
   i token in chiaro) — la correzione corretta è attivare HTTPS, vedi sezione
   4.6. Sintomo tipico: il form di login sembra caricare per un paio di secondi
   e poi resta sulla pagina di login, senza errori visibili nella UI (l'errore
   compare solo nella console del browser: *"Cookie ... rifiutato in quanto un
   cookie non-HTTPS non può essere impostato come 'secure'"*).
9. **Dopo aver rigenerato `certbot/conf` (`rm -rf` + ricreato), nginx vede una
   cartella vuota anche se sull'host i file ci sono**: un bind mount Docker
   stabilito PRIMA che la cartella host venga cancellata e ricreata resta
   agganciato al vecchio inode (ormai orfano), non alla nuova directory. Un
   `nginx -s reload` non basta — serve ricreare il container
   (`docker compose up -d nginx --force-recreate`) perché il bind mount venga
   ristabilito contro il percorso host attuale.

Se un problema NON è in questa lista, è nuovo — documentalo qui dopo averlo
risolto, per lo stesso motivo per cui questi nove lo sono.

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
