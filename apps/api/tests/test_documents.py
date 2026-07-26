"""Covers the private, sensitive document upload/review flow for contracts:
required document types differ for private vs. company customers, a document
goes through PENDING_REVIEW -> APPROVED/REJECTED, and the presigned URL
mechanism never returns a public/guessable link."""

import uuid

import pytest

from app.core.security import hash_password
from app.domains.catalog.models import Product, ProductVersion
from app.domains.contracts import service as contract_service
from app.domains.customers.models import Address, Customer, SupplyPoint
from app.domains.documents import service as documents_service
from app.domains.network import service as network_service
from app.domains.users.models import User

from tests.test_commission_engine_integration import _make_actor


async def _make_customer_and_supply_point(db, organization_id, *, kind="PRIVATE"):
    customer = Customer(organization_id=organization_id, kind=kind, email=f"doc-{uuid.uuid4().hex[:8]}@example.com")
    db.add(customer)
    await db.flush()
    address = Address(
        organization_id=organization_id, customer_id=customer.id, kind="SUPPLY",
        street="Via Documenti 1", city="Roma", province="RM", postal_code="00100",
    )
    db.add(address)
    await db.flush()
    supply_point = SupplyPoint(
        organization_id=organization_id, customer_id=customer.id, energy_type="ELECTRICITY",
        supply_address_id=address.id,
    )
    db.add(supply_point)
    await db.commit()
    return customer, supply_point


async def _make_contract(db, organization_id, *, customer_kind="PRIVATE"):
    actor_user_id = await _make_actor(db, organization_id)
    customer, supply_point = await _make_customer_and_supply_point(db, organization_id, kind=customer_kind)

    product = Product(organization_id=organization_id, code=f"DOC-{uuid.uuid4().hex[:6]}", energy_type="ELECTRICITY", customer_type="PRIVATE")
    db.add(product)
    await db.flush()
    from app.core.db import utcnow

    product_version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Test document product", base_price_cents=1000,
        contract_duration_months=12, valid_from=utcnow(),
    )
    db.add(product_version)
    await db.commit()

    agent = await network_service.create_agent(
        db, organization_id=organization_id, display_name="Doc Agent",
        promoter_code=f"DA-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    contract = await contract_service.create_contract(
        db, organization_id=organization_id, customer_id=customer.id, supply_point_id=supply_point.id,
        product_version_id=product_version.id, producer_agent_id=agent.id,
        actor_user_id=actor_user_id, correlation_id=str(uuid.uuid4()),
    )
    return contract, customer, actor_user_id


def test_required_document_types_for_private_customer():
    types = documents_service.required_document_types_for("PRIVATE")
    assert set(types) == {"IDENTITY", "FISCAL_CODE", "UTILITY_BILL"}
    assert "CHAMBER_OF_COMMERCE" not in types


def test_required_document_types_for_company_customer():
    types = documents_service.required_document_types_for("COMPANY")
    assert "CHAMBER_OF_COMMERCE" in types
    assert set(types) == {"IDENTITY", "FISCAL_CODE", "UTILITY_BILL", "CHAMBER_OF_COMMERCE"}


@pytest.mark.asyncio
async def test_upload_document_and_read_back(db, organization_id):
    contract, customer, actor_user_id = await _make_contract(db, organization_id)

    document = await documents_service.upload_document(
        db, organization_id=organization_id, contract_id=contract.id, document_type="IDENTITY",
        file_bytes=b"fake pdf bytes for a test", content_type="application/pdf",
        original_filename="carta_identita.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
    )
    assert document.status == "PENDING_REVIEW"
    assert document.document_type == "IDENTITY"
    assert document.storage_key.startswith(f"documents/{contract.id}/")

    docs = await documents_service.list_documents_for_contract(
        db, organization_id=organization_id, contract_id=contract.id
    )
    assert len(docs) == 1
    assert docs[0].id == document.id


@pytest.mark.asyncio
async def test_upload_document_rejects_unknown_document_type(db, organization_id):
    contract, customer, actor_user_id = await _make_contract(db, organization_id)
    with pytest.raises(documents_service.DocumentValidationError):
        await documents_service.upload_document(
            db, organization_id=organization_id, contract_id=contract.id, document_type="NOT_A_REAL_TYPE",
            file_bytes=b"irrelevant", content_type="application/pdf",
            original_filename="x.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
        )


@pytest.mark.asyncio
async def test_contract_documents_status_shows_missing_and_uploaded(db, organization_id):
    contract, customer, actor_user_id = await _make_contract(db, organization_id, customer_kind="COMPANY")

    await documents_service.upload_document(
        db, organization_id=organization_id, contract_id=contract.id, document_type="IDENTITY",
        file_bytes=b"id bytes", content_type="application/pdf",
        original_filename="id.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
    )

    rows = await documents_service.get_contract_documents_status(
        db, organization_id=organization_id, contract=contract, customer_kind="COMPANY"
    )
    by_type = {r["document_type"]: r["document"] for r in rows}
    assert set(by_type.keys()) == {"IDENTITY", "FISCAL_CODE", "UTILITY_BILL", "CHAMBER_OF_COMMERCE"}
    assert by_type["IDENTITY"] is not None
    assert by_type["FISCAL_CODE"] is None
    assert by_type["CHAMBER_OF_COMMERCE"] is None


@pytest.mark.asyncio
async def test_review_document_approve_and_reject(db, organization_id):
    contract, customer, actor_user_id = await _make_contract(db, organization_id)
    admin_user_id = await _make_actor(db, organization_id)

    document = await documents_service.upload_document(
        db, organization_id=organization_id, contract_id=contract.id, document_type="UTILITY_BILL",
        file_bytes=b"bill bytes", content_type="image/jpeg",
        original_filename="bolletta.jpg", actor_user_id=actor_user_id, actor_role="CUSTOMER",
    )

    approved = await documents_service.review_document(
        db, organization_id=organization_id, document_id=document.id, new_status="APPROVED",
        review_note="Documento chiaro e leggibile", actor_user_id=admin_user_id,
    )
    assert approved.status == "APPROVED"
    assert approved.reviewed_by_user_id == admin_user_id
    assert approved.reviewed_at is not None

    rejected = await documents_service.review_document(
        db, organization_id=organization_id, document_id=document.id, new_status="REJECTED",
        review_note="In realtà è sfocato, richiedine uno nuovo", actor_user_id=admin_user_id,
    )
    assert rejected.status == "REJECTED"
    assert rejected.review_note == "In realtà è sfocato, richiedine uno nuovo"


@pytest.mark.asyncio
async def test_presigned_document_url_is_time_limited_and_not_the_internal_endpoint(db, organization_id):
    contract, customer, actor_user_id = await _make_contract(db, organization_id)
    document = await documents_service.upload_document(
        db, organization_id=organization_id, contract_id=contract.id, document_type="IDENTITY",
        file_bytes=b"sensitive id document bytes", content_type="application/pdf",
        original_filename="id.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
    )

    url = await documents_service.get_presigned_url_for_document(document)
    # never the raw internal docker-network address -- that would be
    # unreachable from a browser AND would leak infrastructure details
    assert "minio:9000" not in url
    assert "X-Amz-Signature" in url or "X-Amz-Expires" in url
    assert document.storage_key in url


@pytest.mark.asyncio
async def test_get_document_returns_none_for_wrong_organization(db, organization_id):
    contract, customer, actor_user_id = await _make_contract(db, organization_id)
    document = await documents_service.upload_document(
        db, organization_id=organization_id, contract_id=contract.id, document_type="IDENTITY",
        file_bytes=b"x", content_type="application/pdf",
        original_filename="id.pdf", actor_user_id=actor_user_id, actor_role="CUSTOMER",
    )
    other_org_id = uuid.uuid4()
    result = await documents_service.get_document(db, organization_id=other_org_id, document_id=document.id)
    assert result is None
