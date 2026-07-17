"""
Şablonlar - event payload-yny hakyky email mazmunyna öwürýär.
Bulary aýratyn faýla çykarmak, HTML-i handler-den aýyrýar (geljekde
Jinja2 template file-lara geçmek aňsat bolar, logika üýtgemez).
"""

def render_email_verification(payload: dict) -> tuple[str, str]:
    token = payload["token"]
    link = f"https://superwallet.app/verify-email?token={token}"
    subject = "Email salgyňyzy tassyklaň"
    body = f"<p>Tassyklamak üçin basyň: <a href='{link}'>{link}</a></p>"
    return subject, body


def render_password_reset(payload: dict) -> tuple[str, str]:
    token = payload["token"]
    link = f"https://superwallet.app/reset-password?token={token}"
    subject = "Parol täzelemek"
    body = f"<p>Parolyňyzy täzelemek üçin basyň: <a href='{link}'>{link}</a></p>"
    return subject, body


EMAIL_TEMPLATE_RENDERERS = {
    "email_verification": render_email_verification,
    "password_reset": render_password_reset,
}