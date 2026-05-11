from .base import *  # noqa

DEBUG = True
ALLOWED_HOSTS = ["*"]
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

GRAPHENE = {
    "SCHEMA": "config.schema.schema",
    "MIDDLEWARE": [],
}

if not CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS = [
        "http://localhost:3000",
        "http://localhost:8081",
        "http://127.0.0.1:3000",
    ]
