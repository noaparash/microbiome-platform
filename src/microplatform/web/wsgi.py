"""WSGI entry point for production servers. It only imports the app:

    gunicorn -c deploy/gunicorn.conf.py microplatform.web.wsgi:app

On a server the website only queues analyses (``MICROPLATFORM_JOBS=external``,
the default here); ``python -m microplatform.worker`` runs them. A fixed
``MICROPLATFORM_SECRET_KEY`` is required: with several gunicorn workers, a
random key per process would break sessions and messages.
"""

from __future__ import annotations

import os

from microplatform.web import create_app

os.environ.setdefault("MICROPLATFORM_JOBS", "external")
if not os.environ.get("MICROPLATFORM_SECRET_KEY"):
    raise RuntimeError(
        "MICROPLATFORM_SECRET_KEY is not set. Put a long random value in the server's settings file "
        "(see deploy/microplatform.env.example), e.g. from: python -c \"import secrets; print(secrets.token_hex(32))\""
    )

app = create_app()
