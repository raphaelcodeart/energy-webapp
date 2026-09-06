"""Shared HTML layout for every outbound email (verification, password reset,
cashback, admin ticket alerts, ...) -- one branded shell so a change to the
look (logo, colors, footer) happens in one place instead of N ad-hoc bodies.

Table-based layout on purpose: this has to render in Outlook/Gmail/Apple
Mail alike, which do not reliably support flexbox/grid in email HTML.
"""

LOGO_URL = "https://lialenergy.it/img/logo.png"
BRAND_COLOR = "#f97316"  # orange-500, matches the dashboard's accent color
TEXT_COLOR = "#1e293b"
MUTED_COLOR = "#64748b"


def render_email(
    *,
    preheader: str,
    heading: str,
    body_html: str,
    cta_label: str | None = None,
    cta_url: str | None = None,
) -> str:
    """body_html is trusted, pre-built markup from the caller (already-escaped
    plain strings interpolated by each call site) -- this module only owns the
    surrounding shell, never user-supplied content directly."""
    cta_block = ""
    if cta_label and cta_url:
        cta_block = f"""
        <tr>
          <td align="center" style="padding: 8px 0 28px 0;">
            <a href="{cta_url}" style="background:{BRAND_COLOR}; color:#ffffff; text-decoration:none;
               font-weight:600; font-size:15px; padding:14px 32px; border-radius:10px; display:inline-block;">
              {cta_label}
            </a>
          </td>
        </tr>"""

    return f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{heading}</title>
</head>
<body style="margin:0; padding:0; background:#f1f5f9; font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <div style="display:none; max-height:0; overflow:hidden; opacity:0;">{preheader}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9; padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px; background:#ffffff; border-radius:16px; overflow:hidden; box-shadow:0 1px 3px rgba(15,23,42,0.08);">
          <tr>
            <td align="center" style="padding:32px 32px 16px 32px;">
              <img src="{LOGO_URL}" alt="Lial Energy" height="40" style="height:40px; width:auto;">
            </td>
          </tr>
          <tr>
            <td style="padding:8px 32px 0 32px;">
              <h1 style="margin:0 0 16px 0; font-size:20px; line-height:1.3; color:{TEXT_COLOR};">{heading}</h1>
              <div style="font-size:15px; line-height:1.6; color:{TEXT_COLOR};">
                {body_html}
              </div>
            </td>
          </tr>
          {cta_block}
          <tr>
            <td style="padding:24px 32px 32px 32px; border-top:1px solid #f1f5f9;">
              <p style="margin:16px 0 0 0; font-size:12px; line-height:1.5; color:{MUTED_COLOR};">
                Lial Energy S.r.l. &middot; Questa email è stata generata automaticamente, non rispondere direttamente a questo indirizzo.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
