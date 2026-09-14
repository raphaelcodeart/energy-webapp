"""Un cliente non deve restare bloccato perché il suo promoter è stato disattivato.

The bug, reported from production: a customer opened "Attiva Contratto",
filled in the supply point, pressed "Continua" and got
**"Si è verificato un errore imprevisto. Riprova più tardi."** — the
dashboard's generic fallback, i.e. a 500 with a non-JSON body.

The cause was not a crash in the usual sense. `create_contract()` refuses to
attribute a contract to a non-ACTIVE agent, deliberately: a contract that
activates and pays nobody is the exact failure documented in
`docs/paid-contract-commission-audit.md`. But the customer's referring
promoter had been deactivated *after* they signed up, and
`POST /contracts/mine` never caught that refusal — so a business condition
the system understands perfectly surfaced as an unhandled exception, with no
way forward for a customer who had done nothing wrong. Three real customers
were in this state.

Business decision (taken explicitly): walk **up** to the nearest ACTIVE
sponsor rather than block. The branch that built the relationship keeps it,
nobody waits for an admin to notice, and the substitution is audited rather
than silent.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.domains.audit.models import AuditLog
from app.domains.catalog.models import Product, ProductVersion
from app.domains.contracts import service as contract_service
from app.domains.contracts.models import Contract, ContractAttribution
from app.domains.customers.models import Address, Customer, SupplyPoint
from app.domains.customers.schemas import SupplyPointCreate
from app.domains.network import service as network_service
from app.domains.referral import service as referral_service
from app.domains.users.models import User

NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _make_user(db, organization_id, prefix="u") -> User:
    user = User(
        organization_id=organization_id, email=f"{prefix}-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_agent(db, organization_id, *, name, parent_agent_id=None, user_id=None, status="ACTIVE"):
    return await network_service.create_agent(
        db, organization_id=organization_id, first_name=name, last_name="Tester",
        promoter_code=f"{name[:3].upper()}-{uuid.uuid4().hex[:8]}",
        parent_agent_id=parent_agent_id, user_id=user_id, status=status,
    )


async def _make_internal_product(db, organization_id) -> ProductVersion:
    product = Product(
        organization_id=organization_id, code=f"LU-{uuid.uuid4().hex[:6]}",
        energy_type="ELECTRICITY", customer_type="BOTH", category="INTERNAL",
    )
    db.add(product)
    await db.flush()
    version = ProductVersion(
        product_id=product.id, version_label="1.0", name="Luce Energia Circolare",
        base_price_cents=15_00, valid_from=NOW,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return version


async def _make_customer_referred_by(db, organization_id, agent_id, *, with_login=True):
    user = await _make_user(db, organization_id, prefix="cust") if with_login else None
    customer = Customer(
        organization_id=organization_id, kind="PRIVATE", user_id=user.id if user else None,
        email=f"c-{uuid.uuid4().hex[:8]}@example.com",
    )
    db.add(customer)
    await db.flush()
    address = Address(
        organization_id=organization_id, customer_id=customer.id, kind="SUPPLY",
        street="Via Test 1", city="Roma", province="RM", postal_code="00100",
    )
    db.add(address)
    await db.flush()
    db.add(SupplyPoint(
        organization_id=organization_id, customer_id=customer.id, energy_type="ELECTRICITY",
        supply_address_id=address.id,
    ))
    code = await referral_service.get_or_create_promoter_code(
        db, organization_id=organization_id, agent_id=agent_id
    )
    await referral_service.attribute_customer(
        db, organization_id=organization_id, customer_id=customer.id,
        promoter_code_id=code.id, referral_session_id=None,
    )
    await db.commit()
    await db.refresh(customer)
    return customer, user


def _supply_point_payload() -> SupplyPointCreate:
    return SupplyPointCreate(
        energy_type="ELECTRICITY", pod_code="IT001E12345678",
        street="Via Test 1", city="Roma", province="RM", postal_code="00100",
    )


async def _terminate(db, agent):
    agent.status = "TERMINATED"
    await db.commit()
    await db.refresh(agent)


@pytest.mark.asyncio
async def test_customer_can_still_activate_when_their_promoter_was_deactivated(db, organization_id):
    """The exact production scenario: sponsor -> promoter -> customer, and the
    promoter is deactivated afterwards. The contract must be created, and
    credited to the sponsor."""
    sponsor = await _make_agent(db, organization_id, name="Alessandro")
    promoter = await _make_agent(db, organization_id, name="Salvatore", parent_agent_id=sponsor.id)
    _customer, customer_user = await _make_customer_referred_by(db, organization_id, promoter.id)
    version = await _make_internal_product(db, organization_id)

    await _terminate(db, promoter)

    contract = await contract_service.create_contract_self_service(
        db, organization_id=organization_id, customer_user_id=customer_user.id,
        product_version_id=version.id, supply_point_payload=_supply_point_payload(),
        email="cliente@example.com",
    )

    attribution = await db.get(ContractAttribution, contract.contract_attribution_id)
    assert attribution.producer_agent_id == sponsor.id, "la provvigione deve andare allo sponsor attivo"
    # The original referrer is still recorded, so the substitution is visible
    # rather than rewriting history.
    assert contract.first_referrer_agent_id == promoter.id
    assert contract.status == "DOCUMENTS_PENDING"


@pytest.mark.asyncio
async def test_the_substitution_is_audited_not_silent(db, organization_id):
    sponsor = await _make_agent(db, organization_id, name="Alessandro")
    promoter = await _make_agent(db, organization_id, name="Salvatore", parent_agent_id=sponsor.id)
    _customer, customer_user = await _make_customer_referred_by(db, organization_id, promoter.id)
    version = await _make_internal_product(db, organization_id)
    await _terminate(db, promoter)

    contract = await contract_service.create_contract_self_service(
        db, organization_id=organization_id, customer_user_id=customer_user.id,
        product_version_id=version.id, supply_point_payload=_supply_point_payload(),
        email="cliente@example.com",
    )

    rows = list((await db.execute(
        select(AuditLog).where(
            AuditLog.action == "contract.producer_substituted",
            AuditLog.entity_id == str(contract.id),
        )
    )).scalars())
    assert len(rows) == 1
    assert rows[0].previous_value["producer_agent_id"] == str(promoter.id)
    assert rows[0].new_value["producer_agent_id"] == str(sponsor.id)


@pytest.mark.asyncio
async def test_no_substitution_audit_row_when_the_promoter_is_fine(db, organization_id):
    """The common case must stay completely unchanged -- no extra audit noise
    on every contract ever created."""
    promoter = await _make_agent(db, organization_id, name="Attiva")
    _customer, customer_user = await _make_customer_referred_by(db, organization_id, promoter.id)
    version = await _make_internal_product(db, organization_id)

    contract = await contract_service.create_contract_self_service(
        db, organization_id=organization_id, customer_user_id=customer_user.id,
        product_version_id=version.id, supply_point_payload=_supply_point_payload(),
        email="cliente@example.com",
    )

    attribution = await db.get(ContractAttribution, contract.contract_attribution_id)
    assert attribution.producer_agent_id == promoter.id
    rows = list((await db.execute(
        select(AuditLog).where(AuditLog.action == "contract.producer_substituted")
    )).scalars())
    assert rows == []


@pytest.mark.asyncio
async def test_it_walks_past_several_deactivated_levels(db, organization_id):
    """Two deactivated levels in a row: it must keep climbing, not give up at
    the first parent."""
    top = await _make_agent(db, organization_id, name="Top")
    middle = await _make_agent(db, organization_id, name="Middle", parent_agent_id=top.id)
    bottom = await _make_agent(db, organization_id, name="Bottom", parent_agent_id=middle.id)
    _customer, customer_user = await _make_customer_referred_by(db, organization_id, bottom.id)
    version = await _make_internal_product(db, organization_id)

    await _terminate(db, bottom)
    await _terminate(db, middle)

    contract = await contract_service.create_contract_self_service(
        db, organization_id=organization_id, customer_user_id=customer_user.id,
        product_version_id=version.id, supply_point_payload=_supply_point_payload(),
        email="cliente@example.com",
    )
    attribution = await db.get(ContractAttribution, contract.contract_attribution_id)
    assert attribution.producer_agent_id == top.id


@pytest.mark.asyncio
async def test_a_clear_italian_error_when_the_whole_upline_is_inactive(db, organization_id):
    """With nobody left to credit, blocking is the only honest answer -- but it
    must be a sentence the customer can act on, never a 500."""
    root = await _make_agent(db, organization_id, name="Root")
    promoter = await _make_agent(db, organization_id, name="Solo", parent_agent_id=root.id)
    _customer, customer_user = await _make_customer_referred_by(db, organization_id, promoter.id)
    version = await _make_internal_product(db, organization_id)

    await _terminate(db, promoter)
    await _terminate(db, root)

    with pytest.raises(contract_service.SelfServiceContractError) as exc:
        await contract_service.create_contract_self_service(
            db, organization_id=organization_id, customer_user_id=customer_user.id,
            product_version_id=version.id, supply_point_payload=_supply_point_payload(),
            email="cliente@example.com",
        )
    message = str(exc.value)
    assert "assistenza" in message
    # Not an English exception string with a UUID in it.
    assert "producer_agent_id" not in message
    assert "TERMINATED" not in message


@pytest.mark.asyncio
async def test_the_inheriting_sponsor_can_activate_for_that_customer_from_the_crm(db, organization_id):
    """Without this, a customer whose promoter left is unreachable from BOTH
    sides: they cannot self-activate, and nobody can do it for them either."""
    sponsor_user = await _make_user(db, organization_id, prefix="sponsor")
    sponsor = await _make_agent(db, organization_id, name="Alessandro", user_id=sponsor_user.id)
    promoter = await _make_agent(db, organization_id, name="Salvatore", parent_agent_id=sponsor.id)
    customer, _ = await _make_customer_referred_by(db, organization_id, promoter.id, with_login=False)
    version = await _make_internal_product(db, organization_id)

    await _terminate(db, promoter)

    contract = await contract_service.create_contract_for_recruited_customer(
        db, organization_id=organization_id, promoter_user_id=sponsor_user.id,
        customer_id=customer.id, product_version_id=version.id,
        supply_point_payload=_supply_point_payload(), email="cliente@example.com",
    )
    assert contract.activated_by_promoter_id == sponsor.id
    assert contract.created_by_role == "PROMOTER"


@pytest.mark.asyncio
async def test_an_unrelated_promoter_still_cannot_activate_for_someone_elses_customer(db, organization_id):
    """The walk-up must widen access to the upline only -- never to a promoter
    on a different branch."""
    sponsor = await _make_agent(db, organization_id, name="Alessandro")
    promoter = await _make_agent(db, organization_id, name="Salvatore", parent_agent_id=sponsor.id)
    stranger_user = await _make_user(db, organization_id, prefix="stranger")
    await _make_agent(db, organization_id, name="Estraneo", user_id=stranger_user.id)
    customer, _ = await _make_customer_referred_by(db, organization_id, promoter.id, with_login=False)
    version = await _make_internal_product(db, organization_id)

    await _terminate(db, promoter)

    with pytest.raises(contract_service.SelfServiceContractError, match="non è nella tua rete"):
        await contract_service.create_contract_for_recruited_customer(
            db, organization_id=organization_id, promoter_user_id=stranger_user.id,
            customer_id=customer.id, product_version_id=version.id,
            supply_point_payload=_supply_point_payload(), email="cliente@example.com",
        )


@pytest.mark.asyncio
async def test_no_contract_row_is_left_behind_when_activation_is_refused(db, organization_id):
    """A refusal must not leave a half-built contract in the database."""
    root = await _make_agent(db, organization_id, name="Root")
    promoter = await _make_agent(db, organization_id, name="Solo", parent_agent_id=root.id)
    customer, customer_user = await _make_customer_referred_by(db, organization_id, promoter.id)
    version = await _make_internal_product(db, organization_id)
    await _terminate(db, promoter)
    await _terminate(db, root)

    with pytest.raises(contract_service.SelfServiceContractError):
        await contract_service.create_contract_self_service(
            db, organization_id=organization_id, customer_user_id=customer_user.id,
            product_version_id=version.id, supply_point_payload=_supply_point_payload(),
            email="cliente@example.com",
        )

    contracts = list((await db.execute(
        select(Contract).where(Contract.customer_id == customer.id)
    )).scalars())
    assert contracts == []
