import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, require_permission
from app.domains.contracts import service as contract_service
from app.domains.contracts.models import Contract
from app.domains.contracts.schemas import ContractCreate, ContractRead, ContractTransitionRequest
from app.domains.contracts.state_machine import InvalidTransitionError
from app.domains.customers.models import Customer

router = APIRouter(prefix="/contracts", tags=["contracts"])


async def _get_org_scoped_contract(
    db: AsyncSession, *, organization_id: uuid.UUID, contract_id: uuid.UUID
) -> Contract:
    contract = await db.get(Contract, contract_id)
    if contract is None or contract.organization_id != organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contract not found")
    return contract


@router.post("", response_model=ContractRead, status_code=status.HTTP_201_CREATED)
async def create_contract(
    payload: ContractCreate,
    current_user: CurrentUser = Depends(require_permission("contracts.create")),
    db: AsyncSession = Depends(get_db),
) -> ContractRead:
    contract = await contract_service.create_contract(
        db,
        organization_id=current_user.organization_id,
        customer_id=payload.customer_id,
        supply_point_id=payload.supply_point_id,
        product_version_id=payload.product_version_id,
        producer_agent_id=payload.producer_agent_id,
        actor_user_id=current_user.user_id,
        correlation_id=str(uuid.uuid4()),
    )
    return ContractRead.model_validate(contract)


@router.get("", response_model=list[ContractRead])
async def list_contracts(
    current_user: CurrentUser = Depends(require_permission("contracts.read")),
    db: AsyncSession = Depends(get_db),
    limit: int = 200,
) -> list[ContractRead]:
    stmt = (
        select(Contract)
        .where(Contract.organization_id == current_user.organization_id)
        .order_by(Contract.created_at.desc())
        .limit(limit)
    )
    contracts = (await db.execute(stmt)).scalars().all()
    return [ContractRead.model_validate(c) for c in contracts]


@router.get("/mine", response_model=list[ContractRead])
async def list_my_contracts(
    current_user: CurrentUser = Depends(require_permission("contracts.read")),
    db: AsyncSession = Depends(get_db),
) -> list[ContractRead]:
    """Ownership-scoped view for a customer's own login: never the org-wide list.
    A customer with no linked Customer row (not yet self-service-enabled) simply
    sees an empty list rather than an error."""
    customer_stmt = select(Customer.id).where(
        Customer.organization_id == current_user.organization_id,
        Customer.user_id == current_user.user_id,
    )
    customer_id = (await db.execute(customer_stmt)).scalar_one_or_none()
    if customer_id is None:
        return []

    stmt = (
        select(Contract)
        .where(Contract.organization_id == current_user.organization_id, Contract.customer_id == customer_id)
        .order_by(Contract.created_at.desc())
    )
    contracts = (await db.execute(stmt)).scalars().all()
    return [ContractRead.model_validate(c) for c in contracts]


@router.get("/{contract_id}", response_model=ContractRead)
async def get_contract(
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("contracts.read")),
    db: AsyncSession = Depends(get_db),
) -> ContractRead:
    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    return ContractRead.model_validate(contract)


@router.post("/{contract_id}/transition", response_model=ContractRead)
async def transition_contract(
    contract_id: uuid.UUID,
    payload: ContractTransitionRequest,
    current_user: CurrentUser = Depends(require_permission("contracts.review")),
    db: AsyncSession = Depends(get_db),
) -> ContractRead:
    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    try:
        contract = await contract_service.transition_contract(
            db,
            organization_id=current_user.organization_id,
            contract=contract,
            to_status=payload.to_status,
            actor_user_id=current_user.user_id,
            reason=payload.reason,
            notes=payload.notes,
            correlation_id=str(uuid.uuid4()),
        )
    except InvalidTransitionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ContractRead.model_validate(contract)
