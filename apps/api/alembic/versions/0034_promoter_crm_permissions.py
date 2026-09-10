"""Session 36's "Miei Clienti" promoter CRM: a promoter registers a new
customer themselves (no self-registration needed) and activates/manages a
contract for them, including uploading documents on their behalf. Grants
the PROMOTER role two permissions it never had before -- `documents.upload`
and `documents.download` -- both `documents.upload`/`documents.download`
Permission rows already exist (ADMIN/BACK_OFFICE_OPERATOR already hold
them), this only adds the two new role_permissions rows for PROMOTER.
Scoping (a promoter may only touch documents on a contract THEY are the
producer of, never any contract in the org) is enforced in
documents/router.py::_assert_contract_document_access, not by this
permission grant alone -- same "permission gates the door, the service/
router still checks ownership" discipline as every other role-scoped
surface in this codebase. Deliberately NOT `documents.review` (staff-only
approve/reject) and NOT any change to `customers.read`'s existing scope
(see network/service.py::list_recruited_customers -- the promoter's CRM
list is a brand-new, separately-scoped query, not a widened GET /customers).

Revision ID: a1c7e920f4b6
Revises: f3a7c9e15b04
Create Date: 2026-09-11 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1c7e920f4b6"
down_revision: Union[str, None] = "f3a7c9e15b04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_PROMOTER_PERMISSIONS = ["documents.upload", "documents.download"]


def upgrade() -> None:
    conn = op.get_bind()
    permissions_table = sa.table("permissions", sa.column("id", sa.UUID()), sa.column("code", sa.String()))
    role_permissions_table = sa.table(
        "role_permissions", sa.column("role_id", sa.UUID()), sa.column("permission_id", sa.UUID())
    )
    roles_table = sa.table("roles", sa.column("id", sa.UUID()), sa.column("code", sa.String()))

    permission_ids = dict(
        conn.execute(
            sa.select(permissions_table.c.code, permissions_table.c.id).where(
                permissions_table.c.code.in_(NEW_PROMOTER_PERMISSIONS)
            )
        ).all()
    )
    role_rows = conn.execute(sa.select(roles_table.c.id, roles_table.c.code)).all()
    for role_id, role_code in role_rows:
        if role_code != "PROMOTER":
            continue
        for code in NEW_PROMOTER_PERMISSIONS:
            permission_id = permission_ids.get(code)
            if permission_id is None:
                continue
            conn.execute(
                postgresql.insert(role_permissions_table)
                .values(role_id=role_id, permission_id=permission_id)
                .on_conflict_do_nothing()
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE code = 'PROMOTER') "
            "AND permission_id IN (SELECT id FROM permissions WHERE code IN ('documents.upload', 'documents.download'))"
        )
    )
