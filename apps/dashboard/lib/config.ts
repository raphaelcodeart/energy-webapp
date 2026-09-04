// This platform's data model is multi-tenant (organizations table -- see
// docs/database-model.md §1): it can host more than one reseller company,
// each fully isolated from the others. Today there is genuinely only ONE
// organization ("Lial Energy Demo"), so asking every end user to know and
// paste its UUID on login/forgot-password was pure friction with no real
// choice behind it. This constant lets the login/forgot-password forms fill
// it in silently instead of prompting for it.
//
// If a second organization is ever onboarded, this single-org shortcut stops
// being correct -- bring back an organization picker (or resolve it from the
// email server-side) at that point, don't just add a second hardcoded value
// here.
export const DEFAULT_ORGANIZATION_ID = "2617cc7b-9f55-4e08-bded-e40680035c36";
