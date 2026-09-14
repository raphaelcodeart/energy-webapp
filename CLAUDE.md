# Istruzioni operative per Claude Code

Questo file viene letto all'inizio di ogni sessione. Contiene le cose che
**non si deducono leggendo il codice** e che, se ignorate, fanno danni:
convenzioni, trappole già pagate una volta, e i comandi esatti che funzionano
su questo server.

Per la ricostruzione completa da zero (server nuovo, o progetto rifatto per
un'altra azienda) la guida è `docs/server-migration-guide.md` — §12 è un
runbook pensato per essere eseguito passo per passo, verifiche comprese.

---

## 1. Le tre cose da sapere prima di toccare qualsiasi cosa

**Questo server è in produzione.** `app.lialenergy.it` è live, con clienti
veri, contratti veri e pagamenti veri. Non esiste un ambiente di staging.

**"dev" qui significa produzione.** Lo stack gira con
`docker-compose.dev.yml` e `ENVIRONMENT=development` nel `.env`, ma è
l'installazione reale. `docker-compose.production.yml` esiste nel repository
ma **non è quello in esecuzione**. Ogni comando in questo file usa
`-f docker-compose.dev.yml` per questo motivo, non per distrazione.

**Le immagini sono cotte.** I container non montano il sorgente. Modificare
un file e fare `restart` non cambia niente: il container riparte con il
codice di prima. Serve sempre:

```bash
docker compose -f docker-compose.dev.yml build <servizio>
docker compose -f docker-compose.dev.yml up -d <servizio>
```

`celery-worker` e `celery-beat` in più vogliono `--force-recreate`, altrimenti
restano attaccati alla vecchia immagine.

---

## 2. Test

Il database di test viene **cancellato e ricreato** all'inizio di ogni
sessione di pytest (`tests/conftest.py`, `drop_all` + `create_all`). Puntarlo
al database reale distrugge i dati di produzione. Il nome giusto è
`lial_energy_test`, **mai** `lial_energy`: controllalo nella stringa di
connessione ogni volta, prima di premere invio.

Gli hostname `postgres` e `minio` del `.env` esistono solo dentro la rete
Docker: dall'host non risolvono. In più sull'host gira un *altro* Postgres
su `127.0.0.1:5432`, con credenziali diverse — puntarci dà
`password authentication failed for user "lial"`, che sembra una password
sbagliata ma è il server sbagliato. Usa gli IP dei container:

```bash
cd /opt/lialenergy/apps/api
POSTGRES_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
  $(docker compose -f ../../docker-compose.dev.yml ps -q postgres))
MINIO_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
  $(docker compose -f ../../docker-compose.dev.yml ps -q minio))
set -a && . <(grep -E "^(S3_|MINIO_|POSTGRES_PASSWORD)" /opt/lialenergy/.env) && set +a
export S3_ENDPOINT_URL="http://$MINIO_IP:9000"
TEST_DATABASE_URL="postgresql+psycopg://lial:${POSTGRES_PASSWORD}@${POSTGRES_IP}:5432/lial_energy_test" \
  .venv/bin/python -m pytest -q
```

Le variabili S3 servono davvero: i test dei documenti caricano file veri su
MinIO. Senza, falliscono con `EndpointConnectionError`.

La suite completa impiega ~2,5 minuti: lanciala in background e nel
frattempo fai altro. Il driver è `psycopg`, non `asyncpg`. Il venv
`apps/api/.venv` ogni tanto è indietro rispetto a `pyproject.toml` (è già
successo con `stripe`): se la *collection* fallisce su un
`ModuleNotFoundError`, installa il pacchetto e vai avanti.

---

## 3. Verifiche prima di un deploy

```bash
cd apps/api      && .venv/bin/python -c "import app.main"   # vedi sotto
cd apps/dashboard && pnpm typecheck && pnpm build
```

`import app.main` non è pedanteria: un `NameError` in un router non lo prende
nessun test (i test esercitano i servizi, non le rotte) e si manifesta come
un 500 al primo utente che apre quella schermata. È già successo.

`pnpm lint` **non passa** su questo repository: ci sono 15 errori
preesistenti, quasi tutti `react-hooks/set-state-in-effect`. Il criterio non
è "lint verde" ma "lint non peggiora": conta gli errori prima e dopo, o
verifica che i tuoi file non compaiano nell'elenco. Stessa cosa per `mypy` e
per `ruff` su `alembic/` e `tests/`.

`react-hooks/set-state-in-effect` è comunque un **errore**, non un warning:
nel codice nuovo i valori si derivano durante il render, non si sincronizzano
con un `useEffect`.

---

## 4. Migrazioni e schema

Una modifica ai modelli richiede tre cose, non una:

1. un file nuovo in `apps/api/alembic/versions/` (numerazione progressiva
   `00NN_nome.py`, `down_revision` = la revision precedente);
2. `./scripts/backup.sh` **prima** di applicarla in produzione;
3. `./scripts/dump-schema.sh` dopo, e il diff di `docs/database-schema.sql`
   committato insieme al resto.

Il punto 3 sembra burocrazia e non lo è: quel file è l'artefatto con cui si
ricostruisce il database su un altro server, ed è già andato fuori
sincrono due volte (mancavano interi domini). Il diff deve contenere
**solo** ciò che la migrazione dichiara di fare: se contiene altro, qualcuno
ha modificato il database a mano.

Il container `api` esegue `alembic upgrade head` da solo all'avvio. Non serve
lanciarlo a parte dopo un `up -d`.

Lo schema da solo non basta a far partire l'applicazione: permessi, ruoli,
gradi e piano provvigioni sono **dati**, non struttura. Vedi
`docs/server-migration-guide.md` §6.1 e `python -m app.seed.bootstrap`.

---

## 5. Regole di dominio che non si negoziano

Sono scritte per esteso in `docs/business-rules.md`; qui l'essenziale.

- **Ogni calcolo economico è server-side.** Il browser sceglie una chiave
  (`FULL`, `MONTHLY_12`, un id prodotto), mai un importo. Un prezzo che
  arriva dal frontend non si usa nemmeno per visualizzarlo.
- **L'idempotenza si ottiene con un vincolo UNIQUE su una chiave
  deterministica**, mai con un flag applicativo e mai con un UUID generato
  al volo dal client. Bonus, cashback, provvigioni e pagamenti non devono
  poter essere accreditati due volte: è già successo, e la causa era un
  `retry` dopo un errore di invio email.
- **I webhook Stripe si verificano con la firma**, e l'`event.id` si registra
  *prima* di eseguire qualsiasi handler.
- **Gli snapshot sono congelati**: la rete al momento dell'attivazione, il
  prezzo al momento della creazione del contratto. Non si ricalcolano mai a
  posteriori.
- **Un'email che non parte non deve mai far fallire l'operazione che la
  precede** — c'è `send_html_email_best_effort()` per questo. Con due
  eccezioni volute: i link di reset password e i codici OTP, dove se l'invio
  fallisce l'utente *deve* saperlo.

---

## 6. Interfaccia

- Tutto ciò che vede un utente è **in italiano**, incluso ogni messaggio di
  errore. Chi usa questa applicazione non è tecnico: "Si è verificato un
  errore" è un fallimento, non un messaggio.
- Il `detail` di un errore FastAPI 422 è un **array**, non una stringa.
  Passarlo a React produce `[object Object]` sullo schermo. La traduzione sta
  in `apps/dashboard/lib/api-error.ts`: usala, non reinventarla.
- Dark e light: ogni classe di colore ha la sua variante `light:`. Un
  componente nuovo va guardato in entrambi i temi.
- Tailwind v4, niente file di configurazione del tema. Il colore del brand
  (`orange-*`/`amber-*`) è scritto a mano in ogni componente.

---

## 7. Documentazione da aggiornare

Non è opzionale: questo repository si regge sulla documentazione, ed è il
motivo per cui è ricostruibile.

| Quando | Cosa |
|---|---|
| sempre, a fine lavoro | `docs/implementation-progress.md` — una voce per sessione, in italiano, che dice cosa è cambiato **e perché** |
| nuova regola di business | `docs/business-rules.md` |
| nuova tabella o colonna | `docs/database-model.md` **e** `docs/database-schema.sql` (rigenerato) |
| cambia qualcosa per l'utente | `docs/user-guide.md` |
| cambia l'installazione | `docs/server-migration-guide.md` |
| decisione lasciata in sospeso | `docs/open-questions.md` |

---

## 8. Git

Branch `main`, si committa e si pusha solo quando l'utente lo chiede. Ogni
commit termina con:

```
Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
```

Il corpo del messaggio si scrive in italiano e spiega **perché**, non cosa:
il cosa si legge dal diff.

---

## 9. Come è fatto

FastAPI + SQLAlchemy async + Alembic + Pydantic v2 su PostgreSQL 16, Celery
con Redis, MinIO per i file, Next.js 16 (App Router) davanti, tutto dietro
nginx, tutto in Docker Compose.

```
apps/api/app/domains/<dominio>/   models.py schemas.py service.py router.py
apps/api/app/core/                config, db, security, storage, email
apps/api/alembic/versions/        migrazioni
apps/api/tests/                   pytest
apps/dashboard/app/               rotte Next.js (+ BFF in app/api/proxy)
apps/dashboard/components/        UI
infrastructure/nginx/             nginx.conf
scripts/                          backup, restore, deploy, migrate, dump-schema
```

Il frontend non parla mai direttamente con l'API: passa dal proxy BFF in
`apps/dashboard/app/api/proxy/[...path]`, che è dove vive il cookie di
sessione.

La regola di scrittura del codice è una sola: il codice nuovo deve
assomigliare a quello che ha intorno — stessa densità di commenti, stessi
nomi, stesse abitudini. E un commento spiega *perché* una cosa è fatta così,
non *cosa* fa la riga sotto.
