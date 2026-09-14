"""Invio del dossier di un contratto su Google Drive.

Parla direttamente con l'API REST di Drive via `httpx`, che è già una
dipendenza, invece di tirarsi dentro `google-api-python-client` e il suo
albero: qui servono tre chiamate HTTP (scambio del codice, refresh del
token, upload multipart) e una ricerca. Una libreria che ne astrae
quattromila sarebbe peso in più senza niente in cambio.

**Come si collega.** L'amministratore autorizza una volta il proprio account
Google; da lì in poi il pulsante funziona per tutti gli amministratori
dell'organizzazione, perché i file finiscono sul Drive di chi ha
autorizzato. Il refresh token vive in `Organization.settings` accanto alle
chiavi Stripe, con lo stesso trattamento: non torna mai indietro da nessuna
risposta.

**Lo scope è `drive.file`**, non `drive`. Significa che questa applicazione
vede e tocca soltanto ciò che ha creato lei: non può leggere, e nemmeno
elencare, il resto del Drive di chi ha autorizzato. È anche la ragione per
cui la ricerca "esiste già una cartella con questo nome?" funziona senza
poter diventare una finestra sul resto dell'account.
"""

import secrets
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domains.contracts.dossier import Dossier
from app.domains.organizations.models import Organization

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v3/userinfo"
DRIVE_FILES_ENDPOINT = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD_ENDPOINT = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"

#: Solo i file creati da questa applicazione. Vedi il docstring del modulo.
SCOPES = ("https://www.googleapis.com/auth/drive.file", "openid", "email")

#: Il percorso della pagina della dashboard che riceve il `code` di Google.
#: È anche l'URI esatto da registrare fra i "Authorized redirect URIs" del
#: client OAuth sulla console Google Cloud -- lo costruiamo qui e lo
#: mostriamo in chiaro nelle impostazioni, così non c'è da indovinarlo.
CALLBACK_PATH = "/admin/google-drive-callback"

SETTING_CLIENT_ID = "google_client_id"
SETTING_CLIENT_SECRET = "google_client_secret"
SETTING_REFRESH_TOKEN = "google_drive_refresh_token"
SETTING_ACCOUNT_EMAIL = "google_drive_account_email"
SETTING_CONNECTED_AT = "google_drive_connected_at"
SETTING_PARENT_FOLDER_ID = "google_drive_parent_folder_id"
SETTING_OAUTH_STATE = "google_drive_oauth_state"

#: Oltre questo, la richiesta è comunque persa: Drive non è lento, e un
#: amministratore che aspetta un minuto pensa che si sia bloccato.
REQUEST_TIMEOUT_SECONDS = 60.0


class GoogleDriveError(Exception):
    """Errore che ha senso mostrare a un amministratore, in italiano."""


@dataclass(frozen=True)
class DriveStatus:
    #: Client ID e secret inseriti: senza, non c'è nemmeno un pulsante da
    #: premere. È lo stato in cui nasce ogni installazione.
    configured: bool
    #: Qualcuno ha autorizzato il proprio account Google.
    connected: bool
    account_email: str | None
    connected_at: str | None
    parent_folder_id: str | None
    #: Da registrare sulla console Google Cloud. Mostrato all'amministratore.
    redirect_uri: str
    #: Pubblico per definizione (finisce nell'URL di consenso). Il secret no.
    client_id: str | None
    #: Del secret esce solo l'esistenza, mai il valore.
    client_secret_configured: bool


@dataclass(frozen=True)
class DriveUploadResult:
    folder_id: str
    folder_url: str
    folder_name: str
    uploaded: int
    #: File già presenti che sono stati sovrascritti invece di duplicati.
    replaced: int


def redirect_uri() -> str:
    return f"{get_settings().public_app_base_url.rstrip('/')}{CALLBACK_PATH}"


async def _org(db: AsyncSession, organization_id: uuid.UUID) -> Organization:
    org = await db.get(Organization, organization_id)
    if org is None:
        raise GoogleDriveError("Organizzazione non trovata.")
    return org


def _write_settings(org: Organization, values: dict[str, object]) -> None:
    """Un assegnamento nuovo, non una mutazione: SQLAlchemy non si accorge
    di un dict JSONB modificato sul posto (stesso motivo spiegato in
    organizations/service.py::update_settings)."""
    org.settings = {**(org.settings or {}), **values}


async def get_status(db: AsyncSession, *, organization_id: uuid.UUID) -> DriveStatus:
    org = await _org(db, organization_id)
    s = org.settings or {}
    return DriveStatus(
        configured=bool(s.get(SETTING_CLIENT_ID)) and bool(s.get(SETTING_CLIENT_SECRET)),
        connected=bool(s.get(SETTING_REFRESH_TOKEN)),
        account_email=s.get(SETTING_ACCOUNT_EMAIL),
        connected_at=s.get(SETTING_CONNECTED_AT),
        parent_folder_id=s.get(SETTING_PARENT_FOLDER_ID),
        redirect_uri=redirect_uri(),
        client_id=s.get(SETTING_CLIENT_ID),
        client_secret_configured=bool(s.get(SETTING_CLIENT_SECRET)),
    )


async def build_authorize_url(db: AsyncSession, *, organization_id: uuid.UUID) -> str:
    org = await _org(db, organization_id)
    s = org.settings or {}
    client_id = s.get(SETTING_CLIENT_ID)
    if not client_id or not s.get(SETTING_CLIENT_SECRET):
        raise GoogleDriveError(
            "Prima inserisci Client ID e Client Secret di Google nelle impostazioni."
        )

    # Lo state serve a una cosa sola: che il `code` che ci torna indietro sia
    # quello di un consenso che abbiamo chiesto noi, non uno che qualcuno ha
    # fatto arrivare a un amministratore per attaccare il suo Drive
    # all'organizzazione. Vive nelle settings perché è per-organizzazione e
    # dura il tempo di un consenso: una tabella sarebbe sproporzionata.
    state = secrets.token_urlsafe(24)
    _write_settings(org, {SETTING_OAUTH_STATE: state})
    await db.commit()

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        # offline + consent: senza questi due Google restituisce un refresh
        # token solo la primissima volta che quell'account autorizza quel
        # client, e un ricollegamento successivo tornerebbe senza -- cioè
        # con un collegamento che smette di funzionare dopo un'ora.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"


async def complete_connection(
    db: AsyncSession, *, organization_id: uuid.UUID, code: str, state: str
) -> DriveStatus:
    org = await _org(db, organization_id)
    s = org.settings or {}
    expected_state = s.get(SETTING_OAUTH_STATE)
    if not expected_state or not secrets.compare_digest(str(expected_state), state):
        raise GoogleDriveError(
            "Autorizzazione non valida o scaduta. Riprova a collegare Google Drive dall'inizio."
        )

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(TOKEN_ENDPOINT, data={
            "code": code,
            "client_id": s.get(SETTING_CLIENT_ID),
            "client_secret": s.get(SETTING_CLIENT_SECRET),
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
        })
        if response.status_code != 200:
            raise GoogleDriveError(_google_error_message(response, "collegare Google Drive"))
        tokens = response.json()

        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            raise GoogleDriveError(
                "Google non ha restituito un token permanente. Revoca l'accesso "
                "dell'applicazione dal tuo account Google e riprova."
            )

        account_email = None
        access_token = tokens.get("access_token")
        if access_token:
            info = await client.get(
                USERINFO_ENDPOINT, headers={"Authorization": f"Bearer {access_token}"}
            )
            if info.status_code == 200:
                account_email = info.json().get("email")

    _write_settings(org, {
        SETTING_REFRESH_TOKEN: refresh_token,
        SETTING_ACCOUNT_EMAIL: account_email,
        SETTING_CONNECTED_AT: datetime.now(UTC).isoformat(),
        SETTING_OAUTH_STATE: None,
    })
    await db.commit()
    return await get_status(db, organization_id=organization_id)


async def disconnect(db: AsyncSession, *, organization_id: uuid.UUID) -> DriveStatus:
    """Dimentica il token. Non tocca nulla di ciò che è già su Drive: quei
    file sono dell'account che li ospita, non nostri da cancellare."""
    org = await _org(db, organization_id)
    _write_settings(org, {
        SETTING_REFRESH_TOKEN: None,
        SETTING_ACCOUNT_EMAIL: None,
        SETTING_CONNECTED_AT: None,
        SETTING_OAUTH_STATE: None,
    })
    await db.commit()
    return await get_status(db, organization_id=organization_id)


def _google_error_message(response: httpx.Response, action: str) -> str:
    detail = ""
    try:
        payload = response.json()
        detail = payload.get("error_description") or payload.get("error", {}).get("message") or ""
    except Exception:  # noqa: BLE001 -- un corpo non-JSON non deve mascherare l'errore vero
        detail = response.text[:200]
    suffix = f" ({detail})" if detail else ""
    return f"Google ha rifiutato la richiesta di {action}{suffix}."


async def _access_token(client: httpx.AsyncClient, *, org: Organization) -> str:
    s = org.settings or {}
    if not s.get(SETTING_REFRESH_TOKEN):
        raise GoogleDriveError("Google Drive non è collegato. Collegalo dalle impostazioni.")
    response = await client.post(TOKEN_ENDPOINT, data={
        "client_id": s.get(SETTING_CLIENT_ID),
        "client_secret": s.get(SETTING_CLIENT_SECRET),
        "refresh_token": s.get(SETTING_REFRESH_TOKEN),
        "grant_type": "refresh_token",
    })
    if response.status_code != 200:
        raise GoogleDriveError(
            "Il collegamento con Google Drive non è più valido: ricollegalo dalle impostazioni. "
            + _google_error_message(response, "rinnovare l'accesso")
        )
    token = response.json().get("access_token")
    if not token:
        raise GoogleDriveError("Google non ha restituito un accesso valido. Ricollega Google Drive.")
    return token


def _escape_query_value(value: str) -> str:
    """La sintassi `q=` di Drive usa apici singoli come delimitatori: un
    apostrofo in un nome ("Bar D'Angelo") romperebbe la query."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


async def _find_child(
    client: httpx.AsyncClient, *, token: str, name: str, parent_id: str, mime_type: str | None
) -> str | None:
    query = (
        f"name = '{_escape_query_value(name)}' and '{_escape_query_value(parent_id)}' in parents "
        f"and trashed = false"
    )
    if mime_type is not None:
        query += f" and mimeType = '{mime_type}'"
    response = await client.get(
        DRIVE_FILES_ENDPOINT,
        headers={"Authorization": f"Bearer {token}"},
        params={"q": query, "fields": "files(id,name)", "pageSize": 1, "spaces": "drive"},
    )
    if response.status_code != 200:
        raise GoogleDriveError(_google_error_message(response, "cercare la cartella su Drive"))
    files = response.json().get("files") or []
    return files[0]["id"] if files else None


async def _create_folder(
    client: httpx.AsyncClient, *, token: str, name: str, parent_id: str
) -> str:
    response = await client.post(
        DRIVE_FILES_ENDPOINT,
        headers={"Authorization": f"Bearer {token}"},
        params={"fields": "id"},
        json={"name": name, "mimeType": FOLDER_MIME_TYPE, "parents": [parent_id]},
    )
    if response.status_code not in (200, 201):
        raise GoogleDriveError(_google_error_message(response, "creare la cartella su Drive"))
    return response.json()["id"]


async def _upload_file(
    client: httpx.AsyncClient,
    *,
    token: str,
    folder_id: str,
    name: str,
    content: bytes,
    content_type: str,
    existing_id: str | None,
) -> None:
    """Upload **resumable**, in due richieste: prima i metadati, che
    restituiscono un URI di sessione, poi i byte.

    Non multipart, che pure sarebbe una richiesta sola: Drive documenta il
    multipart per file fino a 5 MB, e qui un allegato può arrivare a 15
    (`documents/models.py::MAX_DOCUMENT_BYTES`). Scegliere la strada che
    funziona solo per i file piccoli significa aspettare la prima foto di
    bolletta fatta con un telefono recente per scoprirlo."""
    metadata: dict[str, object] = {"name": name}
    if existing_id is None:
        metadata["parents"] = [folder_id]

    start_headers = {
        "Authorization": f"Bearer {token}",
        "X-Upload-Content-Type": content_type,
        "X-Upload-Content-Length": str(len(content)),
    }
    params = {"uploadType": "resumable", "fields": "id"}
    if existing_id is None:
        start = await client.post(
            DRIVE_UPLOAD_ENDPOINT, headers=start_headers, params=params, json=metadata
        )
    else:
        start = await client.patch(
            f"{DRIVE_UPLOAD_ENDPOINT}/{existing_id}",
            headers=start_headers, params=params, json=metadata,
        )
    if start.status_code not in (200, 201):
        raise GoogleDriveError(_google_error_message(start, f"caricare «{name}» su Drive"))

    session_uri = start.headers.get("Location")
    if not session_uri:
        raise GoogleDriveError(f"Google non ha aperto la sessione di caricamento per «{name}».")

    response = await client.put(
        session_uri,
        headers={"Authorization": f"Bearer {token}", "Content-Type": content_type},
        content=content,
    )
    if response.status_code not in (200, 201):
        raise GoogleDriveError(_google_error_message(response, f"caricare «{name}» su Drive"))


async def upload_dossier(
    db: AsyncSession, *, organization_id: uuid.UUID, dossier: Dossier
) -> DriveUploadResult:
    """Crea (o ritrova) la cartella `<nome cliente>-<id contratto>` e ci
    mette dentro tutto il dossier.

    Premere due volte il pulsante non deve produrre due cartelle né due
    copie di ogni allegato: se la cartella c'è già la riusa, e un file con
    lo stesso nome viene **sostituito**, non affiancato. Il criterio è il
    nome perché è ciò che un umano vede aprendo la cartella, ed è quello che
    deve restare coerente."""
    org = await _org(db, organization_id)
    parent_id = (org.settings or {}).get(SETTING_PARENT_FOLDER_ID) or "root"

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        token = await _access_token(client, org=org)

        folder_id = await _find_child(
            client, token=token, name=dossier.folder_name, parent_id=parent_id,
            mime_type=FOLDER_MIME_TYPE,
        )
        if folder_id is None:
            folder_id = await _create_folder(
                client, token=token, name=dossier.folder_name, parent_id=parent_id
            )

        uploaded = replaced = 0
        for file in dossier.files:
            existing_id = await _find_child(
                client, token=token, name=file.name, parent_id=folder_id, mime_type=None
            )
            await _upload_file(
                client, token=token, folder_id=folder_id, name=file.name,
                content=file.content, content_type=file.content_type, existing_id=existing_id,
            )
            if existing_id is None:
                uploaded += 1
            else:
                replaced += 1

    return DriveUploadResult(
        folder_id=folder_id,
        folder_url=f"https://drive.google.com/drive/folders/{folder_id}",
        folder_name=dossier.folder_name,
        uploaded=uploaded,
        replaced=replaced,
    )
