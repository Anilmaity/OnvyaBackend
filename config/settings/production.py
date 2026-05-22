"""Production settings for the Onvya backend.

Activate by setting the OS/process environment variable (systemd unit, Docker
env, or gunicorn env — NOT just .env, which is loaded too late to choose the
settings module):

    DJANGO_SETTINGS_MODULE=config.settings.production

Backend host  : https://onvya.algorobos.com
Frontend (CORS): https://onvya.netlify.app

Every value below can be overridden with an environment variable; the defaults
are the live deployment domains so the service works without extra config.
"""
import os

from corsheaders.defaults import default_headers

from .base import *  # noqa

def _csv_env(name):
    """Comma-separated env var -> clean list (empty entries dropped)."""
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


# --- Core -------------------------------------------------------------------
DEBUG = False

# Always serve the production host. base.py's load_dotenv() pulls the dev .env
# values into the environment, so we can't use a simple "if unset" fallback —
# we force the production host and merge any extras supplied via ALLOWED_HOSTS.
ALLOWED_HOSTS = list(dict.fromkeys(["onvya.algorobos.com", *_csv_env("ALLOWED_HOSTS")]))

# --- CORS (which front-end origins may call the API) ------------------------
# Tenant resolution is via the JWT agency_id claim and auth is a bearer token
# in the Authorization header (see apps.common.middleware.AgencyContextMiddleware),
# so there are no cross-site cookies and credentials stay off.
#
# Always allow the production frontend; CORS_ALLOWED_ORIGINS may add more, but
# only https:// origins are honoured so leftover http://localhost dev entries
# in a copied .env can't widen production CORS.
_cors_extra = [o for o in _csv_env("CORS_ALLOWED_ORIGINS") if o.startswith("https://")]
CORS_ALLOWED_ORIGINS = list(dict.fromkeys(["https://onvya.netlify.app", *_cors_extra]))

# Also allow Netlify branch / deploy-preview subdomains
# (e.g. deploy-preview-12--onvya.netlify.app) without listing each one.
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://([a-z0-9-]+--)?onvya\.netlify\.app$",
]

CORS_ALLOW_CREDENTIALS = os.environ.get("CORS_ALLOW_CREDENTIALS", "False") == "True"
CORS_ALLOW_HEADERS = list(default_headers) + ["apollo-require-preflight"]

# --- CSRF (admin login + any cookie-bearing POST over HTTPS) ----------------
# GraphQL is csrf_exempt and JWT-authenticated, so this mainly protects the
# Django admin, which is served from the backend host.
_csrf_extra = [o for o in _csv_env("CSRF_TRUSTED_ORIGINS") if o.startswith("https://")]
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys([
    "https://onvya.algorobos.com",
    "https://onvya.netlify.app",
    *_csrf_extra,
]))

# --- HTTPS / proxy hardening ------------------------------------------------
# The app sits behind a TLS-terminating reverse proxy that sets
# X-Forwarded-Proto. If yours does not, set SECURE_SSL_REDIRECT=False to avoid
# a redirect loop.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "True") == "True"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# --- Safety guard -----------------------------------------------------------
# Refuse to boot production on the shared development secret.
if SECRET_KEY == "dev-not-secret-change-me":
    raise RuntimeError(
        "SECRET_KEY is still the development default. Set a real SECRET_KEY "
        "environment variable before deploying to production."
    )
