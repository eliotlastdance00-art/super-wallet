from app.notifications.providers.email_provider import send_raw_email
from app.notifications.templates import EMAIL_TEMPLATE_RENDERERS


async def handle_email_event(payload: dict) -> None:
    """
    payload şekili: {"template": "password_reset", "to": "...", "token": "..."}
    'template' haýsy render funksiýasyny saýlamaly diýeni kesgitleýär.
    """
    template_name = payload["template"]
    renderer = EMAIL_TEMPLATE_RENDERERS.get(template_name)
    if renderer is None:
        raise ValueError(f"Näbelli email template: {template_name}")

    subject, body = renderer(payload)
    await send_raw_email(to=payload["to"], subject=subject, html_body=body)
