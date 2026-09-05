"""Organization.settings (JSONB) exposed through a typed subset -- starting
with the bank IBAN customers wire bonifico payments to (see
docs/cashback-partner-invoices-plan.md). Covers that an update merges rather
than replaces the dict, so an unrelated key already living there (or a field
simply omitted from this PATCH) survives untouched."""

import pytest

from app.domains.organizations import service as organizations_service
from app.domains.organizations.models import Organization
from app.domains.organizations.schemas import OrganizationSettingsUpdate, PaymentSettingsUpdate


@pytest.mark.asyncio
async def test_get_settings_defaults_to_none_when_nothing_set(db, organization_id):
    settings = await organizations_service.get_settings(db, organization_id=organization_id)
    assert settings == {"bank_iban": None, "bank_account_holder": None, "bank_transfer_instructions": None}


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
    assert updated == {
        "bank_iban": "IT60X0542811101000000123456",
        "bank_account_holder": "Lial Energy Srl",
        "bank_transfer_instructions": None,
    }

    # Omitting a field (exclude_unset) leaves it exactly as it was.
    partial = await organizations_service.update_settings(
        db, organization_id=organization_id, payload=OrganizationSettingsUpdate(bank_account_holder="New Holder"),
    )
    assert partial["bank_iban"] == "IT60X0542811101000000123456"
    assert partial["bank_account_holder"] == "New Holder"

    org_after = await db.get(Organization, organization_id)
    assert org_after.settings["unrelated_future_setting"] == "keep-me"


@pytest.mark.asyncio
async def test_bank_transfer_instructions_field_merges_like_the_others(db, organization_id):
    await organizations_service.update_settings(
        db, organization_id=organization_id,
        payload=OrganizationSettingsUpdate(bank_iban="IT66W0883330410000000015702"),
    )
    updated = await organizations_service.update_settings(
        db, organization_id=organization_id,
        payload=OrganizationSettingsUpdate(bank_transfer_instructions="Includi il codice ordine nella causale."),
    )
    assert updated["bank_iban"] == "IT66W0883330410000000015702"  # untouched, omitted from this PATCH
    assert updated["bank_transfer_instructions"] == "Includi il codice ordine nella causale."


@pytest.mark.asyncio
async def test_payment_settings_never_echo_the_secret_and_merge_correctly(db, organization_id):
    empty = await organizations_service.get_payment_settings(db, organization_id=organization_id)
    assert empty == {
        "stripe_publishable_key": None,
        "stripe_secret_key_configured": False,
        "stripe_secret_key_last4": None,
        "stripe_webhook_secret_configured": False,
    }

    updated = await organizations_service.update_payment_settings(
        db, organization_id=organization_id,
        payload=PaymentSettingsUpdate(
            stripe_publishable_key="pk_test_abc123",
            stripe_secret_key="sk_test_verysecretkey9999",
            stripe_webhook_secret="whsec_testsecret",
        ),
    )
    assert updated["stripe_publishable_key"] == "pk_test_abc123"  # safe to echo whole
    assert updated["stripe_secret_key_configured"] is True
    assert updated["stripe_secret_key_last4"] == "9999"  # never the full secret
    assert updated["stripe_webhook_secret_configured"] is True

    # Omitting the secret on a later PATCH leaves it untouched (no re-paste
    # needed just to change the publishable key).
    updated2 = await organizations_service.update_payment_settings(
        db, organization_id=organization_id, payload=PaymentSettingsUpdate(stripe_publishable_key="pk_test_new"),
    )
    assert updated2["stripe_publishable_key"] == "pk_test_new"
    assert updated2["stripe_secret_key_configured"] is True
    assert updated2["stripe_secret_key_last4"] == "9999"

    raw_secret = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id)
    assert raw_secret == "sk_test_verysecretkey9999"
