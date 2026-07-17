"""
Diňe 'email nädip hakykatdan iberilýär' bilýär - SMTP detal-lary şu
ýerde. Bu modul 'näme üçin', 'haçan' diýen sowallary bilenok, diňe
'nädip'.
"""

import logging
from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger("notifications.email_provider")


async def send_raw_email(to: str, subject: str, html_body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.EMAIL_FROM_ADDRESS
    message["To"] = to
    message["Subject"] = subject
    message.set_content("Bu email HTML görnüşinde okalmaly.")  # plaintext fallback
    message.add_alternative(html_body, subtype="html")

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD,
            start_tls=True,
        )
    except aiosmtplib.SMTPException as exc:
        # Bilkastlaýyn gaýtadan "raise" edýäris - worker.py-daky
        # _process_one muny tutup, "attempts" sanyny artdyryp, retry
        # logikasyny işletmeli (bu funksiýanyň özi retry etmeli DÄL,
        # ol worker-iň jogapkärçiligi).
        logger.error("SMTP send failed to %s: %s", to, exc)
        raise