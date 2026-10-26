"""gunicorn settings for the Microbiome Platform website (see docs/deployment.he.md).

The website only shows pages and queues analyses; the heavy work runs in the
separate worker service. So a few web processes with short timeouts are enough.
"""

import os

# Listen only on the server itself: nginx (HTTPS) is the only way in from outside.
bind = os.environ.get("MICROPLATFORM_BIND", "127.0.0.1:8000")

# 2 processes × 4 threads handles a lab comfortably; raise MICROPLATFORM_WEB_WORKERS if many users.
workers = int(os.environ.get("MICROPLATFORM_WEB_WORKERS", "2"))
worker_class = "gthread"
threads = 4

# Long enough for a 100 MB upload on a slow connection; analyses never run inside a request.
timeout = 120
graceful_timeout = 30
keepalive = 5

# Restart each process now and then, to keep memory steady over months.
max_requests = 1000
max_requests_jitter = 100

# Logs go to the system journal (journalctl -u microplatform-web). The access log leaves out
# the requested address: a run's address is its key, so it must not sit in logs.
accesslog = "-"
access_log_format = '%(h)s %(t)s "%(m)s" %(s)s %(B)s %(L)ss'
errorlog = "-"
loglevel = "info"

# Only trust forwarded headers from nginx on this machine.
forwarded_allow_ips = "127.0.0.1"
