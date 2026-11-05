"""Results emails: where the settings come from, how the mail server is used, and the test command."""

import subprocess
from pathlib import Path

import pytest

from microplatform import notify
from microplatform.notify import EmailNotifier, EmailSettings, finished_message

ROOT = Path(__file__).parents[1]
BASE = {"MICROPLATFORM_SMTP_HOST": "smtp.lab.ac.il", "MICROPLATFORM_SMTP_SENDER": "platform@lab.ac.il"}


# --- the settings ---------------------------------------------------------------------------------

def test_email_is_off_without_host_and_sender():
    assert EmailSettings.from_env({}) is None
    assert EmailSettings.from_env({"MICROPLATFORM_SMTP_HOST": "smtp.x"}) is None  # no sender
    assert EmailSettings.load(None, env={}) is None


@pytest.mark.parametrize(("security", "port"), [(None, 587), ("starttls", 587), ("ssl", 465), ("SSL", 465),
                                                ("none", 25)])
def test_the_port_follows_the_security_mode_unless_given(security, port):
    env = BASE | ({"MICROPLATFORM_SMTP_SECURITY": security} if security else {})
    settings = EmailSettings.from_env(env)
    assert settings.port == port and settings.security == (security or "starttls").lower()
    assert EmailSettings.from_env(env | {"MICROPLATFORM_SMTP_PORT": "2525"}).port == 2525


def test_an_unknown_security_mode_is_refused():
    with pytest.raises(ValueError, match="starttls, ssl, none"):
        EmailSettings.from_env(BASE | {"MICROPLATFORM_SMTP_SECURITY": "tls1.3"})


def test_settings_file_in_the_instance_and_the_environment_wins(tmp_path):
    (tmp_path / "email.env").write_text(
        "# laptop settings\n"
        "MICROPLATFORM_SMTP_HOST = smtp.file.ac.il\n"
        "MICROPLATFORM_SMTP_SENDER='platform@file.ac.il'\n"
        "MICROPLATFORM_SMTP_USER=fileuser\n"
        'MICROPLATFORM_SMTP_PASSWORD="se=cret"\n'
        "MICROPLATFORM_SMTP_PORT=\n"
        "OTHER_SETTING=ignored\n", encoding="utf-8")
    from_file = EmailSettings.load(tmp_path, env={})
    assert (from_file.host, from_file.sender, from_file.user, from_file.password, from_file.port) == \
        ("smtp.file.ac.il", "platform@file.ac.il", "fileuser", "se=cret", 587)
    overridden = EmailSettings.load(tmp_path, env={"MICROPLATFORM_SMTP_HOST": "smtp.env.ac.il",
                                                   "MICROPLATFORM_SMTP_USER": ""})  # empty does not erase
    assert overridden.host == "smtp.env.ac.il" and overridden.user == "fileuser"


def test_the_password_is_never_shown(tmp_path):
    settings = EmailSettings.from_env(BASE | {"MICROPLATFORM_SMTP_USER": "u", "MICROPLATFORM_SMTP_PASSWORD": "hunter2"})
    assert "hunter2" not in repr(settings) and "hunter2" not in settings.describe()
    assert settings.describe() == "smtp.lab.ac.il:587 (starttls, login as u), from platform@lab.ac.il"


# --- talking to the mail server ---------------------------------------------------------------------

class FakeSMTP:
    calls: list = []

    def __init__(self, host, port, timeout, context=None):
        FakeSMTP.calls.append(("connect", type(self).__name__, host, port, context is not None))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        FakeSMTP.calls.append(("quit",))

    def starttls(self, context=None):
        FakeSMTP.calls.append(("starttls", context is not None))

    def login(self, user, password):
        FakeSMTP.calls.append(("login", user, password))

    def send_message(self, message):
        FakeSMTP.calls.append(("send", message["From"], message["To"], message["Subject"], message.get_content()))


class FakeSMTPSSL(FakeSMTP):
    pass


@pytest.fixture
def mail_server(monkeypatch):
    FakeSMTP.calls = []
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr("smtplib.SMTP_SSL", FakeSMTPSSL)
    return FakeSMTP.calls


def test_starttls_with_login_sends_the_link_only(mail_server):
    subject, body = finished_message("data.csv", "done", "https://site/runs/abc")
    EmailNotifier(EmailSettings("smtp.lab", "from@lab", 587, "u", "p")).send("to@lab", subject, body)
    assert mail_server[0] == ("connect", "FakeSMTP", "smtp.lab", 587, False)
    assert ("starttls", True) in mail_server and ("login", "u", "p") in mail_server  # certificate checked
    send = next(c for c in mail_server if c[0] == "send")
    assert send[1:4] == ("from@lab", "to@lab", "Your microbiome analysis is ready")
    assert "https://site/runs/abc" in send[4]


def test_ssl_connects_encrypted_from_the_start(mail_server):
    EmailNotifier(EmailSettings("smtp.lab", "from@lab", 465, security="ssl")).send("to@lab", "s", "b")
    assert mail_server[0] == ("connect", "FakeSMTPSSL", "smtp.lab", 465, True)
    assert not any(c[0] in ("starttls", "login") for c in mail_server)  # no STARTTLS, no login without a user


def test_none_sends_without_encryption(mail_server):
    EmailNotifier(EmailSettings("relay.lab", "from@lab", 25, security="none")).send("to@lab", "s", "b")
    assert mail_server[0][1] == "FakeSMTP" and not any(c[0] == "starttls" for c in mail_server)


# --- the test command -------------------------------------------------------------------------------

def test_the_test_command_says_when_email_is_off(tmp_path, capsys, monkeypatch):
    for name in [n for n in __import__("os").environ if n.startswith("MICROPLATFORM_SMTP_")]:
        monkeypatch.delenv(name)
    assert notify.main(["--to", "me@lab.ac.il", "--instance", str(tmp_path)]) == 1
    assert "Email is OFF" in capsys.readouterr().err


def test_the_test_command_sends_one_email_and_never_prints_the_password(tmp_path, capsys, mail_server, monkeypatch):
    for name in [n for n in __import__("os").environ if n.startswith("MICROPLATFORM_SMTP_")]:
        monkeypatch.delenv(name)
    (tmp_path / "email.env").write_text(
        "MICROPLATFORM_SMTP_HOST=smtp.lab\nMICROPLATFORM_SMTP_SENDER=from@lab\n"
        "MICROPLATFORM_SMTP_USER=u\nMICROPLATFORM_SMTP_PASSWORD=hunter2\n", encoding="utf-8")
    assert notify.main(["--to", "me@lab.ac.il", "--instance", str(tmp_path)]) == 0
    out = capsys.readouterr()
    assert "Sent." in out.out and "hunter2" not in out.out + out.err
    assert next(c for c in mail_server if c[0] == "send")[2] == "me@lab.ac.il"


# --- never in Git ---------------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["instance/email.env", "deploy/email.env", "deploy/microplatform.env", ".env"])
def test_real_settings_files_are_ignored_by_git(path):
    assert subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode == 0, path


def test_the_templates_hold_no_secret_values():
    for name in ("deploy/email.env.example", "deploy/microplatform.env.example"):
        lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
        for line in lines:
            if line.startswith(("MICROPLATFORM_SMTP_PASSWORD", "MICROPLATFORM_SMTP_USER", "MICROPLATFORM_SMTP_HOST",
                                "MICROPLATFORM_SMTP_SENDER")):
                assert line.endswith("="), (name, line)  # empty: the real value goes only in the real file
