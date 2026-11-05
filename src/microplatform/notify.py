"""Optional email when a background run finishes.

Off unless the mail settings are given. They are read from environment variables (on a
server: /etc/microplatform/microplatform.env, see deploy/) and, on a laptop, from the
file ``<instance>/email.env`` (same names, ``NAME=value`` lines). An environment variable
wins over the file. Neither place is in Git; nothing is ever hard-coded.

    MICROPLATFORM_SMTP_HOST      mail server, e.g. smtp.example.ac.il   (required to switch on)
    MICROPLATFORM_SMTP_SENDER    the From address                       (required to switch on)
    MICROPLATFORM_SMTP_SECURITY  starttls (default) | ssl | none
    MICROPLATFORM_SMTP_PORT      default by security: starttls 587, ssl 465, none 25
    MICROPLATFORM_SMTP_USER      if the server needs a login
    MICROPLATFORM_SMTP_PASSWORD  (never printed or logged)

Check the settings with one test email: ``python -m microplatform.notify --to you@lab.ac.il``.

Privacy: an email holds only the results link, never data or results, and the
address is deleted from the run as soon as the email has been sent.
"""

from __future__ import annotations

import argparse
import os
import re
import smtplib
import ssl
import sys
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
PREFIX = "MICROPLATFORM_SMTP_"
SETTINGS_FILE = "email.env"  # inside the instance folder (gitignored, like everything there)
SECURITY = {"starttls": 587, "ssl": 465, "none": 25}  # each mode and its usual port


@dataclass(frozen=True)
class EmailSettings:
    host: str
    sender: str
    port: int = 587
    user: str | None = None
    password: str | None = field(default=None, repr=False)  # never shown in logs or errors
    security: str = "starttls"

    @classmethod
    def from_env(cls, env=os.environ) -> EmailSettings | None:
        """The settings from these variables, or None when email is not switched on."""
        host, sender = env.get(f"{PREFIX}HOST"), env.get(f"{PREFIX}SENDER")
        if not host or not sender:
            return None
        security = (env.get(f"{PREFIX}SECURITY") or "starttls").strip().lower()
        if security not in SECURITY:
            raise ValueError(f"{PREFIX}SECURITY must be one of {', '.join(SECURITY)}, not {security!r}")
        port = env.get(f"{PREFIX}PORT")
        return cls(
            host=host.strip(), sender=sender.strip(),
            port=int(port) if port else SECURITY[security],
            user=env.get(f"{PREFIX}USER") or None,
            password=env.get(f"{PREFIX}PASSWORD") or None,
            security=security,
        )

    @classmethod
    def load(cls, instance: Path | None = None, env=os.environ) -> EmailSettings | None:
        """The settings from ``<instance>/email.env`` and the environment (which wins), or None."""
        merged = read_settings_file(Path(instance) / SETTINGS_FILE) if instance else {}
        merged.update({k: v for k, v in env.items() if k.startswith(PREFIX) and v})
        return cls.from_env(merged)

    def describe(self) -> str:
        """The settings in words, for logs: never the password."""
        login = f", login as {self.user}" if self.user else ", no login"
        return f"{self.host}:{self.port} ({self.security}{login}), from {self.sender}"


def read_settings_file(path: Path) -> dict[str, str]:
    """``NAME=value`` lines (blank lines and ``#`` comments ignored; optional quotes removed)."""
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = (part.strip() for part in line.split("=", 1))
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if name.startswith(PREFIX) and value:
            values[name] = value
    return values


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
        s = self.settings
        context = ssl.create_default_context()  # the server's certificate is checked
        if s.security == "ssl":
            server = smtplib.SMTP_SSL(s.host, s.port, timeout=30, context=context)
        else:
            server = smtplib.SMTP(s.host, s.port, timeout=30)
        with server as smtp:
            if s.security == "starttls":
                smtp.starttls(context=context)
            if s.user:
                smtp.login(s.user, s.password or "")
            smtp.send_message(message)


def main(argv: list[str] | None = None) -> int:
    """Send one test email with the configured settings, and say plainly what happened."""
    parser = argparse.ArgumentParser(prog="python -m microplatform.notify",
                                     description="Send one test email to check the SMTP settings.")
    parser.add_argument("--to", required=True, help="where to send the test email")
    parser.add_argument("--instance", type=Path,
                        default=Path(os.environ.get("MICROPLATFORM_INSTANCE", "instance")),
                        help="the instance folder holding email.env (default: $MICROPLATFORM_INSTANCE or ./instance)")
    args = parser.parse_args(argv)
    try:
        settings = EmailSettings.load(args.instance)
    except ValueError as exc:
        print(f"Email settings are wrong: {exc}", file=sys.stderr)
        return 2
    if settings is None:
        print(f"Email is OFF: set {PREFIX}HOST and {PREFIX}SENDER (in the environment or in "
              f"{args.instance / SETTINGS_FILE}).", file=sys.stderr)
        return 1
    print(f"Sending a test email to {args.to} through {settings.describe()} …")
    try:
        EmailNotifier(settings).send(args.to, "Microbiome Platform: test email",
                                     "This is a test email from the Microbiome Platform. "
                                     "If you received it, results emails will work.\n")
    except (OSError, smtplib.SMTPException) as exc:
        print(f"Failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print("Sent. Check the inbox (and the spam folder).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
