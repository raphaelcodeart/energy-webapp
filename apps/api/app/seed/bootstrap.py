"""Avvio di una NUOVA azienda su un database vuoto.

`python -m app.seed` crea la demo di Lial Energy: venti promoter finti,
clienti, contratti, provvigioni. Serve per verificare che lo stack funzioni,
e non va mai eseguito per un cliente reale.

Questo modulo fa l'altra cosa, quella che finora mancava: crea **solo ciò
senza cui l'applicazione non parte**, e niente altro.

  - il catalogo globale dei `permissions` (una riga per codice, condivisa fra
    tutte le organizzazioni);
  - l'`Organization`;
  - i ruoli di sistema di quell'organizzazione e i loro permessi;
  - la scala dei `ranks` e una `CommissionPlanVersion` attiva -- senza queste
    il motore provvigioni non ha su cosa appoggiarsi;
  - **un solo** utente SUPER_ADMIN, da cui poi si fa tutto il resto
    dall'interfaccia.

Nessun cliente, nessun prodotto, nessun contratto, nessun promoter: quelli li
crea l'azienda vera con i propri dati.

È **idempotente**: rieseguirlo con lo stesso nome organizzazione non duplica
nulla, aggiunge solo ciò che manca. Serve perché la ricostruzione di un
server raramente riesce tutta al primo tentativo, e un bootstrap che al
secondo colpo esplode su una UNIQUE è un bootstrap che non si osa rilanciare.

Uso:

    docker compose -f docker-compose.dev.yml exec api \\
      python -m app.seed.bootstrap \\
        --organization-name "Nome Azienda" \\
        --legal-name "Nome Azienda S.r.l." \\
        --admin-email "titolare@azienda.it"

La password, se non la passi con `--admin-password`, viene generata e
stampata **una sola volta**: non è recuperabile dopo, si rifà solo con un
reset. Vedi docs/server-migration-guide.md §12.
"""

import argparse
import asyncio
import secrets
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.core.security import hash_password
from app.domains.commissions.models import CommissionPlanVersion, Rank
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
from app.domains.users.models import User
from app.seed.ranks import RANK_SEED, RULE_VERSION

BOOTSTRAP_ROLE = "SUPER_ADMIN"


def generate_password() -> str:
    """16 caratteri url-safe. Ben oltre il minimo di 8 imposto dalle schemas:
    questa password viaggia in un terminale e in un incolla, non in una
    testa, quindi tanto vale che sia lunga."""
    return secrets.token_urlsafe(12)


async def _ensure_permissions(db) -> dict[str, Permission]:
    """`permissions` non ha organization_id: è un catalogo globale, e alcune
    migrazioni dati (0011, 0012, 0013) ci inseriscono già dei codici prima
    che questo script giri. Si guarda cosa c'è già, esattamente come fa
    seed/data.py, così su un database migrato non si esplode su una
    UniqueViolation."""
    existing = (await db.execute(select(Permission).where(Permission.code.in_(PERMISSIONS)))).scalars().all()
    by_code = {p.code: p for p in existing}
    for code in PERMISSIONS:
        if code not in by_code:
            perm = Permission(code=code, description="")
            db.add(perm)
            by_code[code] = perm
    await db.flush()
    return by_code


async def _ensure_roles(db, *, org_id: uuid.UUID, permissions_by_code: dict[str, Permission]) -> dict[str, Role]:
    existing = (await db.execute(select(Role).where(Role.organization_id == org_id))).scalars().all()
    by_code = {r.code: r for r in existing}
    for code in SYSTEM_ROLES:
        if code not in by_code:
            role = Role(organization_id=org_id, code=code, name=code.replace("_", " ").title())
            db.add(role)
            by_code[code] = role
    await db.flush()

    granted = {
        (rp.role_id, rp.permission_id)
        for rp in (
            await db.execute(
                select(RolePermission).where(RolePermission.role_id.in_([r.id for r in by_code.values()]))
            )
        ).scalars().all()
    }
    for role_code, permission_codes in DEFAULT_ROLE_PERMISSIONS.items():
        role = by_code[role_code]
        for permission_code in permission_codes:
            permission = permissions_by_code[permission_code]
            if (role.id, permission.id) not in granted:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    await db.flush()
    return by_code


async def _ensure_ranks_and_plan(db, *, org_id: uuid.UUID, now: datetime) -> tuple[int, bool]:
    existing_codes = {
        code
        for (code,) in (await db.execute(select(Rank.code).where(Rank.organization_id == org_id))).all()
    }
    created = 0
    for r in RANK_SEED:
        if r["code"] in existing_codes:
            continue
        db.add(
            Rank(
                organization_id=org_id,
                code=r["code"],
                name=r["name"],
                level=r["level"],
                personal_token_cents=r["personal_token_cents"],
                personal_volume_threshold_cents=r["personal_volume_threshold_cents"],
                group_volume_threshold_cents=r["group_volume_threshold_cents"],
                valid_from=now,
                rule_version=RULE_VERSION,
            )
        )
        created += 1

    plan = (
        await db.execute(
            select(CommissionPlanVersion).where(
                CommissionPlanVersion.organization_id == org_id,
                CommissionPlanVersion.status == "ACTIVE",
            )
        )
    ).scalars().first()
    plan_created = plan is None
    if plan_created:
        db.add(
            CommissionPlanVersion(
                organization_id=org_id, version_label=RULE_VERSION, valid_from=now, status="ACTIVE"
            )
        )
    await db.flush()
    return created, plan_created


@dataclass
class BootstrapResult:
    organization_id: uuid.UUID
    organization_created: bool
    roles: int
    #: Quanti rank sono stati inseriti adesso -- 0 alla seconda esecuzione.
    ranks_created: int
    plan_created: bool
    admin_created: bool
    #: Valorizzata SOLO quando l'account è appena stato creato e la password
    #: l'ha generata questo script. Mai letta da nessuna parte: esiste solo
    #: per essere stampata una volta e dimenticata.
    generated_password: str | None


async def bootstrap_organization(
    db,
    *,
    organization_name: str,
    legal_name: str,
    admin_email: str,
    admin_password: str | None,
    now: datetime | None = None,
) -> BootstrapResult:
    """Il lavoro vero, su una sessione passata dal chiamante -- così i test
    girano sul database di test e non su quello a cui punta
    AsyncSessionLocal."""
    admin_email = admin_email.strip().lower()
    now = now or datetime.now(UTC)
    generated_password = None

    org = (
        await db.execute(select(Organization).where(Organization.name == organization_name))
    ).scalars().first()
    org_created = org is None
    if org is None:
        org = Organization(name=organization_name, legal_name=legal_name, status="ACTIVE")
        db.add(org)
        await db.flush()
    org_id = org.id

    permissions_by_code = await _ensure_permissions(db)
    roles_by_code = await _ensure_roles(db, org_id=org_id, permissions_by_code=permissions_by_code)
    ranks_created, plan_created = await _ensure_ranks_and_plan(db, org_id=org_id, now=now)

    user = (
        await db.execute(select(User).where(User.organization_id == org_id, User.email == admin_email))
    ).scalars().first()
    user_created = user is None
    if user is None:
        if admin_password is None:
            admin_password = generated_password = generate_password()
        user = User(
            organization_id=org_id,
            email=admin_email,
            password_hash=hash_password(admin_password),
            status="ACTIVE",
            # Marcata verificata di proposito: questo account nasce da un
            # comando eseguito sul server, che è una prova di controllo ben
            # più forte di un link cliccato -- e all'ora del bootstrap l'SMTP
            # quasi sempre non è ancora configurato, quindi la mail di
            # verifica non partirebbe nemmeno.
            email_verified_at=now,
            # privacy_accepted_at e i campi anagrafici restano NULL apposta:
            # sono atti di una persona vera, non del comando che le crea
            # l'account. Al primo accesso l'interfaccia glieli chiede. È il
            # comportamento voluto, non un bootstrap incompleto.
        )
        db.add(user)
        await db.flush()
        db.add(UserRole(user_id=user.id, organization_id=org_id, role_id=roles_by_code[BOOTSTRAP_ROLE].id))

    await db.commit()
    return BootstrapResult(
        organization_id=org_id,
        organization_created=org_created,
        roles=len(roles_by_code),
        ranks_created=ranks_created,
        plan_created=plan_created,
        admin_created=user_created,
        generated_password=generated_password,
    )


async def run(
    *,
    organization_name: str,
    legal_name: str,
    admin_email: str,
    admin_password: str | None,
) -> int:
    async with AsyncSessionLocal() as db:
        result = await bootstrap_organization(
            db,
            organization_name=organization_name,
            legal_name=legal_name,
            admin_email=admin_email,
            admin_password=admin_password,
        )

    print()
    print("=" * 72)
    print("  Bootstrap completato")
    print("=" * 72)
    print(f"  Organizzazione    {organization_name}  ({'creata' if result.organization_created else 'già esistente'})")
    print(f"  Organization ID   {result.organization_id}")
    print(f"  Ruoli             {result.roles} ruoli di sistema, permessi allineati")
    print(f"  Ranks             {result.ranks_created} creati ({len(RANK_SEED)} attesi in totale)")
    print(f"  Piano provvigioni {'creato' if result.plan_created else 'già attivo'} ({RULE_VERSION})")
    print(f"  Amministratore    {admin_email.strip().lower()}  "
          f"({'creato' if result.admin_created else 'già esistente, invariato'})")
    if result.generated_password is not None:
        print()
        print(f"  PASSWORD (mostrata una sola volta):  {result.generated_password}")
        print("  Salvala ora. Non è recuperabile: si può solo rifare un reset.")
    elif result.admin_created:
        print("  Password: quella che hai passato con --admin-password.")
    print()
    print("  Prossimi passi (docs/server-migration-guide.md §12):")
    print("   1. Accedi come amministratore e completa il tuo profilo quando te lo chiede.")
    print("   2. Impostazioni organizzazione: SMTP, Stripe, IBAN aziendale.")
    print("   3. Crea i prodotti reali, poi i primi promoter.")
    print("=" * 72)
    print()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.seed.bootstrap",
        description="Crea una nuova organizzazione con il minimo indispensabile per partire.",
    )
    parser.add_argument("--organization-name", required=True, help='Nome visibile, es. "Nome Azienda"')
    parser.add_argument("--legal-name", required=True, help='Ragione sociale, es. "Nome Azienda S.r.l."')
    parser.add_argument("--admin-email", required=True, help="Email del primo SUPER_ADMIN")
    parser.add_argument(
        "--admin-password",
        default=None,
        help="Se omessa ne viene generata una e stampata una sola volta (consigliato)",
    )
    args = parser.parse_args(argv)

    if args.admin_password is not None and len(args.admin_password) < 8:
        parser.error("la password deve essere di almeno 8 caratteri (stesso minimo dell'app)")

    return asyncio.run(
        run(
            organization_name=args.organization_name,
            legal_name=args.legal_name,
            admin_email=args.admin_email,
            admin_password=args.admin_password,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
