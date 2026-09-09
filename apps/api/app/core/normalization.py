import re

_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_person_name(v: str | None) -> str | None:
    """Trim, collapse internal whitespace runs to a single space, and
    uppercase -- 'mario   rossi', 'Mario Rossi' and 'MARIO ROSSI' all end up
    stored identically, regardless of how the customer typed it. Applied at
    the schema layer (mode="before") so it is the single point of truth for
    every first_name/last_name field across registration, customer/agent
    creation and updates -- never re-implemented per form. None passes
    through unchanged (an omitted optional field must stay omitted, not
    become the string "NONE")."""
    if v is None:
        return v
    return _WHITESPACE_RUN.sub(" ", v.strip()).upper()


def normalize_email(v: str | None) -> str | None:
    """Trim, strip ALL whitespace (not just the ends -- a stray space
    copy-pasted into the middle of an address, e.g. 'foo@ bar.com', is never
    part of a valid address and would otherwise fail EmailStr validation
    outright instead of being silently cleaned up), and lowercase. An email
    address is effectively case-insensitive in real-world use (no mainstream
    mailbox provider treats 'Foo@bar.com' and 'foo@bar.com' as different
    inboxes) -- storing it consistently lowercase prevents the same real
    inbox from ever silently creating two different-looking accounts.
    None passes through unchanged."""
    if v is None:
        return v
    return _WHITESPACE_RUN.sub("", v.strip()).lower()
