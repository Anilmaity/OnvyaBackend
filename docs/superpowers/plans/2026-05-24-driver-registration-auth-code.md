# Driver Registration Auth Code Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a console user creates a driver, the backend mints a reusable 6-digit registration code, pre-creates a disabled login, emails the code to the driver, and the console driver detail page shows the code with a copy button.

**Architecture:** Add a `registration_code` field to `Driver`. `DriverService.create` generates the code, pre-creates a disabled `AgencyUser` (Driver role, unusable password) linked to the driver, and fires a Celery task that emails the code (eager/inline in dev → printed to the console email backend). `DriverType` exposes `registrationCode` + a derived `registered` boolean, gated by the existing `drivers.read` permission. The console driver detail page shows the code copyable while the driver is not yet registered. Consuming the code (activation) and the mobile Register screen are out of scope.

**Tech Stack:** Django 5, graphene-django, Celery (eager in dev), pytest-django, factory-boy; Next.js 14 / React (console display).

**Spec:** `docs/superpowers/specs/2026-05-24-driver-registration-auth-code-design.md`

**Working dir:** Run all backend commands from `C:\Projects\ClaudeProjects\Omino\OnvyaBackend`. Use the venv Python: `.venv\Scripts\python.exe`. Console commands run from `C:\Projects\ClaudeProjects\Omino\omnio_management_console`.

**Branch:** Backend is on `feat/driver-onboarding`. Commit each task with explicit file paths (the branch has unrelated in-progress changes — never `git add -A`).

---

## File Structure

**Backend (`OnvyaBackend/`):**
- Modify `apps/drivers/models.py` — add `registration_code` field.
- Create `apps/drivers/migrations/000X_driver_registration_code.py` — generated.
- Modify `config/settings/base.py` — add `DEFAULT_FROM_EMAIL`.
- Modify `apps/drivers/services.py` — code generation + pre-create disabled login + fire email.
- Create `apps/drivers/tasks.py` — `send_driver_registration_email` Celery task.
- Modify `apps/drivers/schema.py` — expose `registration_code` + `registered` on `DriverType`.
- Create `apps/drivers/tests/test_registration_code.py` — backend tests.

**Console (`omnio_management_console/`):**
- Modify `app/(console)/drivers/mutations.ts` — add `registrationCode registered` to `DRIVER_DETAIL`.
- Modify `app/(console)/drivers/[id]/page.tsx` — render copyable code row.

---

## Task 1: Add `registration_code` field + email setting

**Files:**
- Modify: `apps/drivers/models.py` (the `Driver` class)
- Modify: `config/settings/base.py`
- Create (generated): `apps/drivers/migrations/000X_driver_registration_code.py`

- [ ] **Step 1: Add the field to the `Driver` model**

In `apps/drivers/models.py`, inside `class Driver(AgencyScopedModel)`, add this line immediately after the `offboard_reason` field (around line 37):

```python
    registration_code = models.CharField(max_length=6, blank=True, default="")
```

- [ ] **Step 2: Add `DEFAULT_FROM_EMAIL` to settings**

In `config/settings/base.py`, add this line immediately after the `CSRF_TRUSTED_ORIGINS = [...]` line (around line 157):

```python
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "no-reply@onvya.local")
```

- [ ] **Step 3: Generate the migration**

Run: `.venv\Scripts\python.exe manage.py makemigrations drivers`
Expected: `Migrations for 'drivers':` followed by a new file `apps/drivers/migrations/000X_driver_registration_code.py` containing `Add field registration_code to driver`.

- [ ] **Step 4: Apply the migration**

Run: `.venv\Scripts\python.exe manage.py migrate drivers`
Expected: `Applying drivers.000X_driver_registration_code... OK`

- [ ] **Step 5: Verify the field exists**

Run:
```
.venv\Scripts\python.exe manage.py shell -c "from apps.drivers.models import Driver; print('registration_code' in [f.name for f in Driver._meta.get_fields()])"
```
Expected: `True`

- [ ] **Step 6: Commit**

```bash
git add apps/drivers/models.py config/settings/base.py apps/drivers/migrations/0003_driver_registration_code.py
git commit -m "feat(drivers): add registration_code field + DEFAULT_FROM_EMAIL setting"
```
(The generated migration should be `0003_driver_registration_code.py` — it follows the existing `0002_driver_dbs_consent...`. Adjust if Django names it differently.)

---

## Task 2: Generate code + pre-create disabled login in `DriverService.create`

**Files:**
- Modify: `apps/drivers/services.py` (`DriverService.create`)
- Test: `apps/drivers/tests/test_registration_code.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `apps/drivers/tests/test_registration_code.py`:

```python
import re

import pytest

from apps.agencies.models import Agency
from apps.accounts.models import AgencyUser, Role
from apps.drivers.models import Driver
from apps.drivers.services import DriverService
from apps.common.context import set_current_agency, clear_current_agency


@pytest.fixture
def agency_ctx(db):
    agency = Agency.objects.create(name="A", slug="a")
    Role.objects.create(agency=agency, name="Driver")
    set_current_agency(agency)
    yield agency
    clear_current_agency()


def test_create_generates_6_digit_code(agency_ctx):
    d = DriverService().create(first_name="A", last_name="B", email="ab@a.test")
    assert re.fullmatch(r"\d{6}", d.registration_code)


def test_create_makes_disabled_login_with_driver_role(agency_ctx):
    d = DriverService().create(first_name="A", last_name="B", email="ab@a.test")
    assert d.user is not None
    assert d.user.is_active is False
    assert d.user.has_usable_password() is False
    assert d.user.user_roles.filter(role__name="Driver").exists()


def test_create_links_existing_user_not_duplicate(agency_ctx):
    existing = AgencyUser(
        agency=agency_ctx, email="ab@a.test",
        first_name="A", last_name="B", is_active=False,
    )
    existing.set_unusable_password()
    existing.save()
    d = DriverService().create(first_name="A", last_name="B", email="AB@a.test")
    assert d.user_id == existing.id
    assert AgencyUser.all_objects.filter(agency=agency_ctx, email="ab@a.test").count() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest apps/drivers/tests/test_registration_code.py -v`
Expected: FAIL — `test_create_generates_6_digit_code` fails because `registration_code` is empty (`""` does not match `\d{6}`); the login tests fail because `d.user` is `None`.

- [ ] **Step 3: Implement code generation + login pre-creation**

Replace the entire `create` method in `apps/drivers/services.py` (currently lines 8–22) with the following, and add the two helper methods and the imports. The full new top of the file:

```python
import random

from django.db import transaction

from apps.common.context import get_current_agency
from apps.common.services import AgencyScopedService
from apps.drivers.models import Driver, DriverNote


class DriverService(AgencyScopedService):
    model = Driver

    def create(self, *, first_name, last_name, email, phone="", ni_number="", date_of_birth=None,
               licence_type="", depot=None, flex_enrolled=False):
        agency = get_current_agency()
        email = email.lower().strip()
        with transaction.atomic():
            driver = Driver(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                ni_number=ni_number,
                date_of_birth=date_of_birth,
                licence_type=licence_type or "",
                depot=depot,
                flex_enrolled=flex_enrolled,
                status=Driver.Status.PENDING,
                registration_code=self._generate_code(),
            )
            driver.user = self._ensure_login(agency, email, first_name, last_name)
            self.save(driver)
        return driver

    def _generate_code(self):
        for _ in range(10):
            code = f"{random.randint(0, 999999):06d}"
            if not Driver.objects.filter(registration_code=code).exists():
                return code
        return f"{random.randint(0, 999999):06d}"

    def _ensure_login(self, agency, email, first_name, last_name):
        from apps.accounts.models import AgencyUser, Role, UserRole
        user = AgencyUser.all_objects.filter(agency=agency, email=email).first()
        if user is None:
            user = AgencyUser(
                agency=agency, email=email,
                first_name=first_name, last_name=last_name,
                is_active=False,
            )
            user.set_unusable_password()
            user.save()
        driver_role = Role.objects.filter(agency=agency, name="Driver").first()
        if driver_role is not None:
            UserRole.objects.get_or_create(user=user, role=driver_role)
        return user
```

Leave the rest of the file (`update`, `suspend`, `reactivate`, `offboard`, `DriverNoteService`) unchanged. Note the import block at the top replaces the existing two import lines.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest apps/drivers/tests/test_registration_code.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the existing driver mutation tests to confirm no regression**

Run: `.venv\Scripts\python.exe -m pytest apps/drivers/tests/test_mutations.py -v`
Expected: PASS — `test_create_driver_happy` still passes (its `ctx` fixture has no "Driver" role, so role assignment is skipped without error).

- [ ] **Step 6: Commit**

```bash
git add apps/drivers/services.py apps/drivers/tests/test_registration_code.py
git commit -m "feat(drivers): generate registration code + pre-create disabled login on create"
```

---

## Task 3: Email the code via a Celery task

**Files:**
- Create: `apps/drivers/tasks.py`
- Modify: `apps/drivers/services.py` (`DriverService.create` — fire the task)
- Test: `apps/drivers/tests/test_registration_code.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `apps/drivers/tests/test_registration_code.py`:

```python
def test_create_sends_email_with_code(agency_ctx):
    from django.core import mail
    mail.outbox.clear()
    d = DriverService().create(first_name="A", last_name="B", email="ab@a.test")
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == ["ab@a.test"]
    assert d.registration_code in msg.body
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest apps/drivers/tests/test_registration_code.py::test_create_sends_email_with_code -v`
Expected: FAIL — `assert len(mail.outbox) == 1` fails because no email is sent yet (outbox is empty).

- [ ] **Step 3: Create the Celery task**

Create `apps/drivers/tasks.py`:

```python
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
```

- [ ] **Step 4: Fire the task from `create`**

In `apps/drivers/services.py`, in `DriverService.create`, change the tail of the method so the email is sent after the transaction commits. Replace:

```python
            self.save(driver)
        return driver
```

with:

```python
            self.save(driver)
        from apps.drivers.tasks import send_driver_registration_email
        send_driver_registration_email.delay(str(driver.id))
        return driver
```

(The `from ... import` stays inside the method to avoid a circular import at module load. `.delay(...)` runs inline because Celery is eager in dev/tests.)

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest apps/drivers/tests/test_registration_code.py -v`
Expected: PASS (4 passed). The email backend is locmem under pytest-django, so `mail.outbox` is populated by the eager task.

- [ ] **Step 6: Commit**

```bash
git add apps/drivers/tasks.py apps/drivers/services.py apps/drivers/tests/test_registration_code.py
git commit -m "feat(drivers): email registration code on driver creation"
```

---

## Task 4: Expose `registrationCode` + `registered` on `DriverType`

**Files:**
- Modify: `apps/drivers/schema.py` (`DriverType`)
- Test: `apps/drivers/tests/test_registration_code.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `apps/drivers/tests/test_registration_code.py`:

```python
def test_driver_type_exposes_code_and_registered(agency_ctx):
    from graphene.test import Client
    from apps.accounts.models import AgencyUser, Role, Permission, RolePermission, UserRole
    from config.schema import schema

    d = DriverService().create(first_name="A", last_name="B", email="ab@a.test")

    reader = AgencyUser(agency=agency_ctx, email="reader@a.test", is_active=True)
    reader.set_password("x")
    reader.save()
    role = Role.objects.create(agency=agency_ctx, name="Reader")
    perm, _ = Permission.objects.get_or_create(code="drivers.read")
    RolePermission.objects.create(role=role, permission=perm)
    UserRole.objects.create(user=reader, role=role)

    class Req:
        pass
    req = Req()
    req.user = reader
    req.current_agency = agency_ctx

    q = f'query {{ driver(id: "{d.id}") {{ registrationCode registered }} }}'
    result = Client(schema).execute(q, context=req)
    assert result.get("errors") is None
    assert result["data"]["driver"]["registrationCode"] == d.registration_code
    assert result["data"]["driver"]["registered"] is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest apps/drivers/tests/test_registration_code.py::test_driver_type_exposes_code_and_registered -v`
Expected: FAIL — GraphQL returns an error like `Cannot query field "registrationCode" on type "DriverType"` (so `result["errors"]` is not None).

- [ ] **Step 3: Add the field + resolver to `DriverType`**

In `apps/drivers/schema.py`, replace the `DriverType` class (currently lines 20–30) with:

```python
class DriverType(DjangoObjectType):
    notes = graphene.List(graphene.NonNull(DriverNoteType), required=True)
    registered = graphene.Boolean(required=True)

    class Meta:
        model = Driver
        fields = ("id", "first_name", "last_name", "email", "phone", "status",
                  "licence_type", "depot", "flex_enrolled", "joined_at",
                  "suspension_reason", "offboard_reason", "registration_code",
                  "created_at", "updated_at")

    def resolve_notes(self, info):
        return list(self.notes.all().order_by("-created_at"))

    def resolve_registered(self, info):
        return bool(self.user_id and self.user.is_active)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest apps/drivers/tests/test_registration_code.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Run the full drivers test module**

Run: `.venv\Scripts\python.exe -m pytest apps/drivers/ -v`
Expected: PASS (all driver tests green).

- [ ] **Step 6: Commit**

```bash
git add apps/drivers/schema.py apps/drivers/tests/test_registration_code.py
git commit -m "feat(drivers): expose registrationCode + registered on DriverType"
```

---

## Task 5: Show the copyable code on the console driver detail page

**Files:**
- Modify: `app/(console)/drivers/mutations.ts` (`DRIVER_DETAIL`)
- Modify: `app/(console)/drivers/[id]/page.tsx`

No automated test (the console has no test runner configured); verification is a type-check build + manual check.

- [ ] **Step 1: Add the fields to the `DRIVER_DETAIL` query**

In `app/(console)/drivers/mutations.ts`, change the `DRIVER_DETAIL` query so the `driver` selection requests the new fields. Replace:

```ts
export const DRIVER_DETAIL = gql`
  query DriverDetail($id: ID!) {
    driver(id: $id) {
      ...DriverFields
      notes { id body createdAt author { id email } }
    }
  }
  ${DRIVER_FIELDS}
`
```

with:

```ts
export const DRIVER_DETAIL = gql`
  query DriverDetail($id: ID!) {
    driver(id: $id) {
      ...DriverFields
      registrationCode
      registered
      notes { id body createdAt author { id email } }
    }
  }
  ${DRIVER_FIELDS}
`
```

- [ ] **Step 2: Add a copyable-code component**

In `app/(console)/drivers/[id]/page.tsx`, add this component at the bottom of the file, after the `Row` function (after line 491):

```tsx
function RegistrationCode({ code }: { code: string }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard unavailable */
    }
  }
  return (
    <div className="flex justify-between items-center py-1.5 border-b border-surface-container-low last:border-b-0">
      <span className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">
        Registration code
      </span>
      <div className="flex items-center gap-2">
        <span className="font-mono text-sm font-semibold tracking-widest text-on-surface">{code}</span>
        <button
          type="button"
          onClick={copy}
          className="rounded-md bg-primary/10 px-2 py-1 text-xs font-semibold text-primary hover:bg-primary/20"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Add `useState` to the existing import**

At the top of `app/(console)/drivers/[id]/page.tsx`, line 3 currently reads:

```tsx
import { useEffect, useMemo } from "react"
```

Change it to:

```tsx
import { useEffect, useMemo, useState } from "react"
```

- [ ] **Step 4: Render the code in the profile card**

In the profile `<section>` of the left column, inside the `<div className="space-y-3">` block (the one containing the `Row` components, around lines 243–256), add this immediately after the `<Row label="Flex" ... />` line:

```tsx
              {!driver.registered && driver.registrationCode && (
                <RegistrationCode code={driver.registrationCode} />
              )}
              {driver.registered && (
                <div className="flex justify-between items-center py-1.5 border-b border-surface-container-low last:border-b-0">
                  <span className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">
                    Registration
                  </span>
                  <span className="text-xs font-bold px-2 py-0.5 rounded uppercase bg-emerald-100 text-emerald-800">
                    Registered
                  </span>
                </div>
              )}
```

- [ ] **Step 5: Type-check / build**

Run (from `omnio_management_console`): `npm run build`
Expected: build succeeds with no TypeScript errors. (`driver` is untyped from the `useQuery` result, so `driver.registrationCode` / `driver.registered` compile.)

- [ ] **Step 6: Manual verification**

With the backend running (seeded) and `npm run dev`:
1. Log in (`admin@demo.test` / `demo1234`), go to Drivers → "New driver", create a driver.
2. Check the backend console output — an email containing a 6-digit code was printed.
3. Open the new driver's detail page — the "Registration code" row shows the 6-digit code with a working **Copy** button.
4. Open an existing active driver (e.g. James Wilson) — instead of a code, the row shows a green **Registered** badge.

- [ ] **Step 7: Commit**

```bash
# from omnio_management_console
git add "app/(console)/drivers/mutations.ts" "app/(console)/drivers/[id]/page.tsx"
git commit -m "feat(console): show copyable registration code on driver detail"
```

---

## Definition of Done
- New drivers created via the console get a 6-digit `registration_code` and a disabled, password-less `AgencyUser` (Driver role) linked to them.
- The code is emailed to the driver (printed to the console email backend in dev).
- `DriverType` exposes `registrationCode` + `registered`; the console driver detail page shows the code copyable while unregistered, and a "Registered" badge once a linked login is active.
- All backend tests pass: `.venv\Scripts\python.exe -m pytest apps/drivers/ -v`.
- Out of scope (not built): code-consumption/activation mutation, mobile Register screen, backfill of pre-existing drivers.
