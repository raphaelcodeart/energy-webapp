"""Non-real demo data: one organization, RBAC bootstrap, a 20-agent / 6-level-deep
commercial network with two parallel top-level branches (to demonstrate isolation),
products, customers of every kind, contracts across every status, and the
commissions those activations generate. See docs/implementation-progress.md."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.core.security import hash_password
from app.domains.catalog.models import Product, ProductVersion
from app.domains.commissions.models import CommissionPlanVersion, Rank
from app.domains.commissions.tasks.dispatch import process_pending_outbox_events
from app.domains.contracts import service as contract_service
from app.domains.customers.models import Address, Customer, CustomerProfile, SupplyPoint
from app.domains.network import service as network_service
from app.domains.organizations.models import Organization
from app.domains.rbac.models import (
    DEFAULT_ROLE_PERMISSIONS,
    PERMISSIONS,
    SYSTEM_ROLES,
    Permission,
    Role,
    RolePermission,
    UserRole,
)
from app.domains.referral.models import PromoterCode
from app.domains.users.models import User
from app.seed.ranks import RANK_SEED, RULE_VERSION

FIXED_NOW = datetime(2026, 7, 25, tzinfo=UTC)

# Placeholder per-rank gettone (personal token) ladder for the two commercial
# formulas the client actually sells -- "Standard" and "Energia Circolare" --
# see docs/business-rules.md#commission-per-product-tokens. Only S1/S2/TL1/MD5
# come from the client's own worked example (40/45/50/80 EUR for Standard,
# exactly double -- 80/90/100/160 EUR -- for Energia Circolare); every other
# rank is linearly interpolated between those anchors and MUST be reviewed/
# adjusted by the client via the product edit screen before this goes live.
STANDARD_TOKENS_CENTS = {
    "S1": 4000, "S2": 4500, "S3": 4750,
    "TL1": 5000, "TL2": 5375, "TL3": 5750, "TL4": 6125,
    "MD1": 6500, "MD2": 6875, "MD3": 7250, "MD4": 7625, "MD5": 8000,
}
CIRCULAR_TOKENS_CENTS = {code: cents * 2 for code, cents in STANDARD_TOKENS_CENTS.items()}


async def run() -> None:
    async with AsyncSessionLocal() as db:
        org = Organization(name="Lial Energy Demo", legal_name="Lial Energy S.r.l. (demo)", status="ACTIVE")
        db.add(org)
        await db.flush()
        org_id = org.id

        # permissions has no organization_id -- it's a single global catalog shared
        # by every org, and data migrations (e.g. 0011, 0012, 0013) already insert
        # some codes into it (idempotently, via ON CONFLICT DO NOTHING) before this
        # script ever runs. Look up what's already there first so re-seeding a
        # migrated database doesn't crash on a duplicate-code UniqueViolation.
        existing_permissions = (
            await db.execute(select(Permission).where(Permission.code.in_(PERMISSIONS)))
        ).scalars().all()
        permissions_by_code: dict[str, Permission] = {p.code: p for p in existing_permissions}
        for code in PERMISSIONS:
            if code not in permissions_by_code:
                perm = Permission(code=code, description="")
                db.add(perm)
                permissions_by_code[code] = perm
        await db.flush()

        roles_by_code: dict[str, Role] = {}
        for code in SYSTEM_ROLES:
            role = Role(organization_id=org_id, code=code, name=code.replace("_", " ").title())
            db.add(role)
            roles_by_code[code] = role
        await db.flush()

        for role_code, granted_codes in DEFAULT_ROLE_PERMISSIONS.items():
            role = roles_by_code[role_code]
            for perm_code in granted_codes:
                db.add(RolePermission(role_id=role.id, permission_id=permissions_by_code[perm_code].id))
        await db.flush()

        ranks_by_code: dict[str, Rank] = {}
        for r in RANK_SEED:
            rank = Rank(
                organization_id=org_id,
                code=r["code"],
                name=r["name"],
                level=r["level"],
                personal_token_cents=r["personal_token_cents"],
                personal_volume_threshold_cents=r["personal_volume_threshold_cents"],
                group_volume_threshold_cents=r["group_volume_threshold_cents"],
                valid_from=FIXED_NOW,
                rule_version=RULE_VERSION,
            )
            db.add(rank)
            ranks_by_code[r["code"]] = rank
        await db.flush()

        plan_version = CommissionPlanVersion(
            organization_id=org_id, version_label=RULE_VERSION, valid_from=FIXED_NOW, status="ACTIVE"
        )
        db.add(plan_version)
        await db.flush()

        def make_user(email: str, password: str, role_codes: list[str]) -> User:
            user = User(
                organization_id=org_id,
                email=email,
                password_hash=hash_password(password),
                status="ACTIVE",
                email_verified_at=FIXED_NOW,
            )
            db.add(user)
            return user

        super_admin = make_user("superadmin@lialenergy.demo", "DemoPass123!", ["SUPER_ADMIN"])
        admin = make_user("admin@lialenergy.demo", "DemoPass123!", ["ADMIN"])
        back_office = make_user("backoffice@lialenergy.demo", "DemoPass123!", ["BACK_OFFICE_OPERATOR"])
        accounting = make_user("accounting@lialenergy.demo", "DemoPass123!", ["ACCOUNTING_OPERATOR"])
        sales_manager = make_user("salesmanager@lialenergy.demo", "DemoPass123!", ["SALES_MANAGER"])
        await db.flush()

        for user, role_code in [
            (super_admin, "SUPER_ADMIN"),
            (admin, "ADMIN"),
            (back_office, "BACK_OFFICE_OPERATOR"),
            (accounting, "ACCOUNTING_OPERATOR"),
            (sales_manager, "SALES_MANAGER"),
        ]:
            db.add(UserRole(user_id=user.id, organization_id=org_id, role_id=roles_by_code[role_code].id))
        await db.commit()

        # --- Commercial network: two parallel top-level branches, 6 levels deep ---
        promoter_names = [
            "Anna Bianchi", "Luca Ferrari", "Giulia Romano", "Marco Colombo", "Sara Ricci",
            "Davide Marino", "Elena Greco", "Paolo Bruno", "Chiara Gallo", "Fabio Conti",
            "Valentina Rossi", "Matteo De Luca", "Francesca Costa", "Simone Giordano",
            "Martina Mancini", "Alessandro Rizzo", "Federica Lombardi", "Andrea Moretti",
            "Silvia Barbieri", "Nicola Fontana",
        ]
        name_iter = iter(promoter_names)

        async def new_agent(
            rank_code: str, parent_id: uuid.UUID | None, promoter_code: str, login_email: str | None = None
        ) -> uuid.UUID:
            display_name = next(name_iter)
            first_name, _, last_name = display_name.partition(" ")
            promoter_user_id = None
            if login_email is not None:
                promoter_user = make_user(login_email, "DemoPass123!", ["PROMOTER"])
                await db.flush()
                db.add(
                    UserRole(
                        user_id=promoter_user.id, organization_id=org_id, role_id=roles_by_code["PROMOTER"].id
                    )
                )
                await db.flush()
                promoter_user_id = promoter_user.id

            agent = await network_service.create_agent(
                db,
                organization_id=org_id,
                first_name=first_name,
                last_name=last_name,
                promoter_code=promoter_code,
                parent_agent_id=parent_id,
                joined_at=FIXED_NOW - timedelta(days=180),
                actor_user_id=admin.id,
                current_rank_id=ranks_by_code[rank_code].id,
                user_id=promoter_user_id,
            )
            code_row = PromoterCode(
                organization_id=org_id,
                agent_id=agent.id,
                code=promoter_code,
                personal_link=f"https://lialenergy.demo/r/{promoter_code}",
                status="ACTIVE",
                valid_from=FIXED_NOW - timedelta(days=180),
            )
            db.add(code_row)
            await db.commit()
            return agent.id

        # Branch A (depth 0..5). a0 gets a real login so the promoter dashboard is
        # demonstrable end-to-end: sees its own branch (network.read_branch) and its
        # own accrued commissions (commissions.read_own), never Branch B's data.
        a0 = await new_agent("MD5", None, "MD5-ROSSI", login_email="promoter@lialenergy.demo")
        a1 = await new_agent("TL4", a0, "TL4-A01")
        a2 = await new_agent("TL2", a1, "TL2-A02")
        a3 = await new_agent("S3", a2, "S3-A03")
        a4 = await new_agent("S2", a3, "S2-A04")
        a5_producer = await new_agent("S1", a4, "S1-A05")  # 6 levels deep: a0..a5
        # parallel sub-branches off a1 and a2 to demonstrate branch isolation
        a6 = await new_agent("TL1", a1, "TL1-A06")
        await new_agent("S1", a6, "S1-A07")
        a8 = await new_agent("S2", a2, "S2-A08")
        a9 = await new_agent("S1", a8, "S1-A09")

        # Branch B: separate root, never an ancestor/descendant of Branch A
        b0 = await new_agent("MD3", None, "MD3-CONTI")
        b1 = await new_agent("TL3", b0, "TL3-B01")
        b2 = await new_agent("S3", b1, "S3-B02")
        b3_producer = await new_agent("S1", b2, "S1-B03")
        b4 = await new_agent("TL1", b1, "TL1-B04")
        b5 = await new_agent("S2", b4, "S2-B05")
        await new_agent("S1", b5, "S1-B06")
        b7 = await new_agent("TL2", b0, "TL2-B07")
        b8 = await new_agent("S1", b7, "S1-B08")
        b9 = await new_agent("S1", b7, "S1-B09")

        # --- Catalog: exactly the 4 packages the network actually sells --
        # Luce/Gas, each in "Standard" or "Energia Circolare" formula. The
        # formula is what carries the different gettone ladder (commission_
        # tokens), not a separate field -- see catalog/models.py::ProductVersion.
        luce_std_product = Product(organization_id=org_id, code="LUCE-STD", energy_type="ELECTRICITY", customer_type="PRIVATE")
        luce_circ_product = Product(organization_id=org_id, code="LUCE-CIRCOLARE", energy_type="ELECTRICITY", customer_type="PRIVATE")
        gas_std_product = Product(organization_id=org_id, code="GAS-STD", energy_type="GAS", customer_type="PRIVATE")
        gas_circ_product = Product(organization_id=org_id, code="GAS-CIRCOLARE", energy_type="GAS", customer_type="PRIVATE")
        db.add_all([luce_std_product, luce_circ_product, gas_std_product, gas_circ_product])
        await db.flush()

        luce_std_version = ProductVersion(
            product_id=luce_std_product.id, version_label="1.0", name="Luce Standard",
            base_price_cents=1800, recurring_fee_cents=300, commission_plan_version_id=plan_version.id,
            commission_tokens=STANDARD_TOKENS_CENTS, valid_from=FIXED_NOW,
        )
        luce_circ_version = ProductVersion(
            product_id=luce_circ_product.id, version_label="1.0", name="Luce Energia Circolare",
            base_price_cents=2200, recurring_fee_cents=400, commission_plan_version_id=plan_version.id,
            commission_tokens=CIRCULAR_TOKENS_CENTS, valid_from=FIXED_NOW,
        )
        gas_std_version = ProductVersion(
            product_id=gas_std_product.id, version_label="1.0", name="Gas Standard",
            base_price_cents=2000, recurring_fee_cents=300, commission_plan_version_id=plan_version.id,
            commission_tokens=STANDARD_TOKENS_CENTS, valid_from=FIXED_NOW,
        )
        gas_circ_version = ProductVersion(
            product_id=gas_circ_product.id, version_label="1.0", name="Gas Energia Circolare",
            base_price_cents=2400, recurring_fee_cents=400, commission_plan_version_id=plan_version.id,
            commission_tokens=CIRCULAR_TOKENS_CENTS, valid_from=FIXED_NOW,
        )
        db.add_all([luce_std_version, luce_circ_version, gas_std_version, gas_circ_version])
        await db.commit()

        # --- Customers, supply points, contracts ---
        async def new_customer(
            kind: str, first: str, last: str, email: str, login_email: str | None = None
        ) -> uuid.UUID:
            customer_user_id = None
            if login_email is not None:
                customer_user = make_user(login_email, "DemoPass123!", ["CUSTOMER"])
                await db.flush()
                db.add(
                    UserRole(
                        user_id=customer_user.id, organization_id=org_id, role_id=roles_by_code["CUSTOMER"].id
                    )
                )
                await db.flush()
                customer_user_id = customer_user.id

            customer = Customer(organization_id=org_id, kind=kind, email=email, user_id=customer_user_id)
            db.add(customer)
            await db.flush()
            db.add(CustomerProfile(customer_id=customer.id, first_name=first, last_name=last))
            await db.commit()
            return customer.id

        # cust1 gets a real login so the customer dashboard is demonstrable
        # end-to-end via GET /contracts/mine (ownership-scoped, never the org-wide list).
        cust1 = await new_customer(
            "PRIVATE", "Roberto", "Villa", "roberto.villa@example.demo",
            login_email="customer@lialenergy.demo",
        )
        cust2 = await new_customer("SOLE_PROPRIETOR", "Laura", "Ferri", "laura.ferri@example.demo")
        cust3 = await new_customer("COMPANY", "Officine", "Bianchi Srl", "info@officinebianchi.demo")

        async def new_supply_point(customer_id: uuid.UUID, energy_type: str) -> uuid.UUID:
            address = Address(
                organization_id=org_id, customer_id=customer_id, kind="SUPPLY",
                street="Via Roma 1", city="Milano", province="MI", postal_code="20100",
            )
            db.add(address)
            await db.flush()
            sp = SupplyPoint(
                organization_id=org_id, customer_id=customer_id, energy_type=energy_type,
                pod_code="IT001E00000001" if energy_type == "ELECTRICITY" else None,
                pdr_code="00000000000001" if energy_type == "GAS" else None,
                supply_address_id=address.id,
            )
            db.add(sp)
            await db.commit()
            return sp.id

        sp1 = await new_supply_point(cust1, "ELECTRICITY")
        sp2 = await new_supply_point(cust2, "GAS")
        sp3 = await new_supply_point(cust3, "ELECTRICITY")

        async def create_and_advance(
            customer_id: uuid.UUID, supply_point_id: uuid.UUID, product_version_id: uuid.UUID,
            producer_agent_id: uuid.UUID, target_status: str,
        ):
            contract = await contract_service.create_contract(
                db, organization_id=org_id, customer_id=customer_id, supply_point_id=supply_point_id,
                product_version_id=product_version_id, producer_agent_id=producer_agent_id,
                actor_user_id=back_office.id, correlation_id=str(uuid.uuid4()),
            )
            # Full happy-path sequence up to (and including) target_status. Stops
            # as soon as target_status is reached. DRAFT means "don't transition at
            # all" -- handled explicitly since it never appears in any path below.
            if target_status == "DRAFT":
                return contract

            full_path = [
                "SUBMITTED", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING",
                "PAID", "ACTIVATION_PENDING", "ACTIVE",
            ]
            if target_status == "REJECTED":
                full_path = ["SUBMITTED", "REJECTED"]
            elif target_status == "CANCELLED":
                full_path = full_path + ["CANCELLED"]

            for step in full_path:
                contract = await contract_service.transition_contract(
                    db, organization_id=org_id, contract=contract, to_status=step,
                    actor_user_id=admin.id, reason="demo data", notes=None, correlation_id=str(uuid.uuid4()),
                )
                if step == target_status:
                    break
            return contract

        await create_and_advance(cust1, sp1, luce_std_version.id, a5_producer, "ACTIVE")
        await create_and_advance(cust2, sp2, gas_std_version.id, b3_producer, "ACTIVE")
        await create_and_advance(cust3, sp3, luce_circ_version.id, a9, "DRAFT")
        await create_and_advance(cust1, sp1, gas_std_version.id, b8, "REJECTED")
        await create_and_advance(cust2, sp2, luce_std_version.id, b9, "CANCELLED")

        processed = await process_pending_outbox_events(db)
        print(f"Seed complete. Processed {processed} outbox event(s) -> commissions generated.")
        print(f"Organization ID: {org_id}")
        print("Demo logins (password: DemoPass123!):")
        print("  superadmin@lialenergy.demo (SUPER_ADMIN)")
        print("  admin@lialenergy.demo (ADMIN)")
        print("  backoffice@lialenergy.demo (BACK_OFFICE_OPERATOR)")
        print("  accounting@lialenergy.demo (ACCOUNTING_OPERATOR)")
        print("  salesmanager@lialenergy.demo (SALES_MANAGER)")
        print("  promoter@lialenergy.demo (PROMOTER, agent MD5-ROSSI, branch A root)")
        print("  customer@lialenergy.demo (CUSTOMER, linked to Roberto Villa)")
