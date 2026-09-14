"""«Lavora con noi»: si firma un testo preciso, non una casella.

The application used to record a single boolean plus a version string, and
the text shown on screen was a one-paragraph summary hardcoded in a React
component -- i.e. the app displayed something that was not the contract.

Now the legal text lives on the server, versioned, and an application must
accept EVERY currently-required document at the exact version it was served.
That matters because a signature is only meaningful together with the wording
it was given for.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.security import hash_otp_code, hash_password
from app.domains.auth import service as auth_service
from app.domains.auth.models import OtpCode
from app.domains.network import collaboration_documents
from app.domains.network import service as network_service
from app.domains.rbac.models import Role
from app.domains.referral import service as referral_service
from app.domains.users.models import User

VALID_OTP_CODE = "123456"


async def _make_applicant(db, organization_id) -> User:
    """A customer attributed to a promoter -- the normal state of anybody who
    can press "Lavora con noi"."""
    role = Role(organization_id=organization_id, code="PROMOTER", name="Promoter")
    db.add(role)
    sponsor = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Sponsor", last_name="Tester",
        promoter_code=f"SP-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    await referral_service.get_or_create_promoter_code(
        db, organization_id=organization_id, agent_id=sponsor.id
    )
    user = User(
        organization_id=organization_id, email=f"applicant-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _fresh_otp(db, user: User) -> str:
    """Seeds a known OTP directly rather than going through the email-sending
    request_otp() -- same approach as test_promoter_self_service.py. The
    subject here is document acceptance; OTP secrecy is covered there."""
    db.add(
        OtpCode(
            user_id=user.id,
            purpose=auth_service.PROMOTER_APPLICATION_OTP_PURPOSE,
            code_hash=hash_otp_code(VALID_OTP_CODE),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    await db.commit()
    return VALID_OTP_CODE


def test_the_contract_text_is_real_and_lives_on_the_server():
    """Guards against the regression this replaced: a summary paragraph
    standing in for the contract."""
    contract = collaboration_documents.document_by_key("CONTRACT")
    assert contract is not None

    text = " ".join(
        block.get("text", "") + " ".join(block.get("items", []))
        for block in contract.blocks
    )
    # Landmarks from the real paper contract.
    assert "procacciamento di affari" in contract.title.lower()
    assert "13438020011" in text, "manca il codice fiscale di LIAL"
    assert "L. 3 febbraio 1989, n. 39" in text, "manca l'obbligo di iscrizione all'albo"
    assert "Foro di Torino" in text
    assert "Reg. UE n. 2016/679" in text
    assert "1456 c.c." in text

    # Every numbered article of the paper contract must be present.
    numbers = {b["number"] for b in contract.blocks if b["type"] == "clause"}
    for expected in ("1.1.", "2.2.", "3.6.", "4.3.", "5.2.", "6.4.", "7.7.", "8.5.", "9.9.", "16.1."):
        assert expected in numbers, f"clausola {expected} mancante"


def test_the_attachment_is_its_own_document_and_says_so_in_its_title():
    """Artt. 1341 e ss. c.c. require the clausole vessatorie to be approved
    separately from the contract, so this cannot be folded into the document
    above. It also has to READ as the attachment it is -- the word "Allegato"
    belongs in the title, not only in the body."""
    attachment = collaboration_documents.document_by_key("SPECIFIC_CLAUSES")
    assert attachment is not None
    assert "allegato" in attachment.title.lower()
    assert "allegato" in attachment.acceptance_label.lower()

    text = " ".join(
        block.get("text", "") + " ".join(block.get("items", []))
        for block in attachment.blocks
    )
    assert "1341" in text
    for clause_no in ("n. 2", "n. 3", "n. 5", "n. 7", "n. 9", "n. 16"):
        assert clause_no in text
    # Both annexes the contract itself names must appear here.
    assert "Allegato A" in text and "Tabella dei compensi" in text
    assert "Allegato B" in text and "avanzamenti di carriera" in text


def test_no_document_talks_about_the_paper_form():
    """The paper contract is the SOURCE of this text, not its subject. A
    reader on screen should never be told what a sheet of paper they have
    never seen requires -- it reads as an excuse for the interface."""
    for doc in collaboration_documents.COLLABORATION_DOCUMENTS:
        haystack = " ".join(
            [doc.title, doc.subtitle, doc.acceptance_label]
            + [b.get("text", "") + " ".join(b.get("items", [])) for b in doc.blocks]
        ).lower()
        for forbidden in ("cartace", "sul modulo di carta", "firma separata"):
            assert forbidden not in haystack, f"{doc.key} parla del cartaceo"


def test_no_document_carries_markup():
    """The dashboard renders structured blocks as text and never interprets
    HTML. A stray tag here would show up literally on screen -- or, worse,
    tempt somebody into adding dangerouslySetInnerHTML."""
    for doc in collaboration_documents.COLLABORATION_DOCUMENTS:
        for block in doc.blocks:
            payload = block.get("text", "") + " ".join(block.get("items", []))
            assert "<" not in payload and ">" not in payload, f"markup in {doc.key}"


@pytest.mark.asyncio
async def test_applying_records_every_document_with_its_version(db, organization_id):
    user = await _make_applicant(db, organization_id)
    code = await _fresh_otp(db, user)

    agent = await network_service.apply_as_promoter(
        db, organization_id=organization_id, user_id=user.id,
        first_name="Nuovo", last_name="Promoter", accept_contract=True, otp_code=code,
        accepted_documents=collaboration_documents.required_versions(),
    )

    recorded = agent.collaboration_accepted_documents
    assert set(recorded) == set(collaboration_documents.required_versions())
    for key, version in collaboration_documents.required_versions().items():
        assert recorded[key]["version"] == version
        assert recorded[key]["accepted_at"], "manca il momento dell'accettazione"
    assert agent.collaboration_accepted_at is not None


@pytest.mark.asyncio
async def test_missing_one_document_is_refused(db, organization_id):
    """Ticking the contract but not the separate clause approval must not get
    through -- the whole point of having two."""
    user = await _make_applicant(db, organization_id)
    code = await _fresh_otp(db, user)

    partial = collaboration_documents.required_versions()
    partial.pop("SPECIFIC_CLAUSES")

    with pytest.raises(network_service.ContractNotAcceptedError, match="Allegato al contratto"):
        await network_service.apply_as_promoter(
            db, organization_id=organization_id, user_id=user.id,
            first_name="Nuovo", last_name="Promoter", accept_contract=True, otp_code=code,
            accepted_documents=partial,
        )


@pytest.mark.asyncio
async def test_accepting_a_stale_version_is_refused(db, organization_id):
    """Somebody who left the page open while the contract was updated must not
    have their acceptance silently recorded against the NEW wording."""
    user = await _make_applicant(db, organization_id)
    code = await _fresh_otp(db, user)

    stale = {key: "1999.0" for key in collaboration_documents.required_versions()}

    with pytest.raises(network_service.ContractNotAcceptedError):
        await network_service.apply_as_promoter(
            db, organization_id=organization_id, user_id=user.id,
            first_name="Nuovo", last_name="Promoter", accept_contract=True, otp_code=code,
            accepted_documents=stale,
        )


@pytest.mark.asyncio
async def test_sending_nothing_at_all_is_refused(db, organization_id):
    user = await _make_applicant(db, organization_id)
    code = await _fresh_otp(db, user)

    with pytest.raises(network_service.ContractNotAcceptedError):
        await network_service.apply_as_promoter(
            db, organization_id=organization_id, user_id=user.id,
            first_name="Nuovo", last_name="Promoter", accept_contract=True, otp_code=code,
            accepted_documents={},
        )


@pytest.mark.asyncio
async def test_the_otp_is_still_required_on_top_of_the_acceptances(db, organization_id):
    """Reading and ticking is not signing: the emailed code is what proves the
    account holder, not just whoever is logged in, agreed."""
    user = await _make_applicant(db, organization_id)

    with pytest.raises(network_service.InvalidOtpError):
        await network_service.apply_as_promoter(
            db, organization_id=organization_id, user_id=user.id,
            first_name="Nuovo", last_name="Promoter", accept_contract=True, otp_code="000000",
            accepted_documents=collaboration_documents.required_versions(),
        )
