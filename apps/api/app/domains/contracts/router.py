import urllib.parse
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import CurrentUser, get_current_user, require_permission
from app.domains.audit import service as audit_service
from app.domains.catalog import pricing
from app.domains.catalog.models import ProductVersion
from app.domains.contracts import dossier, payment_plans
from app.domains.contracts import service as contract_service
from app.domains.contracts.models import Contract
from app.domains.contracts.schemas import (
    ContractCheckoutRequest,
    ContractCreate,
    ContractForCustomerCreate,
    ContractIbanUpdate,
    ContractPaymentOptionRead,
    ContractPaymentOptionsRead,
    ContractRead,
    ContractSelfServiceCreate,
    ContractStatusHistoryRead,
    ContractTransitionRequest,
)
from app.domains.contracts.service import InvalidProducerAgentError, SelfServiceContractError
from app.domains.contracts.state_machine import InvalidTransitionError
from app.domains.customers.models import Customer
from app.domains.integrations import google_drive
from app.domains.integrations.google_drive import GoogleDriveError
from app.domains.integrations.schemas import DriveUploadResultRead
from app.domains.network import service as network_service
from app.domains.organizations import service as organizations_service
from app.domains.support.service import actor_role_for

router = APIRouter(prefix="/contracts", tags=["contracts"])


async def _get_org_scoped_contract(
    db: AsyncSession, *, organization_id: uuid.UUID, contract_id: uuid.UUID
) -> Contract:
    contract = await db.get(Contract, contract_id)
    if contract is None or contract.organization_id != organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contract not found")
    return contract


async def _assert_own_contract_or_staff(
    db: AsyncSession, *, current_user: CurrentUser, contract: Contract
) -> None:
    if actor_role_for(current_user.roles) != "CUSTOMER":
        return
    customer_stmt = select(Customer.id).where(
        Customer.organization_id == current_user.organization_id, Customer.user_id == current_user.user_id
    )
    own_customer_id = (await db.execute(customer_stmt)).scalar_one_or_none()
    if own_customer_id is None or contract.customer_id != own_customer_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized for this contract")


@router.post("", response_model=ContractRead, status_code=status.HTTP_201_CREATED)
async def create_contract(
    payload: ContractCreate,
    current_user: CurrentUser = Depends(require_permission("contracts.create")),
    db: AsyncSession = Depends(get_db),
) -> ContractRead:
    # Snapshotted from the creator's roles rather than inferred later: the
    # same person can gain or lose a role afterwards, but what they were
    # acting as when they built this contract cannot change. A promoter using
    # this staff endpoint is, by definition, filling a contract in for
    # somebody else -- which is exactly the case the admin screen must be
    # able to call out -- so their own agent id is recorded as the one who
    # did it. Staff get no such marker: an admin-created contract is not
    # "attivato dal promoter X".
    created_by_role = actor_role_for(current_user.roles)
    activated_by_promoter_id = None
    if created_by_role == "PROMOTER":
        own_agent = await network_service.get_own_agent_profile(
            db, organization_id=current_user.organization_id, user_id=current_user.user_id
        )
        activated_by_promoter_id = own_agent.id if own_agent else None

    try:
        contract = await contract_service.create_contract(
            db,
            organization_id=current_user.organization_id,
            customer_id=payload.customer_id,
            supply_point_id=payload.supply_point_id,
            product_version_id=payload.product_version_id,
            producer_agent_id=payload.producer_agent_id,
            actor_user_id=current_user.user_id,
            correlation_id=str(uuid.uuid4()),
            notes=payload.notes,
            iban=payload.iban,
            email=payload.email,
            created_by_role=created_by_role,
            activated_by_promoter_id=activated_by_promoter_id,
        )
    except InvalidProducerAgentError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    rows = await contract_service.to_read_dicts(db, [contract])
    return ContractRead(**rows[0])


@router.post("/mine", response_model=ContractRead, status_code=status.HTTP_201_CREATED)
async def create_my_contract(
    payload: ContractSelfServiceCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractRead:
    """'Attiva Contratto': any authenticated customer can self-activate a Lial
    Energy product -- no contracts.create permission needed, same "self
    checkout, own account only" pattern as POST /orders/mine. Creates the
    supply point and the contract in one call, then immediately advances it
    to DOCUMENTS_PENDING -- see contracts/service.py::create_contract_self_service."""
    try:
        contract = await contract_service.create_contract_self_service(
            db,
            organization_id=current_user.organization_id,
            customer_user_id=current_user.user_id,
            product_version_id=payload.product_version_id,
            supply_point_payload=payload.supply_point,
            email=payload.email,
            holder_first_name=payload.holder_first_name,
            holder_last_name=payload.holder_last_name,
            pec=payload.pec,
            iban=payload.iban,
        )
    except SelfServiceContractError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except InvalidProducerAgentError as exc:
        # Reachable on the self-service path for a reason that is nobody's
        # mistake: the customer's referring promoter has since been
        # deactivated. create_contract() refuses to attribute a contract to a
        # non-ACTIVE agent (otherwise it activates and pays nobody -- see
        # docs/paid-contract-commission-audit.md), but this endpoint used to
        # let that exception escape, so a customer clicking "Continua" got a
        # 500 and the dashboard's generic "Si è verificato un errore
        # imprevisto". A refusal the business understands must never surface
        # as a crash.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    rows = await contract_service.to_read_dicts(db, [contract])
    return ContractRead(**rows[0])


@router.post("/for-customer", response_model=ContractRead, status_code=status.HTTP_201_CREATED)
async def create_contract_for_my_customer(
    payload: ContractForCustomerCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractRead:
    """The CRM-style counterpart to POST /contracts/mine: a promoter
    activates a contract for one of THEIR OWN customers (who may never have
    logged in) instead of a customer activating their own. No permission
    beyond authentication -- any user with an ACTIVE AgentProfile can call
    this, exactly like /contracts/mine works for any authenticated customer;
    ownership of the target customer is enforced inside the service, not
    here (see create_contract_for_recruited_customer's own docstring)."""
    try:
        contract = await contract_service.create_contract_for_recruited_customer(
            db, organization_id=current_user.organization_id, promoter_user_id=current_user.user_id,
            customer_id=payload.customer_id, product_version_id=payload.product_version_id,
            supply_point_payload=payload.supply_point, email=payload.email,
            holder_first_name=payload.holder_first_name, holder_last_name=payload.holder_last_name,
            pec=payload.pec, iban=payload.iban,
        )
    except SelfServiceContractError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except InvalidProducerAgentError as exc:
        # Same reasoning as POST /contracts/mine above.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    rows = await contract_service.to_read_dicts(db, [contract])
    return ContractRead(**rows[0])


@router.get("/mine/{contract_id}/payment-options", response_model=ContractPaymentOptionsRead)
async def get_my_contract_payment_options(
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContractPaymentOptionsRead:
    """How this contract can be paid, priced. Own contract only.

    Every figure is computed here from the amount frozen on the contract --
    the browser is never asked what anything costs, it only picks a plan
    key."""
    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    await _assert_own_contract_or_staff(db, current_user=current_user, contract=contract)

    card_available = await organizations_service.is_stripe_configured(
        db, organization_id=current_user.organization_id
    )
    payable = contract_service.is_payable(contract)
    version = await db.get(ProductVersion, contract.product_version_id) if contract.product_version_id else None
    cashback_percentage = int(version.contract_cashback_percentage or 0) if version is not None else 0
    options = (
        [
            ContractPaymentOptionRead(
                key=b.plan.key, label=b.plan.label, description=b.plan.description,
                instalments=b.plan.instalments, instalment_cents=b.instalment_cents,
                total_cents=b.total_cents, rounding_difference_cents=b.rounding_difference_cents,
            )
            for b in payment_plans.available_breakdowns(contract.gross_amount_cents or 0)
        ]
        if payable
        else []
    )
    return ContractPaymentOptionsRead(
        contract_id=contract.id, payable=payable, status=contract.status,
        missing_amount=contract.status in contract_service.PREPAYABLE_STATUSES and not contract.gross_amount_cents,
        gross_amount_cents=contract.gross_amount_cents, card_available=card_available,
        options=options, paid_at=contract.paid_at, payment_plan=contract.payment_plan,
        cashback_percentage=cashback_percentage,
        cashback_total_cents=(
            pricing.contract_cashback_cents(version=version, gross_amount_cents=contract.gross_amount_cents)
            if version is not None and contract.gross_amount_cents
            else 0
        ),
    )


@router.post("/mine/{contract_id}/checkout-session")
async def create_my_contract_checkout_session(
    contract_id: uuid.UUID,
    payload: ContractCheckoutRequest,
    success_url: str,
    cancel_url: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Opens Stripe Checkout for one's own contract -- before or after the
    documents are approved (contracts/service.py::PREPAYABLE_STATUSES). Returns the URL; the contract
    is NOT marked paid here -- only the verified webhook does that."""
    from app.domains.payments import service as payments_service

    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    await _assert_own_contract_or_staff(db, current_user=current_user, contract=contract)
    if contract.paid_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Questo contratto risulta già pagato.")
    if not contract_service.is_payable(contract):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Questo contratto non si può pagare in questo stato.")

    try:
        url = await payments_service.create_checkout_session_for_contract(
            db, organization_id=current_user.organization_id, contract=contract,
            plan_key=payload.payment_plan, success_url=success_url, cancel_url=cancel_url,
        )
    except payments_service.StripeNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except payments_service.PaymentsError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"checkout_url": url}


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
    rows = await contract_service.to_read_dicts(db, list(contracts))
    return [ContractRead(**row) for row in rows]


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
    rows = await contract_service.to_read_dicts(db, list(contracts))
    return [ContractRead(**row) for row in rows]


@router.get("/{contract_id}", response_model=ContractRead)
async def get_contract(
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("contracts.read")),
    db: AsyncSession = Depends(get_db),
) -> ContractRead:
    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    rows = await contract_service.to_read_dicts(db, [contract])
    return ContractRead(**rows[0])


@router.get("/{contract_id}/status-history", response_model=list[ContractStatusHistoryRead])
async def get_contract_status_history(
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("contracts.read")),
    db: AsyncSession = Depends(get_db),
) -> list[ContractStatusHistoryRead]:
    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    await _assert_own_contract_or_staff(db, current_user=current_user, contract=contract)
    rows = await contract_service.get_status_history(db, contract_id=contract_id)
    return [ContractStatusHistoryRead(**row) for row in rows]


@router.patch("/{contract_id}/iban", response_model=ContractRead)
async def update_contract_iban(
    contract_id: uuid.UUID,
    payload: ContractIbanUpdate,
    current_user: CurrentUser = Depends(require_permission("contracts.read")),
    db: AsyncSession = Depends(get_db),
) -> ContractRead:
    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    await _assert_own_contract_or_staff(db, current_user=current_user, contract=contract)
    contract = await contract_service.set_contract_iban(
        db, organization_id=current_user.organization_id, contract=contract,
        iban=payload.iban, actor_user_id=current_user.user_id,
    )
    rows = await contract_service.to_read_dicts(db, [contract])
    return ContractRead(**rows[0])


#: Targets on the road to a contract's FIRST activation. Reaching any of them
#: can end in ACTIVE through the auto-cascade (an already-paid contract goes
#: straight from APPROVED to ACTIVE), which is where commissions are paid --
#: so none of them is allowed until the administrator has accepted the
#: commission preview. Reactivating a SUSPENDED contract is not a first
#: activation and pays nothing, so it is not gated.
_ACTIVATION_PATH_TARGETS = frozenset({"APPROVED", "PAYMENT_PENDING", "PAID", "ACTIVATION_PENDING", "ACTIVE"})


@router.get("/{contract_id}/commission-preview")
async def get_commission_preview(
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("contracts.review")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Who would be paid what, and when, if this contract activated now.
    Read-only -- see commissions/services/preview.py."""
    from app.domains.commissions.services.preview import build_commission_preview

    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    if contract.product_version_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Questo punto non ha ancora un pacchetto: non ci sono provvigioni da mostrare."
        )
    preview = await build_commission_preview(db, organization_id=current_user.organization_id, contract=contract)
    preview["already_accepted"] = await contract_service.has_accepted_commission_plan(db, contract_id=contract.id)
    return preview


@router.get("/{contract_id}/commission-log")
async def get_commission_log(
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("contracts.review")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The accepted preview, the instalment schedule with what each one has
    released, and the commission movements actually written -- side by side,
    so an administrator can check later that what happened is what they
    approved."""
    from app.domains.commissions.services import admin_ledger
    from app.domains.contracts import instalments as instalments_service
    from app.domains.contracts.models import ContractCommissionPlan
    from app.domains.users.models import User

    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    plan = (
        await db.execute(select(ContractCommissionPlan).where(ContractCommissionPlan.contract_id == contract.id))
    ).scalar_one_or_none()
    accepted_by = await db.get(User, plan.accepted_by_user_id) if plan is not None else None
    rows = await instalments_service.list_instalments(db, contract_id=contract.id)
    confirmer_ids = {r.confirmed_by_user_id for r in rows if r.confirmed_by_user_id}
    confirmers = {
        u.id: u.email for u in (await db.execute(select(User).where(User.id.in_(confirmer_ids)))).scalars()
    } if confirmer_ids else {}
    movements = await admin_ledger.get_commission_movements(
        db, organization_id=current_user.organization_id, contract_id=contract.id
    )
    return {
        "contract_id": str(contract.id),
        "status": contract.status,
        "payment_plan": contract.payment_plan,
        "accepted_plan": (
            {
                "accepted_at": plan.accepted_at.isoformat(),
                "accepted_by": accepted_by.email if accepted_by else None,
                "total_commission_cents": plan.total_commission_cents,
                "preview": plan.preview,
            }
            if plan is not None
            else None
        ),
        "instalments": [
            {
                "number": r.number,
                "instalments_total": r.instalments_total,
                "due_date": r.due_date.isoformat(),
                "amount_cents": r.amount_cents,
                "status": r.status,
                "paid_at": r.paid_at.isoformat() if r.paid_at else None,
                "payment_source": r.payment_source,
                "confirmed_by": confirmers.get(r.confirmed_by_user_id) if r.confirmed_by_user_id else None,
                "commission_released_at": r.commission_released_at.isoformat() if r.commission_released_at else None,
                "commission_pending": r.commission_event_id is not None and r.commission_released_at is None,
            }
            for r in rows
        ],
        "movements": [
            {
                "id": str(m["id"]),
                "agent_name": m["agent_name"],
                "movement_type": m["movement_type"],
                "amount_cents": m["amount_cents"],
                "status": m["status"],
                "explanation": m["explanation"],
                "effective_date": m["effective_date"].isoformat(),
            }
            for m in movements
        ],
    }


@router.post("/{contract_id}/instalments/{number}/confirm")
async def confirm_instalment_manually(
    contract_id: uuid.UUID,
    number: int,
    current_user: CurrentUser = Depends(require_permission("contracts.review")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Staff confirming an instalment Stripe did not collect. On an active
    contract it releases that instalment's commissions."""
    from app.domains.contracts import instalments as instalments_service

    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    try:
        row = await instalments_service.confirm_manually(
            db, contract=contract, number=number, actor_user_id=current_user.user_id
        )
    except instalments_service.InstalmentError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await audit_service.record(
        db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
        action="contract.instalment_confirmed_manually", entity_type="contract", entity_id=str(contract.id),
        new_value={"instalment_number": number},
    )
    await db.commit()
    return {"number": row.number, "status": row.status}


@router.post("/{contract_id}/stop-billing", response_model=ContractRead)
async def stop_contract_billing(
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("contracts.review")),
    db: AsyncSession = Depends(get_db),
) -> ContractRead:
    """"Interrompi addebiti": Stripe stops charging this contract every month.
    In a pratica only this contract's line leaves the subscription."""
    from app.domains.payments import service as payments_service

    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    try:
        contract = await payments_service.stop_contract_billing(
            db, organization_id=current_user.organization_id, contract=contract, actor_user_id=current_user.user_id
        )
    except payments_service.StripeNotConfiguredError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except payments_service.PaymentsError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    rows = await contract_service.to_read_dicts(db, [contract])
    return ContractRead(**rows[0])


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
    if (
        payload.to_status in _ACTIVATION_PATH_TARGETS
        and contract.activated_at is None
        and contract.status != "SUSPENDED"
        and not await contract_service.has_accepted_commission_plan(db, contract_id=contract.id)
    ):
        if not payload.accept_commission_preview_checksum:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Prima di approvare devi controllare e accettare l'anteprima delle provvigioni.",
            )
        try:
            await contract_service.accept_commission_plan(
                db, organization_id=current_user.organization_id, contract=contract,
                checksum=payload.accept_commission_preview_checksum, actor_user_id=current_user.user_id,
            )
        except contract_service.CommissionPreviewChangedError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
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
    rows = await contract_service.to_read_dicts(db, [contract])
    return ContractRead(**rows[0])


@router.get("/{contract_id}/dossier.zip")
async def download_contract_dossier(
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("documents.review")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Tutti gli allegati del contratto più un PDF riassuntivo, in un solo
    zip chiamato `<nome cliente>-<id contratto>.zip`.

    Dietro `documents.review` e non `documents.download`: quest'ultimo ce
    l'ha anche il cliente per i propri documenti, mentre qui si scarica
    l'intero fascicolo di una pratica -- anagrafica, IBAN, riferimenti di
    pagamento -- ed è roba da amministrazione, esattamente le stesse persone
    che quei documenti li verificano una per una.

    Lo zip si costruisce tutto in memoria: un fascicolo sono cinque o sei
    file da qualche MB, e un file temporaneo su disco sarebbe una copia in
    chiaro di documenti d'identità da ricordarsi di cancellare."""
    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    built = await dossier.build_dossier(
        db, organization_id=current_user.organization_id, contract=contract
    )
    await audit_service.record(
        db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
        action="contract.dossier_downloaded", entity_type="contract", entity_id=str(contract_id),
        new_value={"files": len(built.files), "archive": built.zip_filename},
    )
    await db.commit()

    content = dossier.zip_bytes(built)
    # Due volte il nome: `filename=` con i soli ASCII per i client vecchi,
    # `filename*=` con la versione UTF-8 per tutti gli altri. Senza il
    # secondo, "Bàrbara Rossi-....zip" arriva storpiato.
    ascii_name = built.zip_filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    quoted = urllib.parse.quote(built.zip_filename)
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted}',
            "Content-Length": str(len(content)),
        },
    )


@router.post("/{contract_id}/dossier/drive", response_model=DriveUploadResultRead)
async def send_contract_dossier_to_drive(
    contract_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("documents.review")),
    db: AsyncSession = Depends(get_db),
) -> DriveUploadResultRead:
    """Lo stesso fascicolo dello zip, in una cartella Google Drive chiamata
    `<nome cliente>-<id contratto>`. Stesso contenuto perché lo costruisce
    lo stesso modulo: le due strade non possono divergere."""
    contract = await _get_org_scoped_contract(
        db, organization_id=current_user.organization_id, contract_id=contract_id
    )
    built = await dossier.build_dossier(
        db, organization_id=current_user.organization_id, contract=contract
    )
    try:
        result = await google_drive.upload_dossier(
            db, organization_id=current_user.organization_id, dossier=built
        )
    except GoogleDriveError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    await audit_service.record(
        db, organization_id=current_user.organization_id, actor_user_id=current_user.user_id,
        action="contract.dossier_sent_to_drive", entity_type="contract", entity_id=str(contract_id),
        new_value={"folder": result.folder_name, "uploaded": result.uploaded, "replaced": result.replaced},
    )
    await db.commit()

    return DriveUploadResultRead(
        folder_name=result.folder_name,
        folder_url=result.folder_url,
        uploaded=result.uploaded,
        replaced=result.replaced,
    )
