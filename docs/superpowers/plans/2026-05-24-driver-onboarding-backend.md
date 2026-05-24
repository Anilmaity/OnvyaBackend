# Driver Onboarding — Backend Implementation Plan (Phase A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add driver self-service onboarding to the Graphene API so the mobile wizard can persist personal details, vehicle details, NI/DBS consent, documents, and submit for review.

**Architecture:** New `apps/vehicles` app (`Vehicle` OneToOne→Driver); add `dbs_consent`/`dbs_consent_at` to `Driver`; extend `ApplicationDocument.Kind`. Add self-service mutations following the `UpsertDriverBankAccount` pattern (no `@permission_required`; inline `is_self` check via `user.driver_profile`). Existing 6-step model + `submit_for_review` gate unchanged; DVLA/RTW/OCR already pass inline because `CELERY_TASK_ALWAYS_EAGER=True`.

**Tech Stack:** Django 5, graphene-django, pytest, PostgreSQL (shared RDS via `.env DATABASE_URL`).

**Spec:** `omnio_mobile_app/docs/superpowers/specs/2026-05-24-driver-onboarding-flow-design.md`

**Before you start:**
- Run all commands from `C:\Projects\ClaudeProjects\Omino\OnvyaBackend` with the venv: prefix python as `.\.venv\Scripts\python.exe` and set `$env:DJANGO_SETTINGS_MODULE="config.settings.dev"`.
- Migrations run against the shared RDS — they are **additive only** (new table, new nullable columns, new enum values), safe for the still-deployed hosted code.
- Tests use pytest-django which creates a `test_<db>` database on the RDS server. If the RDS role lacks CREATE DATABASE, run pytest with `--reuse-db` after a one-time manual test DB creation, or point tests at a local Postgres. Surface this immediately if `pytest` can't create the test DB.

---

### Task 1: Create `apps/vehicles` app with `Vehicle` model

**Files:**
- Create: `apps/vehicles/__init__.py` (empty)
- Create: `apps/vehicles/apps.py`
- Create: `apps/vehicles/models.py`
- Create: `apps/vehicles/services.py`
- Create: `apps/vehicles/__init__.py`, `apps/vehicles/migrations/__init__.py` (empty)
- Create: `apps/vehicles/tests/__init__.py` (empty), `apps/vehicles/tests/test_models.py`
- Modify: `config/settings/base.py` (add `"apps.vehicles"` to `INSTALLED_APPS`)

- [ ] **Step 1: Register the app**

In `config/settings/base.py`, add `"apps.vehicles",` to `INSTALLED_APPS` immediately after `"apps.drivers",`.

- [ ] **Step 2: Write `apps/vehicles/apps.py`**

```python
from django.apps import AppConfig


class VehiclesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.vehicles"
```

- [ ] **Step 3: Write `apps/vehicles/models.py`**

```python
from django.db import models
from auditlog.registry import auditlog

from apps.common.models import AgencyScopedModel


class Vehicle(AgencyScopedModel):
    driver = models.OneToOneField(
        "drivers.Driver", on_delete=models.CASCADE, related_name="vehicle"
    )
    registration = models.CharField(max_length=16, blank=True, default="")
    make = models.CharField(max_length=64, blank=True, default="")
    model = models.CharField(max_length=64, blank=True, default="")
    year = models.PositiveIntegerField(null=True, blank=True)
    colour = models.CharField(max_length=32, blank=True, default="")

    def __str__(self):
        return f"{self.registration} ({self.make} {self.model})"


auditlog.register(Vehicle)
```

- [ ] **Step 4: Write `apps/vehicles/services.py`**

```python
from apps.common.services import AgencyScopedService
from apps.vehicles.models import Vehicle


class VehicleService(AgencyScopedService):
    model = Vehicle
```

- [ ] **Step 5: Make + apply the migration**

Run:
```
$env:DJANGO_SETTINGS_MODULE="config.settings.dev"; .\.venv\Scripts\python.exe manage.py makemigrations vehicles
.\.venv\Scripts\python.exe manage.py migrate vehicles
```
Expected: creates `apps/vehicles/migrations/0001_initial.py`; migrate applies it (new `vehicles_vehicle` table).

- [ ] **Step 6: Write the failing test** in `apps/vehicles/tests/test_models.py`

```python
import pytest
from apps.agencies.models import Agency
from apps.common.context import set_current_agency, clear_current_agency
from apps.drivers.factories import DriverFactory
from apps.vehicles.models import Vehicle
from apps.vehicles.services import VehicleService


@pytest.fixture
def agency(db):
    a = Agency.objects.create(name="A", slug="a")
    set_current_agency(a)
    yield a
    clear_current_agency()


def test_vehicle_upsert_one_per_driver(agency):
    d = DriverFactory(agency=agency)
    v = Vehicle(driver=d, registration="LV71 ABC", make="Tesla", model="Model 3", year=2021, colour="Black")
    VehicleService().save(v)
    assert d.vehicle.registration == "LV71 ABC"
    assert d.vehicle.agency_id == agency.id
```

- [ ] **Step 7: Run test**

Run: `.\.venv\Scripts\python.exe -m pytest apps/vehicles/tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```
git add apps/vehicles config/settings/base.py
git commit -m "feat(onboarding): add vehicles app + Vehicle model"
```

---

### Task 2: Add `dbs_consent` fields to `Driver`

**Files:**
- Modify: `apps/drivers/models.py:30` (after `date_of_birth`)
- Test: `apps/drivers/tests/test_models.py` (create if absent; otherwise add a test fn)

- [ ] **Step 1: Add fields** to `apps/drivers/models.py`, right after the `date_of_birth` line:

```python
    dbs_consent = models.BooleanField(default=False)
    dbs_consent_at = models.DateTimeField(null=True, blank=True)
```

- [ ] **Step 2: Make + apply migration**

Run:
```
.\.venv\Scripts\python.exe manage.py makemigrations drivers
.\.venv\Scripts\python.exe manage.py migrate drivers
```
Expected: new migration adding two nullable/defaulted columns.

- [ ] **Step 3: Commit**

```
git add apps/drivers/models.py apps/drivers/migrations
git commit -m "feat(onboarding): add dbs_consent fields to Driver"
```

---

### Task 3: Extend `ApplicationDocument.Kind`

**Files:**
- Modify: `apps/onboarding/models.py` (the `ApplicationDocument.Kind` TextChoices)

- [ ] **Step 1: Add kinds.** In `ApplicationDocument.Kind`, add after the existing members:

```python
        PHV_LICENCE = "PHV_LICENCE"
        INSURANCE = "INSURANCE"
```
(Keep `LICENCE`, `PASSPORT`, `RTW_EVIDENCE`.)

- [ ] **Step 2: Make + apply migration**

Run:
```
.\.venv\Scripts\python.exe manage.py makemigrations onboarding
.\.venv\Scripts\python.exe manage.py migrate onboarding
```
Expected: migration altering `kind` choices (no data change).

- [ ] **Step 3: Commit**

```
git add apps/onboarding/models.py apps/onboarding/migrations
git commit -m "feat(onboarding): add PHV_LICENCE + INSURANCE document kinds"
```

---

### Task 4: Expose `niNumber`, `dbsConsent`, and `vehicle` in the schema

**Files:**
- Create: `apps/vehicles/schema.py`
- Modify: `apps/drivers/schema.py` (DriverType)
- Test: `apps/drivers/tests/test_schema_vehicle.py` (create)

- [ ] **Step 1: Write `apps/vehicles/schema.py`**

```python
from graphene_django import DjangoObjectType

from apps.vehicles.models import Vehicle


class VehicleType(DjangoObjectType):
    class Meta:
        model = Vehicle
        fields = ("id", "registration", "make", "model", "year", "colour")
```

- [ ] **Step 2: Extend `DriverType`** in `apps/drivers/schema.py`.

Add a `vehicle` field + resolver to the `DriverType` class body (alongside `notes`):
```python
    vehicle = graphene.Field("apps.vehicles.schema.VehicleType")

    def resolve_vehicle(self, info):
        try:
            return self.vehicle
        except Exception:
            return None
```
And add `"ni_number", "dbs_consent", "dbs_consent_at",` to the `fields` tuple in `DriverType.Meta`.

- [ ] **Step 3: Write the failing test** in `apps/drivers/tests/test_schema_vehicle.py`

```python
import pytest
from graphene.test import Client
from apps.agencies.models import Agency
from apps.common.context import set_current_agency, clear_current_agency
from apps.accounts.factories import AgencyUserFactory
from apps.drivers.factories import DriverFactory
from apps.vehicles.models import Vehicle
from apps.vehicles.services import VehicleService
from config.schema import schema


@pytest.fixture
def ctx(db):
    a = Agency.objects.create(name="A", slug="a")
    set_current_agency(a)
    user = AgencyUserFactory(agency=a, email="d@a.test", password="x")
    driver = DriverFactory(agency=a, user=user, ni_number="QQ123456C")
    VehicleService().save(Vehicle(driver=driver, registration="LV71 ABC", make="Tesla", model="Model 3", year=2021, colour="Black"))
    class Req: pass
    req = Req(); req.user = user; req.current_agency = a
    yield req
    clear_current_agency()


def test_me_exposes_vehicle_and_ni(ctx):
    q = "query { me { driverProfile { niNumber dbsConsent vehicle { registration make } } } }"
    r = Client(schema).execute(q, context=ctx)
    dp = r["data"]["me"]["driverProfile"]
    assert dp["niNumber"] == "QQ123456C"
    assert dp["vehicle"]["registration"] == "LV71 ABC"
```

- [ ] **Step 4: Run test**

Run: `.\.venv\Scripts\python.exe -m pytest apps/drivers/tests/test_schema_vehicle.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add apps/vehicles/schema.py apps/drivers/schema.py apps/drivers/tests/test_schema_vehicle.py
git commit -m "feat(onboarding): expose niNumber, dbsConsent, vehicle on DriverType"
```

---

### Task 5: Add self-service helpers + `startMyApplication`

**Files:**
- Modify: `apps/onboarding/schema.py` (imports, helper, mutation, register)
- Test: `apps/onboarding/tests/test_self_service.py` (create)

- [ ] **Step 1: Update imports** at the top of `apps/onboarding/schema.py`.

Change the common import line to include `PermissionDenied`:
```python
from apps.common.graphql_types import MutationResult, Success, ValidationError, FieldError, PermissionDenied
```
Add near the other imports:
```python
from django.utils import timezone
from apps.onboarding.services import StepService
```

- [ ] **Step 2: Add the self-service helper** below `_validation` in `apps/onboarding/schema.py`:

```python
def _self_driver(info):
    """Return the authenticated user's own Driver, or None."""
    user = getattr(info.context, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return None
    return getattr(user, "driver_profile", None)
```

- [ ] **Step 3: Add the `StartMyApplication` mutation** in `apps/onboarding/schema.py` (before `class Query`):

```python
class StartMyApplication(graphene.Mutation):
    Output = MutationResult

    def mutate(self, info):
        driver = _self_driver(info)
        if driver is None:
            return PermissionDenied(code="no_driver", message="No driver profile for current user")
        existing = Application.objects.filter(driver=driver).first()
        if existing and existing.state != Application.State.REJECTED:
            return Success(id=str(existing.id), message="already_started")
        try:
            app = ApplicationService().start(driver)
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(app.id), message="started")
```

- [ ] **Step 4: Register** it in the `Mutation` class at the bottom of `apps/onboarding/schema.py`:

```python
    start_my_application = StartMyApplication.Field()
```

- [ ] **Step 5: Write the failing test** in `apps/onboarding/tests/test_self_service.py`

```python
import pytest
from graphene.test import Client
from apps.agencies.models import Agency
from apps.common.context import set_current_agency, clear_current_agency
from apps.accounts.factories import AgencyUserFactory
from apps.drivers.factories import DriverFactory
from apps.onboarding.models import Application
from config.schema import schema


@pytest.fixture
def driver_ctx(db):
    a = Agency.objects.create(name="A", slug="a")
    set_current_agency(a)
    user = AgencyUserFactory(agency=a, email="d@a.test", password="x")
    driver = DriverFactory(agency=a, user=user)
    class Req: pass
    req = Req(); req.user = user; req.current_agency = a
    yield a, user, driver, req
    clear_current_agency()


def _run(q, req, variables=None):
    return Client(schema).execute(q, context=req, variables=variables)


def test_start_my_application_creates_for_self(driver_ctx):
    a, user, driver, req = driver_ctx
    r = _run("mutation { startMyApplication { __typename ... on Success { message } } }", req)
    assert r["data"]["startMyApplication"]["__typename"] == "Success"
    assert Application.objects.filter(driver=driver).exists()


def test_start_my_application_no_profile_denied(db):
    a = Agency.objects.create(name="B", slug="b")
    set_current_agency(a)
    user = AgencyUserFactory(agency=a, email="op@b.test", password="x")
    class Req: pass
    req = Req(); req.user = user; req.current_agency = a
    r = _run("mutation { startMyApplication { __typename } }", req)
    clear_current_agency()
    assert r["data"]["startMyApplication"]["__typename"] == "PermissionDenied"
```

- [ ] **Step 6: Run tests**

Run: `.\.venv\Scripts\python.exe -m pytest apps/onboarding/tests/test_self_service.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```
git add apps/onboarding/schema.py apps/onboarding/tests/test_self_service.py
git commit -m "feat(onboarding): startMyApplication self-service mutation"
```

---

### Task 6: `saveMyPersonalDetails`

**Files:**
- Modify: `apps/onboarding/schema.py`
- Test: `apps/onboarding/tests/test_self_service.py` (append)

- [ ] **Step 1: Add the mutation** (before `class Query`):

```python
class SaveMyPersonalDetails(graphene.Mutation):
    class Arguments:
        first_name = graphene.String(required=True)
        last_name = graphene.String(required=True)
        phone = graphene.String()
        date_of_birth = graphene.Date()

    Output = MutationResult

    def mutate(self, info, first_name, last_name, phone=None, date_of_birth=None):
        driver = _self_driver(info)
        if driver is None:
            return PermissionDenied(code="no_driver", message="No driver profile for current user")
        app = Application.objects.filter(driver=driver).first()
        if app is None:
            return _validation("application", "No application; start onboarding first")
        driver.first_name = first_name
        driver.last_name = last_name
        if phone is not None:
            driver.phone = phone
        if date_of_birth is not None:
            driver.date_of_birth = date_of_birth
        driver.save()
        step = Step.objects.filter(application=app, kind=Step.Kind.PERSONAL_DETAILS).first()
        if step is not None:
            step.outcome = {
                **(step.outcome or {}),
                "first_name": first_name, "last_name": last_name,
                "phone": phone or "", "date_of_birth": str(date_of_birth) if date_of_birth else None,
            }
            step.status = Step.Status.PASSED
            step.completed_at = timezone.now()
            StepService().save(step)
        return Success(id=str(driver.id), message="personal_details_saved")
```

- [ ] **Step 2: Register** in `Mutation`:

```python
    save_my_personal_details = SaveMyPersonalDetails.Field()
```

- [ ] **Step 3: Add the failing test** to `apps/onboarding/tests/test_self_service.py`:

```python
def test_save_my_personal_details(driver_ctx):
    a, user, driver, req = driver_ctx
    _run("mutation { startMyApplication { __typename } }", req)
    q = 'mutation { saveMyPersonalDetails(firstName:"Jane", lastName:"Doe", phone:"7123456789") { __typename ... on Success { message } } }'
    r = _run(q, req)
    assert r["data"]["saveMyPersonalDetails"]["__typename"] == "Success"
    driver.refresh_from_db()
    assert driver.first_name == "Jane" and driver.phone == "7123456789"
```

- [ ] **Step 4: Run + commit**

Run: `.\.venv\Scripts\python.exe -m pytest apps/onboarding/tests/test_self_service.py -v` (PASS), then:
```
git add apps/onboarding/schema.py apps/onboarding/tests/test_self_service.py
git commit -m "feat(onboarding): saveMyPersonalDetails self-service mutation"
```

---

### Task 7: `saveMyVehicle`

**Files:**
- Modify: `apps/onboarding/schema.py`
- Test: `apps/onboarding/tests/test_self_service.py` (append)

- [ ] **Step 1: Add the mutation:**

```python
class SaveMyVehicle(graphene.Mutation):
    class Arguments:
        registration = graphene.String(required=True)
        make = graphene.String(required=True)
        model = graphene.String(required=True)
        year = graphene.Int()
        colour = graphene.String()

    Output = MutationResult

    def mutate(self, info, registration, make, model, year=None, colour=None):
        driver = _self_driver(info)
        if driver is None:
            return PermissionDenied(code="no_driver", message="No driver profile for current user")
        from apps.vehicles.models import Vehicle
        from apps.vehicles.services import VehicleService
        v = Vehicle.objects.filter(driver=driver).first() or Vehicle(driver=driver)
        v.registration = registration
        v.make = make
        v.model = model
        v.year = year
        v.colour = colour or ""
        VehicleService().save(v)
        return Success(id=str(v.id), message="vehicle_saved")
```

- [ ] **Step 2: Register** in `Mutation`: `save_my_vehicle = SaveMyVehicle.Field()`

- [ ] **Step 3: Add the failing test:**

```python
def test_save_my_vehicle_upsert(driver_ctx):
    a, user, driver, req = driver_ctx
    _run("mutation { startMyApplication { __typename } }", req)
    q = 'mutation { saveMyVehicle(registration:"LV71 ABC", make:"Tesla", model:"Model 3", year:2021, colour:"Black") { __typename } }'
    assert _run(q, req)["data"]["saveMyVehicle"]["__typename"] == "Success"
    driver.refresh_from_db()
    assert driver.vehicle.make == "Tesla"
```

- [ ] **Step 4: Run + commit**

Run pytest (PASS), then:
```
git add apps/onboarding/schema.py apps/onboarding/tests/test_self_service.py
git commit -m "feat(onboarding): saveMyVehicle self-service mutation"
```

---

### Task 8: `saveMyBackgroundCheck`

**Files:**
- Modify: `apps/onboarding/schema.py`
- Test: `apps/onboarding/tests/test_self_service.py` (append)

- [ ] **Step 1: Add the mutation:**

```python
class SaveMyBackgroundCheck(graphene.Mutation):
    class Arguments:
        ni_number = graphene.String(required=True)
        dbs_consent = graphene.Boolean(required=True)

    Output = MutationResult

    def mutate(self, info, ni_number, dbs_consent):
        driver = _self_driver(info)
        if driver is None:
            return PermissionDenied(code="no_driver", message="No driver profile for current user")
        if not dbs_consent:
            return _validation("dbs_consent", "DBS consent is required to proceed")
        driver.ni_number = ni_number
        driver.dbs_consent = True
        driver.dbs_consent_at = timezone.now()
        driver.save()
        return Success(id=str(driver.id), message="background_saved")
```

- [ ] **Step 2: Register** in `Mutation`: `save_my_background_check = SaveMyBackgroundCheck.Field()`

- [ ] **Step 3: Add the failing test:**

```python
def test_save_my_background_check(driver_ctx):
    a, user, driver, req = driver_ctx
    _run("mutation { startMyApplication { __typename } }", req)
    q = 'mutation { saveMyBackgroundCheck(niNumber:"QQ123456C", dbsConsent:true) { __typename } }'
    assert _run(q, req)["data"]["saveMyBackgroundCheck"]["__typename"] == "Success"
    driver.refresh_from_db()
    assert driver.ni_number == "QQ123456C" and driver.dbs_consent is True


def test_background_check_requires_consent(driver_ctx):
    a, user, driver, req = driver_ctx
    _run("mutation { startMyApplication { __typename } }", req)
    q = 'mutation { saveMyBackgroundCheck(niNumber:"QQ123456C", dbsConsent:false) { __typename } }'
    assert _run(q, req)["data"]["saveMyBackgroundCheck"]["__typename"] == "ValidationError"
```

- [ ] **Step 4: Run + commit**

Run pytest (PASS), then:
```
git add apps/onboarding/schema.py apps/onboarding/tests/test_self_service.py
git commit -m "feat(onboarding): saveMyBackgroundCheck self-service mutation"
```

---

### Task 9: Make `uploadApplicationDocument` self-service-callable

**Files:**
- Modify: `apps/onboarding/schema.py` (the `UploadApplicationDocument.mutate`)
- Test: `apps/onboarding/tests/test_self_service.py` (append)

- [ ] **Step 1: Replace the mutate method** of `UploadApplicationDocument`. Remove the `@permission_required("applications.update")` decorator and use:

```python
    def mutate(self, info, application_id, kind, file):
        app = Application.objects.filter(id=application_id).first()
        if app is None:
            return _validation("application_id", "Application not found")
        user = getattr(info.context, "user", None)
        is_self = (
            user is not None
            and getattr(user, "driver_profile", None) is not None
            and str(user.driver_profile.id) == str(app.driver_id)
        )
        if not is_self:
            from apps.common.permissions import has_permission
            if not has_permission(user, "applications.update"):
                return PermissionDenied(code="permission_denied", message="applications.update required")
        try:
            doc = ApplicationService().upload_document(app, kind, file)
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(doc.id), message="uploaded")
```

- [ ] **Step 2: Add the failing test:**

```python
from django.core.files.uploadedfile import SimpleUploadedFile

def test_driver_uploads_to_own_application(driver_ctx):
    a, user, driver, req = driver_ctx
    from apps.onboarding.services import ApplicationService
    app = ApplicationService().start(driver)
    f = SimpleUploadedFile("l.pdf", b"x", content_type="application/pdf")
    r = Client(schema).execute(
        'mutation($f: Upload!) { uploadApplicationDocument(applicationId: "%s", kind: "LICENCE", file: $f) { __typename } }' % app.id,
        context=req, variables={"f": f},
    )
    assert r["data"]["uploadApplicationDocument"]["__typename"] == "Success"
```

- [ ] **Step 3: Run + commit**

Run pytest (PASS — also re-run `apps/onboarding/tests/test_mutations.py` to confirm operator path still works via the `has_permission` fallback), then:
```
git add apps/onboarding/schema.py apps/onboarding/tests/test_self_service.py
git commit -m "feat(onboarding): allow drivers to upload docs to their own application"
```

---

### Task 10: `submitMyApplication`

**Files:**
- Modify: `apps/onboarding/schema.py`
- Test: `apps/onboarding/tests/test_self_service.py` (append)

- [ ] **Step 1: Add the mutation:**

```python
class SubmitMyApplication(graphene.Mutation):
    Output = MutationResult

    def mutate(self, info):
        driver = _self_driver(info)
        if driver is None:
            return PermissionDenied(code="no_driver", message="No driver profile for current user")
        app = Application.objects.filter(driver=driver).first()
        if app is None:
            return _validation("application", "No application to submit")
        try:
            ApplicationService().submit_for_review(app)
        except IllegalTransition as e:
            return _validation("state", str(e))
        return Success(id=str(app.id), message="submitted")
```

- [ ] **Step 2: Register** in `Mutation`: `submit_my_application = SubmitMyApplication.Field()`

- [ ] **Step 3: Add the failing test** (full happy path — relies on eager Celery passing DVLA/RTW/OCR):

```python
def test_submit_my_application_happy(driver_ctx):
    a, user, driver, req = driver_ctx
    from apps.onboarding.services import ApplicationService
    from apps.onboarding.models import Application
    app = ApplicationService().start(driver)
    f = SimpleUploadedFile("l.pdf", b"x", content_type="application/pdf")
    ApplicationService().upload_document(app, "LICENCE", f)
    r = _run("mutation { submitMyApplication { __typename ... on Success { message } } }", req)
    assert r["data"]["submitMyApplication"]["__typename"] == "Success"
    app.refresh_from_db()
    assert app.state == Application.State.PENDING_REVIEW
```

- [ ] **Step 4: Run + commit**

Run pytest (PASS), then:
```
git add apps/onboarding/schema.py apps/onboarding/tests/test_self_service.py
git commit -m "feat(onboarding): submitMyApplication self-service mutation"
```

---

### Task 11: Management command to prepare the demo driver

The mobile flow needs `driver@demo.test` to (a) have a linked `driver_profile`, and (b) start from a clean state. This command is idempotent and reusable for "start from start" testing.

**Files:**
- Create: `apps/onboarding/management/__init__.py`, `apps/onboarding/management/commands/__init__.py` (empty, if absent)
- Create: `apps/onboarding/management/commands/reset_driver_onboarding.py`

- [ ] **Step 1: Write the command:**

```python
from django.core.management.base import BaseCommand

from apps.agencies.models import Agency
from apps.accounts.models import AgencyUser
from apps.common.context import agency_context
from apps.drivers.models import Driver
from apps.onboarding.models import Application


class Command(BaseCommand):
    help = "Ensure a driver user has a linked Driver profile and a clean (no) application."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="driver@demo.test")
        parser.add_argument("--agency", default="demo")

    def handle(self, *args, **opts):
        agency = Agency.objects.get(slug=opts["agency"])
        with agency_context(agency):
            user = AgencyUser.all_objects.filter(agency=agency, email=opts["email"]).first()
            if user is None:
                self.stderr.write(f"No user {opts['email']} in agency {agency.slug}")
                return
            driver = Driver.objects.filter(agency=agency, user=user).first()
            if driver is None:
                driver = Driver.objects.filter(agency=agency, email=opts["email"]).first()
                if driver is None:
                    driver = Driver(agency=agency, email=opts["email"],
                                    first_name=user.first_name or "Test",
                                    last_name=user.last_name or "Driver",
                                    status=Driver.Status.PENDING)
                driver.user = user
                driver.save()
            Application.objects.filter(driver=driver).delete()
            self.stdout.write(self.style.SUCCESS(
                f"Driver {driver.id} linked to {user.email}; application cleared."))
```

- [ ] **Step 2: Run it** against the shared dev DB:

```
.\.venv\Scripts\python.exe manage.py reset_driver_onboarding --email driver@demo.test --agency demo
```
Expected: "Driver <id> linked ...; application cleared." (If agency slug differs, pass `--agency <slug>`.)

- [ ] **Step 3: Verify** via the hosted/local API that `me.driverProfile` is non-null and `myApplication` is null for `driver@demo.test`.

- [ ] **Step 4: Commit**

```
git add apps/onboarding/management
git commit -m "chore(onboarding): reset_driver_onboarding management command"
```

---

### Task 12: Full backend test pass + run server

- [ ] **Step 1: Run the full onboarding + drivers + vehicles suites**

Run: `.\.venv\Scripts\python.exe -m pytest apps/onboarding apps/drivers apps/vehicles -v`
Expected: all PASS (no regressions in `test_mutations.py`).

- [ ] **Step 2: Start the local server on :8001 for mobile e2e**

Run: `$env:DJANGO_SETTINGS_MODULE="config.settings.dev"; .\.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8001`
Expected: serving at `http://0.0.0.0:8001/graphql/`. Leave running for Phase B (mobile) e2e.

- [ ] **Step 3: Smoke-test a self-service mutation** with the driver token (PowerShell/curl), confirming `startMyApplication` returns `Success` for `driver@demo.test`.

---

## Self-Review Notes
- Spec coverage: Vehicle model (T1), dbs_consent (T2), doc kinds (T3), schema exposure (T4), start/personal/vehicle/background/upload/submit mutations (T5–T10), driver profile/seed prep (T11), eager Celery already on (base.py:160, no task needed), test pass (T12). ✓
- All mutations follow the inline `is_self` pattern (no `@permission_required`) so the zero-permission Driver role can self-serve. ✓
- Migrations additive only — safe for the shared RDS + deployed hosted code. ✓
