from pydantic import BaseModel, Field


class GoogleDriveStatusRead(BaseModel):
    """Lo stato del collegamento, senza mai far uscire un segreto.

    `client_secret` e il refresh token non tornano indietro in nessuna
    forma -- stesso trattamento della chiave segreta Stripe
    (organizations/schemas.py::PaymentSettingsRead): del secret si sa solo
    se c'è, del token solo che il collegamento è attivo."""

    #: Client ID e secret inseriti: prima di questo non c'è niente da premere.
    configured: bool
    #: Qualcuno ha autorizzato il proprio account Google.
    connected: bool
    account_email: str | None = None
    connected_at: str | None = None
    #: Se valorizzato, le cartelle dei contratti nascono qui dentro invece
    #: che nella radice del Drive di chi ha autorizzato.
    parent_folder_id: str | None = None
    #: Da incollare tale e quale fra gli "Authorized redirect URIs" del
    #: client OAuth sulla console Google Cloud.
    redirect_uri: str
    #: Non è un segreto -- viaggia in chiaro nell'URL di consenso di Google --
    #: e rivederlo è l'unico modo per accorgersi di averlo incollato male.
    client_id: str | None = None
    client_secret_configured: bool = False


class GoogleDriveCredentialsUpdate(BaseModel):
    client_id: str | None = Field(default=None, max_length=255)
    client_secret: str | None = Field(default=None, max_length=255)
    parent_folder_id: str | None = Field(default=None, max_length=255)


class GoogleDriveAuthorizeUrlRead(BaseModel):
    url: str


class GoogleDriveCallbackRequest(BaseModel):
    code: str
    state: str


class DriveUploadResultRead(BaseModel):
    folder_name: str
    folder_url: str
    #: File nuovi creati adesso.
    uploaded: int
    #: File già presenti sovrascritti -- premere due volte il pulsante non
    #: duplica niente, e questo numero è come lo si vede.
    replaced: int
