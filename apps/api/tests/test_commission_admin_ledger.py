"""Admin-facing commission traceability + payment tracking: which contract,
which customer, which promoter, from how many network levels below the
producer, and the exact calculation breakdown -- plus marking a movement as
actually paid (status ACCRUED -> PAID, paid_date set)."""

import pytest
from sqlalchemy import select

from app.domains.commissions.models import CommissionMovement
from app.domains.commissions.services import admin_ledger
from app.domains.commissions.tasks.dispatch import process_pending_outbox_events

from tests.test_commission_engine_integration import (
    _advance_to_active,
    _make_actor,
    _setup_contract_ready_to_activate,
)


@pytest.mark.asyncio
async def test_get_commission_movements_includes_full_traceability(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    contract, _sponsor = await _setup_contract_ready_to_activate(db, organization_id, actor_user_id)
    await _advance_to_active(db, organization_id, contract, actor_user_id)
    await process_pending_outbox_events(db)

    rows = await admin_ledger.get_commission_movements(db, organization_id=organization_id)
    assert len(rows) == 2  # producer's personal token + sponsor's entrepreneurial difference

    producer_row = next(r for r in rows if r["depth_from_producer"] == 0)
    assert producer_row["contract_id"] == contract.id
    assert producer_row["movement_type"] == "PERSONAL_TOKEN"
    assert producer_row["amount_cents"] == 4000
    assert producer_row["explanation"]  # a real, non-empty human-readable explanation
    assert producer_row["status"] == "ACCRUED"
    assert producer_row["paid_date"] is None

    sponsor_row = next(r for r in rows if r["depth_from_producer"] == 1)
    assert sponsor_row["movement_type"] == "ENTREPRENEURIAL_DIFFERENCE"
    assert sponsor_row["amount_cents"] == 500  # 4500 (S2) - 4000 (S1) already distributed
    assert sponsor_row["rank_at_calculation"] == "S2"


@pytest.mark.asyncio
async def test_get_commission_movements_filters_by_agent_and_status(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    contract, _sponsor = await _setup_contract_ready_to_activate(db, organization_id, actor_user_id)
    await _advance_to_active(db, organization_id, contract, actor_user_id)
    await process_pending_outbox_events(db)

    all_rows = await admin_ledger.get_commission_movements(db, organization_id=organization_id)
    one_agent = all_rows[0]["agent_id"]

    filtered = await admin_ledger.get_commission_movements(db, organization_id=organization_id, agent_id=one_agent)
    assert len(filtered) == 1
    assert filtered[0]["agent_id"] == one_agent

    accrued_only = await admin_ledger.get_commission_movements(db, organization_id=organization_id, status="ACCRUED")
    assert len(accrued_only) == 2
    paid_only = await admin_ledger.get_commission_movements(db, organization_id=organization_id, status="PAID")
    assert len(paid_only) == 0


@pytest.mark.asyncio
async def test_mark_movement_paid_transitions_status_and_is_idempotent_against_double_payment(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    contract, _sponsor = await _setup_contract_ready_to_activate(db, organization_id, actor_user_id)
    await _advance_to_active(db, organization_id, contract, actor_user_id)
    await process_pending_outbox_events(db)

    movement = (await db.execute(select(CommissionMovement).where(CommissionMovement.contract_id == contract.id))).scalars().first()
    assert movement.status == "ACCRUED"
    assert movement.paid_date is None

    paid = await admin_ledger.mark_movement_paid(
        db, organization_id=organization_id, movement_id=movement.id, actor_user_id=actor_user_id, note="Bonifico test"
    )
    assert paid.status == "PAID"
    assert paid.paid_date is not None

    with pytest.raises(admin_ledger.CommissionPaymentError):
        await admin_ledger.mark_movement_paid(
            db, organization_id=organization_id, movement_id=movement.id, actor_user_id=actor_user_id
        )


@pytest.mark.asyncio
async def test_commission_totals_by_level_aggregates_correctly(db, organization_id):
    actor_user_id = await _make_actor(db, organization_id)
    contract, _sponsor = await _setup_contract_ready_to_activate(db, organization_id, actor_user_id)
    await _advance_to_active(db, organization_id, contract, actor_user_id)
    await process_pending_outbox_events(db)

    levels = await admin_ledger.get_commission_totals_by_level(db, organization_id=organization_id)
    by_depth = {row["depth"]: row for row in levels}

    assert by_depth[0]["contracts"] == 1
    assert by_depth[0]["commission_cents"] == 4000
    assert by_depth[0]["value_cents"] == 1000  # the test product's base_price_cents

    assert by_depth[1]["contracts"] == 1
    assert by_depth[1]["commission_cents"] == 500
