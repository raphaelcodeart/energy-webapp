"""Organization.settings (JSONB) exposed through a typed subset -- starting
with the bank IBAN customers wire bonifico payments to (see
docs/cashback-partner-invoices-plan.md). Covers that an update merges rather
than replaces the dict, so an unrelated key already living there (or a field
simply omitted from this PATCH) survives untouched."""

import pytest

from app.domains.organizations import service as organizations_service
from app.domains.organizations.models import Organization
from app.domains.organizations.schemas import OrganizationSettingsUpdate


@pytest.mark.asyncio
async def test_get_settings_defaults_to_none_when_nothing_set(db, organization_id):
    settings = await organizations_service.get_settings(db, organization_id=organization_id)
    assert settings == {"bank_iban": None, "bank_account_holder": None}


@pytest.mark.asyncio
async def test_update_settings_merges_and_partial_update_preserves_the_rest(db, organization_id):
    org = await db.get(Organization, organization_id)
    # An unrelated key already living in the JSONB blob -- must survive
    # untouched by anything this endpoint does.
    org.settings = {**org.settings, "unrelated_future_setting": "keep-me"}
    await db.commit()

    updated = await organizations_service.update_settings(
        db, organization_id=organization_id,
        payload=OrganizationSettingsUpdate(bank_iban="IT60X0542811101000000123456", bank_account_holder="Lial Energy Srl"),
    )
    assert updated == {"bank_iban": "IT60X0542811101000000123456", "bank_account_holder": "Lial Energy Srl"}

    # Omitting a field (exclude_unset) leaves it exactly as it was.
    partial = await organizations_service.update_settings(
        db, organization_id=organization_id, payload=OrganizationSettingsUpdate(bank_account_holder="New Holder"),
    )
    assert partial["bank_iban"] == "IT60X0542811101000000123456"
    assert partial["bank_account_holder"] == "New Holder"

    org_after = await db.get(Organization, organization_id)
    assert org_after.settings["unrelated_future_setting"] == "keep-me"
