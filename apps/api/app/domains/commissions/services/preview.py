"""Anteprima provvigioni: who would be paid what if this contract activated now.

Read-only. It walks the same live ancestor chain `network_service.
create_snapshot_for_contract` would freeze (ACTIVE agents only), prices it with
the same tokens `run_calculation._build_chain` uses (product override first,
rank default second) and the same pure calculator, and spreads it over the
customer's instalments with the same `instalment_share` the engine will use.
Nothing here writes a row: the administrator accepting it is what stores it
(contracts.ContractCommissionPlan), and activation is what pays.

Kept deliberately honest about what it cannot know: if the customer has not
paid yet, the instalment count is unknown, so every possible split is shown;
and if the network changes between acceptance and activation, the real
snapshot wins -- the log shows the accepted preview next to the movements
actually written.
"""

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.catalog import pricing
from app.domains.catalog.models import ProductVersion
from app.domains.commissions.calculators.entrepreneurial_difference import (
    ChainMember,
    calculate_chain,
)
from app.domains.commissions.models import Rank
from app.domains.commissions.services.run_calculation import instalment_share
from app.domains.contracts import payment_plans
from app.domains.contracts.instalments import _add_months
from app.domains.contracts.models import Contract, ContractAttribution
from app.domains.customers.models import Company, Customer, CustomerProfile
from app.domains.network import service as network_service
from app.domains.network.models import AgentProfile

MOVEMENT_LABELS = {
    "PERSONAL_TOKEN": "Gettone personale",
    "ENTREPRENEURIAL_DIFFERENCE": "Differenza imprenditoriale",
    "FIRST_REFERRER_BONUS": "Bonus primo segnalatore",
}


def _role_label(depth: int) -> str:
    if depth == 0:
        return "Promoter del cliente"
    if depth == 1:
        return "Sponsor diretto"
    return f"Sponsor di {depth}° livello"


async def build_commission_preview(db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract) -> dict:
    from app.domains.customers.service import display_name_for

    version = await db.get(ProductVersion, contract.product_version_id)
    attribution = (
        await db.get(ContractAttribution, contract.contract_attribution_id)
        if contract.contract_attribution_id
        else None
    )
    warnings: list[str] = []

    customer = await db.get(Customer, contract.customer_id)
    customer_name = (
        display_name_for(customer.kind, await db.get(CustomerProfile, customer.id), await db.get(Company, customer.id))
        if customer is not None
        else "Cliente"
    )

    beneficiaries: list[dict] = []
    if attribution is None:
        warnings.append("Il contratto non ha un promoter attribuito: nessuna provvigione verrà pagata.")
    else:
        ancestors = await network_service._get_active_ancestors(
            db, organization_id=organization_id, agent_id=attribution.producer_agent_id
        )
        agent_ids = [a for a, _ in ancestors]
        agents = {
            a.id: a
            for a in (await db.execute(select(AgentProfile).where(AgentProfile.id.in_(agent_ids)))).scalars()
        } if agent_ids else {}
        rank_ids = {a.current_rank_id for a in agents.values() if a.current_rank_id}
        ranks = {
            r.id: r for r in (await db.execute(select(Rank).where(Rank.id.in_(rank_ids)))).scalars()
        } if rank_ids else {}
        product_tokens: dict = (version.commission_tokens or {}) if version else {}

        chain: list[ChainMember] = []
        skipped = 0
        for agent_id, depth in sorted(ancestors, key=lambda pair: pair[1]):
            agent = agents.get(agent_id)
            if agent is None or agent.status != "ACTIVE":
                skipped += 1
                continue
            rank = ranks.get(agent.current_rank_id) if agent.current_rank_id else None
            rank_code = rank.code if rank else "UNRANKED"
            chain.append(ChainMember(
                agent_id=str(agent_id),
                rank_code=rank_code,
                personal_token_cents=product_tokens.get(rank_code, rank.personal_token_cents if rank else 0),
                depth=depth,
            ))
            if rank is None:
                warnings.append(f"{agent.display_name} non ha un grado: il suo gettone è 0.")
        if skipped:
            warnings.append(
                f"{skipped} promoter sopra al cliente non sono attivi e sono esclusi dalla catena."
            )
        if not chain:
            warnings.append("Nessun promoter attivo nella catena: nessuna provvigione verrà pagata.")

        for step, member in zip(calculate_chain(chain), chain, strict=True):
            agent = agents[uuid.UUID(step.beneficiary_agent_id)]
            beneficiaries.append({
                "agent_id": step.beneficiary_agent_id,
                "name": agent.display_name,
                "rank_code": step.rank_code,
                "depth": member.depth,
                "role": _role_label(member.depth),
                "movement_type": step.movement_type,
                "movement_label": MOVEMENT_LABELS.get(step.movement_type, step.movement_type),
                "total_cents": step.gross_amount_cents,
                "explanation": step.explanation,
            })

    bonus = None
    if version is not None and version.first_referrer_bonus_enabled and (version.first_referrer_bonus_cents or 0) > 0:
        referrer = (
            await db.get(AgentProfile, contract.first_referrer_agent_id) if contract.first_referrer_agent_id else None
        )
        if referrer is not None and referrer.status == "ACTIVE":
            bonus = {
                "agent_id": str(referrer.id),
                "name": referrer.display_name,
                "amount_cents": int(version.first_referrer_bonus_cents),
                "note": "Una sola volta, intero, insieme alla prima rata.",
            }

    total_commission = sum(b["total_cents"] for b in beneficiaries)
    plan = payment_plans.plan_by_key(contract.payment_plan) if contract.paid_at else None
    if contract.paid_at and plan is None:
        # Paid, but not through a plan (a confirmed bank transfer): one payment.
        plan = payment_plans.plan_by_key(payment_plans.PLAN_FULL)
    gross = int(contract.gross_amount_cents or 0)

    def _schedule(p: payment_plans.PaymentPlan) -> list[dict]:
        start = (contract.paid_at.date() if contract.paid_at else None)
        instalment_cents = payment_plans.breakdown_for(p, gross).instalment_cents if gross else 0
        rows = []
        for n in range(1, p.instalments + 1):
            rows.append({
                "number": n,
                "due_date": _add_months(start, n - 1).isoformat() if start else None,
                "customer_amount_cents": instalment_cents,
                "commission_cents": sum(
                    instalment_share(b["total_cents"], number=n, instalments=p.instalments) for b in beneficiaries
                ),
                "per_beneficiary_cents": {
                    b["agent_id"]: instalment_share(b["total_cents"], number=n, instalments=p.instalments)
                    for b in beneficiaries
                },
                "release": (
                    "Alla tua conferma di questa anteprima" if n == 1
                    else "Quando Stripe conferma l'incasso della rata (o la confermi tu a mano)"
                ),
            })
        return rows

    if plan is not None:
        payment = {
            "paid": True,
            "paid_at": contract.paid_at.isoformat() if contract.paid_at else None,
            "plan_key": plan.key,
            "plan_label": plan.label,
            "instalments": plan.instalments,
            "schedule": _schedule(plan),
            "last_release_date": _schedule(plan)[-1]["due_date"],
            "scenarios": [],
        }
    else:
        warnings.append(
            "Il cliente non ha ancora pagato: accettando, le provvigioni partiranno da sole al primo pagamento, "
            "divise secondo la modalità che sceglierà."
        )
        payment = {
            "paid": False,
            "paid_at": None,
            "plan_key": None,
            "plan_label": None,
            "instalments": None,
            "schedule": [],
            "last_release_date": None,
            "scenarios": [
                {
                    "plan_key": p.key,
                    "plan_label": p.label,
                    "instalments": p.instalments,
                    "commission_per_instalment_cents": sum(
                        instalment_share(b["total_cents"], number=1, instalments=p.instalments) for b in beneficiaries
                    ),
                }
                for p in payment_plans.PAYMENT_PLANS
            ],
        }

    cashback_cents = (
        pricing.contract_cashback_cents(version=version, gross_amount_cents=gross) if version is not None and gross else 0
    )

    body = {
        "contract_id": str(contract.id),
        "customer_name": customer_name,
        "gross_amount_cents": gross,
        "beneficiaries": beneficiaries,
        "first_referrer_bonus": bonus,
        "total_commission_cents": total_commission,
        "payment": payment,
        "customer_cashback_cents": cashback_cents,
    }
    checksum = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return {**body, "warnings": warnings, "checksum": checksum}
