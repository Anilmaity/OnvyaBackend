from django.urls import path

from apps.payments.webhooks import modulr_webhook


urlpatterns = [
    path("webhooks/modulr/", modulr_webhook, name="modulr-webhook"),
]
