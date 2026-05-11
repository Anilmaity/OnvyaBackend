from django.core.management.base import BaseCommand

from apps.agencies.models import Agency, Depot
from apps.accounts.models import AgencyUser, Role, Permission, RolePermission, UserRole
from apps.accounts.data.permission_catalogue import PERMISSIONS, ROLE_MATRIX
from apps.drivers.models import Driver
from apps.onboarding.services import ApplicationService
from apps.common.context import agency_context


class Command(BaseCommand):
    help = "Seed a minimal demo agency, admin user, driver user, and in-flight application."

    def handle(self, *args, **opts):
        # 1. Permissions
        for code, desc in PERMISSIONS:
            Permission.objects.get_or_create(code=code, defaults={"description": desc})

        # 2. Agency
        agency, created = Agency.objects.get_or_create(
            slug="demo",
            defaults={"name": "Demo Agency", "timezone": "Europe/London"},
        )
        if created:
            self.stdout.write(f"Created Agency: {agency.name}")

        with agency_context(agency):
            # 3. Roles + role permissions
            for role_name, codes in ROLE_MATRIX.items():
                role, _ = Role.objects.get_or_create(
                    agency=agency, name=role_name,
                    defaults={"is_system": True, "description": f"System role: {role_name}"},
                )
                existing = set(role.role_permissions.values_list("permission__code", flat=True))
                for code in codes - existing:
                    perm = Permission.objects.get(code=code)
                    RolePermission.objects.get_or_create(role=role, permission=perm)

            # 4. Depot
            Depot.objects.get_or_create(agency=agency, name="London North", defaults={"address": "Demo address"})

            # 5. Admin user
            admin_email = "admin@demo.test"
            admin = AgencyUser.all_objects.filter(agency=agency, email=admin_email).first()
            if admin is None:
                admin = AgencyUser(
                    agency=agency, email=admin_email,
                    first_name="Demo", last_name="Admin",
                    is_active=True, is_staff=True, is_superuser=True,
                )
                admin.set_password("demo1234")
                admin.save()
                self.stdout.write(f"Created admin user: {admin_email} / demo1234")
            super_role = Role.objects.get(agency=agency, name="Super Admin")
            UserRole.objects.get_or_create(user=admin, role=super_role)

            # 6. Driver user
            driver_email = "driver@demo.test"
            driver_user = AgencyUser.all_objects.filter(agency=agency, email=driver_email).first()
            if driver_user is None:
                driver_user = AgencyUser(
                    agency=agency, email=driver_email,
                    first_name="Test", last_name="Driver",
                    is_active=True,
                )
                driver_user.set_password("demo1234")
                driver_user.save()
            driver_role = Role.objects.get(agency=agency, name="Driver")
            UserRole.objects.get_or_create(user=driver_user, role=driver_role)

            # 7. Driver row
            driver, _ = Driver.objects.get_or_create(
                agency=agency, email=driver_email,
                defaults={
                    "first_name": "Test", "last_name": "Driver",
                    "status": Driver.Status.PENDING,
                    "user": driver_user,
                },
            )

            # 8. In-flight application (idempotent — skip if exists)
            if not hasattr(driver, "application"):
                ApplicationService().start(driver)
                self.stdout.write("Created in-flight application for demo driver")

        self.stdout.write(self.style.SUCCESS("seed_minimal complete"))
