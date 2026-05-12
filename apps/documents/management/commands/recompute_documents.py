from django.core.management.base import BaseCommand

from apps.agencies.models import Agency
from apps.common.context import agency_context
from apps.documents.services import DocumentService


class Command(BaseCommand):
    help = "Recompute DriverDocument.status across all agencies."

    def handle(self, *args, **opts):
        total = 0
        for agency in Agency.objects.all():
            with agency_context(agency):
                changed = DocumentService.recompute_all(agency)
                total += changed
                self.stdout.write(f"{agency.slug}: {changed} updated")
        self.stdout.write(self.style.SUCCESS(f"Done. {total} rows changed."))
