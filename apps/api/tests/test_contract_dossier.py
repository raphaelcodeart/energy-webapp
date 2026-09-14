"""Il fascicolo di un contratto: zip con tutti gli allegati + PDF riassuntivo.

È quello che l'amministrazione manda fuori di qui -- al fornitore, al
commercialista, a un legale. Le cose che contano davvero sono tre: che non
manchi niente, che il nome del file sia quello concordato anche quando il
cliente si chiama "Bàr D'Angelo & C. S.r.l.", e che un allegato irrecuperabile
non porti giù l'intero fascicolo.
"""

import io
import uuid
import zipfile

import pytest
import reportlab.rl_config

from app.domains.catalog.models import Product, ProductVersion
from app.domains.contracts import dossier
from app.domains.contracts import service as contract_service
from app.domains.customers.models import Address, Company, Customer, CustomerProfile, SupplyPoint
from app.domains.documents import service as documents_service
from app.domains.network import service as network_service
from tests.test_commission_engine_integration import _make_actor

PDF_BYTES = b"%PDF-1.4\ncontenuto finto ma con l'intestazione giusta"
JPEG_BYTES = b"\xff\xd8\xff" + b"finta foto"


async def _make_contract(db, organization_id, *, kind="PRIVATE", first_name="Mario", last_name="Rossi",
                         company_name=None):
    actor_user_id = await _make_actor(db, organization_id)
    customer = Customer(
        organization_id=organization_id, kind=kind, email="dossier@example.com",
        fiscal_code="RSSMRA80A01H501U", vat_number="12345678901", phone="+39 333 1234567",
    )
    db.add(customer)
    await db.flush()
    if company_name is not None:
        db.add(Company(customer_id=customer.id, company_name=company_name, legal_form="S.r.l."))
    else:
        db.add(CustomerProfile(customer_id=customer.id, first_name=first_name, last_name=last_name))
    address = Address(
        organization_id=organization_id, customer_id=customer.id, kind="SUPPLY",
        street="Via Dossier 1", city="Roma", province="RM", postal_code="00100",
    )
    db.add(address)
    await db.flush()
    supply_point = SupplyPoint(
        organization_id=organization_id, customer_id=customer.id, energy_type="ELECTRICITY",
        supply_address_id=address.id, pod_code="IT001E12345678", label="Abitazione principale",
    )
    db.add(supply_point)

    product = Product(
        organization_id=organization_id, code=f"DOS-{uuid.uuid4().hex[:6]}",
        energy_type="ELECTRICITY", customer_type="BOTH", category="INTERNAL",
    )
    db.add(product)
    await db.flush()
    from app.core.db import utcnow

    version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Energia Circolare",
        base_price_cents=24900, contract_duration_months=12, valid_from=utcnow(),
    )
    db.add(version)
    await db.commit()

    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Anna", last_name="Bianchi",
        promoter_code=f"DOS-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id,
        supply_point_id=supply_point.id, product_version_id=version.id,
        producer_agent_id=agent.id, actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )
    return contract, actor_user_id


async def _upload(db, organization_id, contract, actor_user_id, *, document_type, description=None,
                  filename="file.pdf", content=PDF_BYTES, content_type="application/pdf"):
    return await documents_service.upload_document(
        db, organization_id=organization_id, contract_id=contract.id, document_type=document_type,
        description=description, file_bytes=content, content_type=content_type,
        original_filename=filename, actor_user_id=actor_user_id, actor_role="CUSTOMER",
    )


# --- Il nome dei file --------------------------------------------------------


def test_a_customer_name_survives_becoming_a_filename():
    """Gli accenti restano -- il fascicolo si chiama come si chiama il
    cliente -- mentre sparisce solo ciò che romperebbe un percorso."""
    assert dossier.sanitize_filename_component("Bàrbara D'Angelo") == "Bàrbara D'Angelo"
    assert dossier.sanitize_filename_component("Rossi / Bianchi S.r.l.") == "Rossi Bianchi S.r.l"
    assert dossier.sanitize_filename_component('A"B<C>D|E?F*G') == "A B C D E F G"
    assert dossier.sanitize_filename_component("nome\x00con\x1fcontrolli") == "nome con controlli"


def test_a_trailing_dot_is_removed_because_windows_removes_it_anyway():
    """Se lo lasciassimo, il nome sul disco dell'utente non sarebbe più
    quello che abbiamo scritto noi."""
    assert dossier.sanitize_filename_component("Studio Rossi...") == "Studio Rossi"
    assert dossier.sanitize_filename_component("  spazi  ") == "spazi"


def test_the_dos_device_names_are_still_a_problem_in_2026():
    assert dossier.sanitize_filename_component("CON") == "_CON"
    assert dossier.sanitize_filename_component("lpt1") == "_lpt1"


def test_an_empty_or_unusable_name_still_produces_a_file():
    assert dossier.sanitize_filename_component("///") == "documento"
    assert dossier.sanitize_filename_component("", fallback="Cliente") == "Cliente"


def test_a_very_long_company_name_is_cut_before_the_filesystem_cuts_it():
    name = dossier.sanitize_filename_component("A" * 300)
    assert len(name) == dossier.MAX_NAME_COMPONENT


def test_amounts_read_like_italian_money():
    assert dossier._fmt_cents(24900) == "249,00 €"
    assert dossier._fmt_cents(123456789) == "1.234.567,89 €"
    assert dossier._fmt_cents(None) == "—"


# --- Il fascicolo ------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_archive_is_named_after_the_customer_and_the_contract(db, organization_id):
    contract, _ = await _make_contract(db, organization_id)
    built = await dossier.build_dossier(db, organization_id=organization_id, contract=contract)
    assert built.folder_name == f"Mario Rossi-{contract.id}"
    assert built.zip_filename == f"Mario Rossi-{contract.id}.zip"


@pytest.mark.asyncio
async def test_the_archive_holds_the_summary_plus_every_attachment(db, organization_id):
    contract, actor_user_id = await _make_contract(db, organization_id)
    await _upload(db, organization_id, contract, actor_user_id, document_type="IDENTITY")
    await _upload(db, organization_id, contract, actor_user_id, document_type="UTILITY_BILL",
                  content=JPEG_BYTES, content_type="image/jpeg", filename="bolletta.jpg")
    await _upload(db, organization_id, contract, actor_user_id, document_type="OTHER",
                  description="Delega firmata")

    built = await dossier.build_dossier(db, organization_id=organization_id, contract=contract)
    names = [f.name for f in built.files]
    assert names[0] == dossier.SUMMARY_FILENAME
    assert names[1:] == [
        "01 - Documento d'identità.pdf",
        "02 - Fattura luce gas.jpg",
        "03 - Delega firmata.pdf",
    ]

    with zipfile.ZipFile(io.BytesIO(dossier.zip_bytes(built))) as archive:
        assert archive.namelist() == names
        assert archive.read("02 - Fattura luce gas.jpg") == JPEG_BYTES
        assert archive.read(dossier.SUMMARY_FILENAME).startswith(b"%PDF")


@pytest.mark.asyncio
async def test_a_contract_with_no_attachments_still_produces_a_usable_archive(db, organization_id):
    contract, _ = await _make_contract(db, organization_id)
    built = await dossier.build_dossier(db, organization_id=organization_id, contract=contract)
    assert [f.name for f in built.files] == [dossier.SUMMARY_FILENAME]
    with zipfile.ZipFile(io.BytesIO(dossier.zip_bytes(built))) as archive:
        assert archive.read(dossier.SUMMARY_FILENAME).startswith(b"%PDF")


@pytest.mark.asyncio
async def test_one_unrecoverable_attachment_does_not_take_down_the_whole_dossier(
    db, organization_id, monkeypatch
):
    """Un file sparito dal bucket (cancellato a mano, migrazione storage
    andata storta) non deve far fallire il download: gli altri allegati e il
    riepilogo servono lo stesso, e chi apre la cartella deve leggere cosa
    manca invece di doversene accorgere contando i file."""
    contract, actor_user_id = await _make_contract(db, organization_id)
    await _upload(db, organization_id, contract, actor_user_id, document_type="IDENTITY")

    def boom(**kwargs):
        raise RuntimeError("NoSuchKey")

    # Patch sul nome importato DENTRO dossier.py: l'import è per valore, e
    # toccare app.core.storage.download_document non cambierebbe nulla qui.
    monkeypatch.setattr(dossier, "download_document", boom)

    built = await dossier.build_dossier(db, organization_id=organization_id, contract=contract)
    names = [f.name for f in built.files]
    assert names == [dossier.SUMMARY_FILENAME, "01 - Documento d'identità (MANCANTE).txt"]
    placeholder = built.files[1].content.decode("utf-8")
    assert "non è stato recuperato" in placeholder
    assert str(built.files[1].name).endswith(".txt")


@pytest.mark.asyncio
async def test_a_company_dossier_is_named_after_the_company(db, organization_id):
    contract, _ = await _make_contract(
        db, organization_id, kind="COMPANY", company_name="Bàr D'Angelo & C. S.r.l."
    )
    built = await dossier.build_dossier(db, organization_id=organization_id, contract=contract)
    assert built.folder_name.startswith("Bàr D'Angelo & C. S.r.l")
    assert "/" not in built.folder_name


# --- Il PDF ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_summary_pdf_actually_carries_the_data(db, organization_id, monkeypatch):
    """Un PDF che si apre ma è vuoto passerebbe qualunque controllo sul solo
    `%PDF`. Qui la compressione dei flussi viene spenta per la durata del
    test, così i testi restano leggibili nei byte e si può verificare che ci
    siano davvero."""
    monkeypatch.setattr(reportlab.rl_config, "pageCompression", 0)

    contract, actor_user_id = await _make_contract(db, organization_id)
    await _upload(db, organization_id, contract, actor_user_id, document_type="IDENTITY")
    built = await dossier.build_dossier(db, organization_id=organization_id, contract=contract)

    pdf = built.files[0].content
    assert pdf.startswith(b"%PDF")
    for expected in (
        b"Mario Rossi",            # intestatario
        b"IT001E12345678",         # POD
        b"Energia Circolare",      # prodotto
        b"RSSMRA80A01H501U",       # codice fiscale
        b"Anna Bianchi",           # promoter
        b"Abitazione principale",  # punto di fornitura
    ):
        assert expected in pdf, f"manca dal PDF: {expected!r}"


@pytest.mark.asyncio
async def test_the_summary_lists_the_attachments_with_their_review_state(db, organization_id, monkeypatch):
    monkeypatch.setattr(reportlab.rl_config, "pageCompression", 0)

    contract, actor_user_id = await _make_contract(db, organization_id)
    document = await _upload(db, organization_id, contract, actor_user_id, document_type="OTHER",
                             description="Contratto di locazione")
    admin_user_id = await _make_actor(db, organization_id)
    await documents_service.review_document(
        db, organization_id=organization_id, document_id=document.id, new_status="APPROVED",
        review_note=None, actor_user_id=admin_user_id,
    )

    built = await dossier.build_dossier(db, organization_id=organization_id, contract=contract)
    pdf = built.files[0].content
    assert b"Contratto di locazione" in pdf
    assert b"Approvato" in pdf
