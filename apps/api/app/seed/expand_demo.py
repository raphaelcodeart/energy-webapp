"""Additive demo-data expansion, run ONCE against the EXISTING live "Lial Energy
Demo" organization (ORG_ID below) -- NOT a fresh org, unlike seed/data.py. Adds:

  - ~30 more network agents, broadening the existing 41-agent/12-level tree
    (which was two thin thin single-file chains reaching depth 12) so the
    sales-network view actually renders as a full, branching tree at every
    depth instead of a couple of bare threads.
  - ~50 more customers with contracts spread across the whole tree (old and
    new agents alike) in a realistic mix of statuses -- including
    DOCUMENTS_PENDING contracts with zero or partially-uploaded documents, to
    demonstrate the "missing documentation" review flow end-to-end.

Every row this script creates is tagged for easy identification/removal
before going to production:
  - agent promoter_code starts with "DEMO-"
  - customer email domain is "@demo-expansion.lial"
  - contract notes contain the literal string "[DEMO-EXPANSION]"
See docs/server-migration-guide.md "Rimuovere i dati demo" for the delete
queries keyed off these markers. Safe to re-run only after deleting its own
output first -- it does not check for prior runs.
"""

import asyncio
import itertools
import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.db import AsyncSessionLocal

# Every domain's models must be imported before any mapper configures (e.g. the
# first db.flush() below) -- SQLAlchemy resolves FK target tables lazily across
# the whole mapper registry, not just the modules this file happens to import
# directly. main.py normally does this via its own router imports; this script
# has no such entrypoint, so it must import them explicitly (same pattern as
# tests/conftest.py).
from app.domains.audit import models as _audit_models  # noqa: F401
from app.domains.auth import models as _auth_models  # noqa: F401
from app.domains.catalog.models import Product, ProductVersion
from app.domains.commissions import models as _commissions_models  # noqa: F401
from app.domains.commissions.models import Rank
from app.domains.commissions.tasks.dispatch import process_pending_outbox_events
from app.domains.contracts import models as _contracts_models  # noqa: F401
from app.domains.contracts import service as contract_service
from app.domains.customers import models as _customers_models  # noqa: F401
from app.domains.customers import service as customer_service
from app.domains.customers.schemas import CustomerCreate, SupplyPointCreate
from app.domains.documents import models as _documents_models  # noqa: F401
from app.domains.documents import service as documents_service
from app.domains.network import models as _network_models  # noqa: F401
from app.domains.network import service as network_service
from app.domains.network.models import AgentProfile
from app.domains.organizations import models as _organizations_models  # noqa: F401
from app.domains.outbox import models as _outbox_models  # noqa: F401
from app.domains.rbac import models as _rbac_models  # noqa: F401
from app.domains.referral import models as _referral_models  # noqa: F401
from app.domains.referral.models import PromoterCode
from app.domains.support import models as _support_models  # noqa: F401
from app.domains.users import models as _users_models  # noqa: F401
from app.domains.users.models import User

ORG_ID = uuid.UUID("0b0b6a89-e09d-4581-80cd-e8457f287b9e")
ANCHOR = datetime(2026, 7, 26, tzinfo=UTC)
RNG = random.Random(42)

# agent_id -> variable name, taken from the live tree dump (see chat history /
# implementation-progress.md for how this was read out of network_nodes).
EXISTING = {
    "root_a": uuid.UUID("b94a6a89-bbcd-42a6-8ec3-7427828fac85"),
    "root_b": uuid.UUID("47667260-49e3-4669-a851-c5b4a8b3d777"),
    "luca_ferrari": uuid.UUID("490a26dc-f8a2-420e-905b-5724a34045fc"),
    "matteo_de_luca": uuid.UUID("7286fb5c-b158-4aeb-823b-a5b270713978"),
    "elena_greco": uuid.UUID("e3bba79c-d812-478f-a297-9921c7bc831f"),
    "giulia_romano": uuid.UUID("67a071af-28bd-4c20-8ff8-6b6d13d2264f"),
    "marco_colombo": uuid.UUID("bc8de695-2480-4034-8afa-3873dd5eef16"),
    "chiara_gallo": uuid.UUID("4555a4a7-fa9d-4a2e-a1ba-3141c4b827c1"),
    "sara_ricci": uuid.UUID("e4f54c59-6fb8-4066-9d7c-7dcfb7e9817e"),
    "beatrice_villa": uuid.UUID("bcdd5f93-0260-4b46-901e-297e3a437df3"),
    "davide_marino": uuid.UUID("13c9c339-7fbe-4f06-9ee4-b046d0253beb"),
    "giorgia_leone": uuid.UUID("93840c46-55f6-42ef-bf0f-c4e6ea713f69"),
    "elisa_testa": uuid.UUID("5ea0ec08-3051-4744-ae02-f02e292f6184"),
    "michele_grassi": uuid.UUID("de930a0d-4fcc-495b-8d43-8d09efb724e8"),
    "lorenzo_bruni": uuid.UUID("99cb1cec-95a9-40f1-b99b-0e520f32f07b"),
    "sofia_ferraro": uuid.UUID("9b378b3e-0bc3-435c-8f89-0c1296a1cbb0"),
    "alice_pellegrino": uuid.UUID("6b2b7b4a-55f2-46a3-9aa7-7900cb8303a2"),
    "gabriele_vitale": uuid.UUID("6c658aef-7f3f-40f4-9351-0907041cacb1"),
    "emanuele_neri": uuid.UUID("ab4b2e11-96f0-48c9-8beb-5177bbb72c95"),
    "ilaria_sanna": uuid.UUID("fd61bb5a-912c-4f48-b111-10996341fbab"),
    "nicolo_silvestri": uuid.UUID("1aaad11b-7a60-4a49-af40-38e098ab2831"),
    "veronica_rinaldi": uuid.UUID("2c062bf1-8c33-4df8-9e72-adbf1fcb8e1f"),
}

# (display_name, rank_code, parent_key, promoter_code) -- parent_key is either
# a key into EXISTING or a key into the new-agents dict being built below
# (resolved in a second pass since python dicts preserve insertion order).
NEW_AGENTS_PLAN = [
    # Group 1: two brand-new root branches, 2 levels deep each -- gives the
    # tree more top-level breadth, not just depth.
    ("Federico Longo", "MD2", None, "DEMO-MD2-C00"),
    ("Ombretta Serra", "MD2", None, "DEMO-MD2-D00"),
    ("Giacomo Villani", "TL2", "Federico Longo", "DEMO-TL2-C01"),
    ("Aurora Fabbri", "TL2", "Federico Longo", "DEMO-TL2-C02"),
    ("Leonardo Grasso", "TL2", "Ombretta Serra", "DEMO-TL2-D01"),
    ("Bianca Rinaldi", "TL2", "Ombretta Serra", "DEMO-TL2-D02"),
    ("Tommaso Riva", "S3", "Giacomo Villani", "DEMO-S3-C01A"),
    ("Ginevra Moro", "S3", "Aurora Fabbri", "DEMO-S3-C02A"),
    ("Edoardo Pace", "S3", "Leonardo Grasso", "DEMO-S3-D01A"),
    ("Camilla Sorrentino", "S3", "Bianca Rinaldi", "DEMO-S3-D02A"),
    # Group 2: one extra sibling child under 10 existing mid-tree nodes
    # (depths 1-7), broadening the middle of the tree.
    ("Serena Bassi", "S3", "__existing__luca_ferrari", "DEMO-S3-E01"),
    ("Cristian Fabbri", "S3", "__existing__matteo_de_luca", "DEMO-S3-E02"),
    ("Denise Orlando", "S2", "__existing__elena_greco", "DEMO-S2-E03"),
    ("Manuel Costantini", "S2", "__existing__giulia_romano", "DEMO-S2-E04"),
    ("Ivan Palumbo", "S2", "__existing__marco_colombo", "DEMO-S2-E05"),
    ("Rebecca Marini", "S2", "__existing__chiara_gallo", "DEMO-S2-E06"),
    ("Kevin De Santis", "S1", "__existing__sara_ricci", "DEMO-S1-E07"),
    ("Jessica Bellini", "S1", "__existing__beatrice_villa", "DEMO-S1-E08"),
    ("Samuele Gatti", "S1", "__existing__davide_marino", "DEMO-S1-E09"),
    ("Noemi Barone", "S1", "__existing__giorgia_leone", "DEMO-S1-E10"),
    # Group 3: extra sibling children deep in the tree (depths 7-11), so
    # depths 8-12 gain breadth too, not just the original two lone chains.
    ("Riccardo Testa Jr", "S1", "__existing__elisa_testa", "DEMO-S1-F01"),
    ("Vittoria Grassi", "S1", "__existing__michele_grassi", "DEMO-S1-F02"),
    ("Nicole Bruni", "S1", "__existing__lorenzo_bruni", "DEMO-S1-F03"),
    ("Diego Ferraro", "S1", "__existing__sofia_ferraro", "DEMO-S1-F04"),
    ("Tania Pellegrino", "S1", "__existing__alice_pellegrino", "DEMO-S1-F05"),
    ("Omar Vitale", "S1", "__existing__gabriele_vitale", "DEMO-S1-F06"),
    ("Greta Neri", "S1", "__existing__emanuele_neri", "DEMO-S1-F07"),
    ("Filippo Sanna", "S1", "__existing__ilaria_sanna", "DEMO-S1-F08"),
    ("Asia Silvestri", "S1", "__existing__nicolo_silvestri", "DEMO-S1-F09"),
    ("Cristiano Rinaldi", "S1", "__existing__veronica_rinaldi", "DEMO-S1-F10"),
]

FIRST_NAMES = [
    "Giovanni", "Martina", "Alessio", "Chiara", "Riccardo", "Beatrice", "Tommaso", "Alessia",
    "Gabriele", "Ludovica", "Antonio", "Rebecca", "Salvatore", "Camilla", "Vincenzo", "Sofia",
    "Emanuele", "Giorgia", "Raffaele", "Arianna", "Cristian", "Vittoria", "Massimo", "Elisa",
    "Pietro", "Alice", "Gianluca", "Noemi", "Filippo", "Greta", "Michele", "Asia", "Leonardo",
    "Ginevra", "Edoardo", "Aurora", "Manuel", "Denise", "Ivan", "Serena",
]
LAST_NAMES = [
    "Fontana", "Bruno", "Ferrara", "Marchetti", "Santoro", "Mariani", "Rinaldi", "Caruso",
    "Ferretti", "Gatti", "Serra", "Villani", "Longo", "Sorrentino", "Palumbo", "Barone",
    "De Angelis", "Pellegrini", "Testa", "Grasso", "Basile", "Farina", "Neri", "Sanna",
]
COMPANY_NAMES = [
    "Verde Energia Srl", "Sole Impianti Snc", "Ecoluce Distribuzione Srl", "Termica Nova Spa",
    "Bio Power Italia Srl", "Fonti Rinnovabili del Sud Srl", "Elettra Servizi Srl",
]
CITIES = [
    ("Milano", "MI", "20100"), ("Torino", "TO", "10100"), ("Bologna", "BO", "40100"),
    ("Firenze", "FI", "50100"), ("Roma", "RM", "00100"), ("Napoli", "NA", "80100"),
    ("Bari", "BA", "70100"), ("Padova", "PD", "35100"), ("Verona", "VR", "37100"),
    ("Bergamo", "BG", "24100"),
]

STATUS_PLAN = (
    ["ACTIVE"] * 18
    + ["DOCUMENTS_PENDING"] * 10
    + ["UNDER_REVIEW"] * 6
    + ["SUBMITTED"] * 6
    + ["DRAFT"] * 5
    + ["REJECTED"] * 3
    + ["CANCELLED"] * 2
)
assert len(STATUS_PLAN) == 50


async def _advance_to(db, *, contract, org_id, actor_user_id, target_status: str):
    if target_status == "DRAFT":
        return contract
    path_for_target = {
        "SUBMITTED": ["SUBMITTED"],
        "DOCUMENTS_PENDING": ["SUBMITTED", "DOCUMENTS_PENDING"],
        "UNDER_REVIEW": ["SUBMITTED", "UNDER_REVIEW"],
        "REJECTED": ["SUBMITTED", "REJECTED"],
        "ACTIVE": ["SUBMITTED", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING", "PAID", "ACTIVATION_PENDING", "ACTIVE"],
        "CANCELLED": [
            "SUBMITTED", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING", "PAID",
            "ACTIVATION_PENDING", "ACTIVE", "CANCELLED",
        ],
    }[target_status]
    for step in path_for_target:
        contract = await contract_service.transition_contract(
            db, organization_id=org_id, contract=contract, to_status=step,
            actor_user_id=actor_user_id, reason="[DEMO-EXPANSION] avanzamento dimostrativo",
            notes="[DEMO-EXPANSION]" if step != "DOCUMENTS_PENDING" else
                  "[DEMO-EXPANSION] In attesa che il cliente completi la documentazione richiesta.",
            correlation_id=str(uuid.uuid4()),
        )
    return contract


async def run() -> None:
    async with AsyncSessionLocal() as db:
        admin = (await db.execute(select(User).where(User.organization_id == ORG_ID, User.email == "admin@lialenergy.demo"))).scalar_one()
        ranks = {r.code: r for r in (await db.execute(select(Rank).where(Rank.organization_id == ORG_ID))).scalars()}
        product_versions = list(
            (await db.execute(
                select(ProductVersion).join(Product, Product.id == ProductVersion.product_id)
                .where(Product.organization_id == ORG_ID)
            )).scalars()
        )
        if not product_versions:
            raise RuntimeError("No product versions found for this organization -- run seed/data.py first.")

        # --- 1. Expand the network tree ---
        resolved: dict[str, uuid.UUID] = {}
        new_agent_ids: list[uuid.UUID] = []
        for display_name, rank_code, parent_key, promoter_code in NEW_AGENTS_PLAN:
            if parent_key is None:
                parent_id = None
            elif parent_key.startswith("__existing__"):
                parent_id = EXISTING[parent_key.removeprefix("__existing__")]
            else:
                parent_id = resolved[parent_key]

            first_name, last_name = display_name.split(" ", 1)
            agent = await network_service.create_agent(
                db, organization_id=ORG_ID, first_name=first_name, last_name=last_name, promoter_code=promoter_code,
                parent_agent_id=parent_id, joined_at=ANCHOR - timedelta(days=RNG.randint(10, 300)),
                actor_user_id=admin.id, current_rank_id=ranks[rank_code].id,
            )
            db.add(PromoterCode(
                organization_id=ORG_ID, agent_id=agent.id, code=promoter_code,
                personal_link=f"https://lialenergy.demo/r/{promoter_code}", status="ACTIVE",
                valid_from=ANCHOR - timedelta(days=RNG.randint(10, 300)),
            ))
            await db.commit()
            resolved[display_name] = agent.id
            new_agent_ids.append(agent.id)

        print(f"Created {len(new_agent_ids)} new network agents.")

        # Full pool (old + new) so contracts/commissions land across the whole
        # tree, not just the freshly-added branches.
        all_agents = list(
            (await db.execute(
                select(AgentProfile.id).where(AgentProfile.organization_id == ORG_ID, AgentProfile.status == "ACTIVE")
            )).scalars()
        )
        agent_cycle = itertools.cycle(RNG.sample(all_agents, len(all_agents)))
        product_cycle = itertools.cycle(product_versions)
        first_name_cycle = itertools.cycle(FIRST_NAMES)
        last_name_cycle = itertools.cycle(LAST_NAMES)
        company_cycle = itertools.cycle(COMPANY_NAMES)
        city_cycle = itertools.cycle(CITIES)

        # --- 2. Expand customers + contracts ---
        created_contracts = 0
        for i, target_status in enumerate(STATUS_PLAN):
            kind = ["PRIVATE", "PRIVATE", "SOLE_PROPRIETOR", "COMPANY"][i % 4]
            first, last = next(first_name_cycle), next(last_name_cycle)
            city, province, postal = next(city_cycle)
            email = f"{first.lower()}.{last.lower().replace(' ', '')}{i}@demo-expansion.lial"

            payload_kwargs = dict(
                kind=kind, email=email, phone=f"+39 3{RNG.randint(10,99)}{RNG.randint(1000000,9999999)}",
                fiscal_code=None, vat_number=None,
            )
            if kind in ("PRIVATE", "SOLE_PROPRIETOR"):
                payload_kwargs.update(first_name=first, last_name=last)
                if kind == "SOLE_PROPRIETOR":
                    payload_kwargs["vat_number"] = f"IT{RNG.randint(10**10, 10**11 - 1)}"
            else:
                payload_kwargs.update(company_name=f"{next(company_cycle)} {i}")
                payload_kwargs["vat_number"] = f"IT{RNG.randint(10**10, 10**11 - 1)}"

            customer = await customer_service.create_customer(
                db, organization_id=ORG_ID, payload=CustomerCreate(**payload_kwargs), actor_user_id=admin.id,
            )

            energy_type = "ELECTRICITY" if i % 3 != 0 else "GAS"
            supply_point = await customer_service.add_supply_point(
                db, organization_id=ORG_ID, customer_id=customer.id, actor_user_id=admin.id,
                payload=SupplyPointCreate(
                    energy_type=energy_type, street=f"Via Demo Expansion {i+1}", city=city,
                    province=province, postal_code=postal, country="IT",
                ),
            )

            producer_agent_id = next(agent_cycle)
            contract = await contract_service.create_contract(
                db, organization_id=ORG_ID, customer_id=customer.id, supply_point_id=supply_point.id,
                product_version_id=next(product_cycle).id, producer_agent_id=producer_agent_id,
                actor_user_id=admin.id, correlation_id=str(uuid.uuid4()),
                notes="[DEMO-EXPANSION] contenuto dimostrativo, da rimuovere prima della produzione.",
            )
            contract = await _advance_to(db, contract=contract, org_id=ORG_ID, actor_user_id=admin.id, target_status=target_status)

            required_types = documents_service.required_document_types_for(kind)
            if target_status == "DOCUMENTS_PENDING":
                # Half get a partial upload (one doc submitted, still missing
                # the rest -- exactly the "manca documentazione" case); half
                # get none at all yet.
                if i % 2 == 0:
                    doc = await documents_service.upload_document(
                        db, organization_id=ORG_ID, contract_id=contract.id, document_type=required_types[0],
                        file_bytes=b"[DEMO-EXPANSION] fake scanned document bytes",
                        content_type="application/pdf", original_filename="documento_demo.pdf",
                        actor_user_id=admin.id, actor_role="ADMIN",
                    )
            elif target_status in ("UNDER_REVIEW", "ACTIVE", "CANCELLED"):
                for doc_type in required_types:
                    doc = await documents_service.upload_document(
                        db, organization_id=ORG_ID, contract_id=contract.id, document_type=doc_type,
                        file_bytes=b"[DEMO-EXPANSION] fake scanned document bytes",
                        content_type="application/pdf", original_filename=f"{doc_type.lower()}_demo.pdf",
                        actor_user_id=admin.id, actor_role="ADMIN",
                    )
                    await documents_service.review_document(
                        db, organization_id=ORG_ID, document_id=doc.id, new_status="APPROVED",
                        review_note="[DEMO-EXPANSION] documento verificato.", actor_user_id=admin.id,
                    )

            created_contracts += 1

        print(f"Created {created_contracts} new customers + contracts.")

        processed = await process_pending_outbox_events(db)
        print(f"Processed {processed} outbox event(s) -> commissions generated for newly-ACTIVE contracts.")


if __name__ == "__main__":
    asyncio.run(run())
