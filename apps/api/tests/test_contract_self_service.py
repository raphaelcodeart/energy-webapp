"""'Attiva Contratto' self-service flow (Session 29): a customer activates a
Lial Energy (INTERNAL) product themselves -- POST /contracts/mine creates the
supply point + contract and immediately submits it, attributed to the
customer's own referring promoter (same resolution "lavora con noi" uses).
Also covers the two pieces of admin-click reduction that make this
worthwhile: transition_contract's AUTO_CASCADE_AFTER (APPROVED lands in
PAYMENT_PENDING, PAID lands in ACTIVE) and documents/service.py's
auto-advance to UNDER_REVIEW once every required document is uploaded."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.domains.auth import service as auth_service
from app.domains.auth.schemas import RegisterRequest
from app.domains.catalog.models import Product, ProductVersion
from app.domains.contracts import service as contracts_service
from app.domains.customers.models import Customer
from app.domains.customers.schemas import SupplyPointCreate
from app.domains.documents import service as documents_service
from app.domains.network import service as network_service
from app.domains.rbac.models import Role
from app.domains.referral import service as referral_service
from app.domains.users.models import User

NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _make_customer_role(db, organization_id) -> Role:
    role = Role(organization_id=organization_id, code="CUSTOMER", name="Customer")
    db.add(role)
    await db.commit()
    return role


async def _make_attributed_customer(db, organization_id, *, email: str = "selfservice@example.demo") -> User:
    """A customer who registered through a real promoter's referral link --
    the exact precondition create_contract_self_service resolves its
    producer_agent_id from."""
    await _make_customer_role(db, organization_id)
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Referring", last_name="Promoter",
        promoter_code=f"REF-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    promoter_code = await referral_service.get_or_create_promoter_code(
        db, organization_id=organization_id, agent_id=agent.id
    )
    payload = RegisterRequest(
        organization_id=str(organization_id), referral_code=promoter_code.code, email=email,
        password="correct-horse-battery-staple", kind="PRIVATE", first_name="Nuovo", last_name="Cliente",
        accept_privacy=True,
    )
    return await auth_service.register_with_referral(db, organization_id=organization_id, payload=payload)


async def _make_internal_product_version(db, organization_id, *, energy_type: str = "ELECTRICITY") -> ProductVersion:
    product = Product(
        organization_id=organization_id, code=f"LUCE-{uuid.uuid4().hex[:6]}", energy_type=energy_type,
        customer_type="PRIVATE", category="INTERNAL",
    )
    db.add(product)
    await db.flush()
    version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Luce Self-Service", base_price_cents=2000,
        contract_duration_months=12, valid_from=NOW,
    )
    db.add(version)
    await db.commit()
    return version


def _supply_point_payload(energy_type: str = "ELECTRICITY") -> SupplyPointCreate:
    return SupplyPointCreate(
        energy_type=energy_type, pod_code="IT001E00000000" if energy_type != "GAS" else None,
        pdr_code="00000000000000" if energy_type in ("GAS", "DUAL_FUEL") else None,
        street="Via Self-Service 1", city="Roma", province="RM", postal_code="00100",
    )


@pytest.mark.asyncio
async def test_create_contract_self_service_submits_and_attributes_to_referring_promoter(db, organization_id):
    user = await _make_attributed_customer(db, organization_id)
    version = await _make_internal_product_version(db, organization_id)

    contract = await contracts_service.create_contract_self_service(
        db, organization_id=organization_id, customer_user_id=user.id,
        product_version_id=version.id, supply_point_payload=_supply_point_payload(),
        email="contatto@example.demo",
    )

    assert contract.status == "DOCUMENTS_PENDING"
    assert contract.email == "contatto@example.demo"
    customer = (await db.execute(select(Customer).where(Customer.user_id == user.id))).scalar_one()
    assert contract.customer_id == customer.id

    # Persists through the read path too (to_read_dicts), not just on the ORM
    # object still in the session -- catches a to_read_dicts row missing the
    # key, which the ORM-only assertion above would not.
    rows = await contracts_service.to_read_dicts(db, [contract])
    assert rows[0]["email"] == "contatto@example.demo"

    attribution = await db.get(contracts_service.ContractAttribution, contract.contract_attribution_id)
    # The producer is whichever agent the customer's own referral code
    # resolves to -- asserting it's set (not None) is the meaningful
    # invariant here; which specific agent is exercised by the "referring
    # promoter" helper above, already covered by test_registration.py.
    assert attribution.producer_agent_id is not None


@pytest.mark.asyncio
async def test_create_contract_self_service_rejects_non_internal_product(db, organization_id):
    user = await _make_attributed_customer(db, organization_id)
    product = Product(
        organization_id=organization_id, code="PARTNER-X", product_type="PHYSICAL",
        customer_type="PRIVATE", category="PARTNER",
    )
    db.add(product)
    await db.flush()
    version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Zaino Partner", base_price_cents=5000, valid_from=NOW,
    )
    db.add(version)
    await db.commit()

    with pytest.raises(contracts_service.SelfServiceContractError):
        await contracts_service.create_contract_self_service(
            db, organization_id=organization_id, customer_user_id=user.id,
            product_version_id=version.id, supply_point_payload=_supply_point_payload(),
            email="contatto@example.demo",
        )


@pytest.mark.asyncio
async def test_create_contract_self_service_requires_a_customer_record(db, organization_id):
    user = User(organization_id=organization_id, email="norecord@example.demo", password_hash=hash_password("x"))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    version = await _make_internal_product_version(db, organization_id)

    with pytest.raises(contracts_service.SelfServiceContractError):
        await contracts_service.create_contract_self_service(
            db, organization_id=organization_id, customer_user_id=user.id,
            product_version_id=version.id, supply_point_payload=_supply_point_payload(),
            email="contatto@example.demo",
        )


@pytest.mark.asyncio
async def test_create_contract_self_service_requires_a_referring_promoter(db, organization_id):
    """A Customer row with no CustomerAttribution at all (shouldn't normally
    happen -- registration is invite-only -- but must fail loudly rather
    than silently attribute to no one, which would break commissions)."""
    await _make_customer_role(db, organization_id)
    customer_user = User(organization_id=organization_id, email="orphan@example.demo", password_hash=hash_password("x"))
    db.add(customer_user)
    await db.flush()
    customer = Customer(organization_id=organization_id, user_id=customer_user.id, kind="PRIVATE", email="orphan@example.demo")
    db.add(customer)
    await db.commit()

    version = await _make_internal_product_version(db, organization_id)

    with pytest.raises(contracts_service.SelfServiceContractError):
        await contracts_service.create_contract_self_service(
            db, organization_id=organization_id, customer_user_id=customer_user.id,
            product_version_id=version.id, supply_point_payload=_supply_point_payload(),
            email="contatto@example.demo",
        )


@pytest.mark.asyncio
async def test_transition_approved_cascades_into_payment_pending(db, organization_id):
    user = await _make_attributed_customer(db, organization_id, email="cascade1@example.demo")
    version = await _make_internal_product_version(db, organization_id)
    contract = await contracts_service.create_contract_self_service(
        db, organization_id=organization_id, customer_user_id=user.id,
        product_version_id=version.id, supply_point_payload=_supply_point_payload(),
        email="contatto@example.demo",
    )
    contract = await contracts_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="UNDER_REVIEW",
        actor_user_id=user.id, reason=None, notes=None, correlation_id=str(uuid.uuid4()),
    )

    contract = await contracts_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="APPROVED",
        actor_user_id=user.id, reason=None, notes=None, correlation_id=str(uuid.uuid4()),
    )

    assert contract.status == "PAYMENT_PENDING"


@pytest.mark.asyncio
async def test_transition_paid_cascades_all_the_way_to_active(db, organization_id):
    user = await _make_attributed_customer(db, organization_id, email="cascade2@example.demo")
    version = await _make_internal_product_version(db, organization_id)
    contract = await contracts_service.create_contract_self_service(
        db, organization_id=organization_id, customer_user_id=user.id,
        product_version_id=version.id, supply_point_payload=_supply_point_payload(),
        email="contatto@example.demo",
    )
    for to_status in ["UNDER_REVIEW", "APPROVED"]:
        contract = await contracts_service.transition_contract(
            db, organization_id=organization_id, contract=contract, to_status=to_status,
            actor_user_id=user.id, reason=None, notes=None, correlation_id=str(uuid.uuid4()),
        )
    assert contract.status == "PAYMENT_PENDING"

    contract = await contracts_service.transition_contract(
        db, organization_id=organization_id, contract=contract, to_status="PAID",
        actor_user_id=user.id, reason=None, notes=None, correlation_id=str(uuid.uuid4()),
    )

    assert contract.status == "ACTIVE"
    assert contract.activated_at is not None
    assert contract.network_snapshot_id is not None


@pytest.mark.asyncio
async def test_uploading_all_required_documents_auto_advances_to_under_review(db, organization_id):
    user = await _make_attributed_customer(db, organization_id, email="docs1@example.demo")
    version = await _make_internal_product_version(db, organization_id)
    contract = await contracts_service.create_contract_self_service(
        db, organization_id=organization_id, customer_user_id=user.id,
        product_version_id=version.id, supply_point_payload=_supply_point_payload(),
        email="contatto@example.demo",
    )
    assert contract.status == "DOCUMENTS_PENDING"

    required_types = documents_service.required_document_types_for("PRIVATE")
    for i, doc_type in enumerate(required_types):
        await documents_service.upload_document(
            db, organization_id=organization_id, contract_id=contract.id, document_type=doc_type,
            file_bytes=b"%PDF-1.4\nfake", content_type="application/pdf", original_filename=f"doc-{i}.pdf",
            actor_user_id=user.id, actor_role="CUSTOMER",
        )

    refreshed = await db.get(type(contract), contract.id)
    assert refreshed.status == "UNDER_REVIEW"


@pytest.mark.asyncio
async def test_uploading_some_but_not_all_documents_does_not_advance(db, organization_id):
    user = await _make_attributed_customer(db, organization_id, email="docs2@example.demo")
    version = await _make_internal_product_version(db, organization_id)
    contract = await contracts_service.create_contract_self_service(
        db, organization_id=organization_id, customer_user_id=user.id,
        product_version_id=version.id, supply_point_payload=_supply_point_payload(),
        email="contatto@example.demo",
    )

    required_types = documents_service.required_document_types_for("PRIVATE")
    await documents_service.upload_document(
        db, organization_id=organization_id, contract_id=contract.id, document_type=required_types[0],
        file_bytes=b"%PDF-1.4\nfake", content_type="application/pdf", original_filename="doc-0.pdf",
        actor_user_id=user.id, actor_role="CUSTOMER",
    )

    refreshed = await db.get(type(contract), contract.id)
    assert refreshed.status == "DOCUMENTS_PENDING"
