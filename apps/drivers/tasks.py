import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from apps.common.context import agency_context
from apps.drivers.models import Driver

logger = logging.getLogger(__name__)


@shared_task
def send_driver_registration_email(driver_id):
    driver = Driver.all_objects.get(id=driver_id)
    with agency_context(driver.agency):
        if not driver.registration_code:
            return
        subject = "Your Omnio driver registration code"
        body = (
            f"Hi {driver.first_name},\n\n"
            f"Your registration code is: {driver.registration_code}\n\n"
            f"Download the Omnio app and register using your email address and this code.\n\n"
            f"— Omnio"
        )
        try:
            send_mail(
                subject, body, settings.DEFAULT_FROM_EMAIL, [driver.email],
                fail_silently=False,
            )
        except Exception:
            logger.exception("Failed to send registration email for driver %s", driver_id)
