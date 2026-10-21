"""Optional email when a background run finishes.

Off unless the server's mail settings are given in the environment:

    MICROPLATFORM_SMTP_HOST      mail server, e.g. smtp.example.ac.il   (required to switch on)
    MICROPLATFORM_SMTP_SENDER    the From address                       (required to switch on)
    MICROPLATFORM_SMTP_PORT      default 587
    MICROPLATFORM_SMTP_USER      if the server needs a login
    MICROPLATFORM_SMTP_PASSWORD
    MICROPLATFORM_SMTP_TLS       "1" (default) to use STARTTLS, "0" to not

Privacy: an email holds only the results link, never data or results, and the
address is deleted from the run as soon as the email has been sent.
"""

from __future__ import annotations

import os
import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


@dataclass(frozen=True)
class EmailSettings:
    host: str
    sender: str
    port: int = 587
    user: str | None = None
    password: str | None = None
    use_tls: bool = True

    @classmethod
    def from_env(cls, env=os.environ) -> EmailSettings | None:
        """The settings from the environment, or None when email is not switched on."""
        host, sender = env.get("MICROPLATFORM_SMTP_HOST"), env.get("MICROPLATFORM_SMTP_SENDER")
        if not host or not sender:
            return None
        return cls(
            host=host, sender=sender,
            port=int(env.get("MICROPLATFORM_SMTP_PORT", "587")),
            user=env.get("MICROPLATFORM_SMTP_USER") or None,
            password=env.get("MICROPLATFORM_SMTP_PASSWORD") or None,
            use_tls=env.get("MICROPLATFORM_SMTP_TLS", "1") != "0",
        )


def is_valid_email(address: str) -> bool:
    return bool(_EMAIL.fullmatch(address.strip()))


def finished_message(analysis_name: str, status: str, url: str) -> tuple[str, str]:
    """Subject and body: the link only, never data or results."""
    if status == "done":
        subject = "Your microbiome analysis is ready"
        first = f'Your analysis of "{analysis_name}" has finished. See the results here:'
    else:
        subject = "Your microbiome analysis did not finish"
        first = f'Your analysis of "{analysis_name}" did not finish. The page explains what went wrong:'
    body = (
        f"{first}\n\n{url}\n\n"
        "This email contains no data. Anyone with the link can open the results, so please do not forward it "
        "outside your team. Your email address has now been deleted from the analysis.\n\n"
        "Microbiome Platform, Prof. Yoram Louzoun Lab, Bar-Ilan University\n"
    )
    return subject, body


class EmailNotifier:
    def __init__(self, settings: EmailSettings) -> None:
        self.settings = settings

    def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = self.settings.sender, to, subject
        message.set_content(body)
        with smtplib.SMTP(self.settings.host, self.settings.port, timeout=30) as smtp:
            if self.settings.use_tls:
                smtp.starttls()
            if self.settings.user:
                smtp.login(self.settings.user, self.settings.password or "")
            smtp.send_message(message)
