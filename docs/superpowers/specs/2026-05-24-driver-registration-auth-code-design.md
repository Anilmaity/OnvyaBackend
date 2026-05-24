# Driver Registration Auth Code — Design

**Date:** 2026-05-24
**Status:** Approved (pending spec review)
**Repos touched:** `OnvyaBackend/` (primary), `omnio_management_console/` (display only)

## Summary

When a console user creates a driver, the backend mints a 6-digit **registration code**, pre-creates a **disabled login** for that driver, and **emails the code** to the driver. The code is displayed, copyable, on the console **driver detail page**.

The code is the credential a driver will later use (with their email + a chosen password) to activate their login and sign into the mobile app. **That consumption/activation flow and the mobile Register screen are explicitly out of scope for this task** — this task only *issues, stores, emails, and displays* the code, and pre-creates the disabled login it will eventually activate.

## Decisions (locked)

| Decision | Choice |
|---|---|
| Scope of this task | Issue + display only (no consumption mutation, no mobile screen) |
| Pre-create the disabled login? | **Yes, now** (in `CreateDriver`) |
| Code format | 6-digit numeric (`000000`–`999999`) |
| Lifetime / reuse | Reusable, no expiry; valid until the driver registers |
| "Registered" signal | Derived: a linked `AgencyUser` exists **and** `is_active is True` |
| Code storage | Field on `Driver` |
| Permission to view code | Existing `drivers.read` (no new permission) |
| Email format | Plain text |
| Where code is shown in console | Driver **detail** page only (not the create-success screen) |

## Context (current state)

- `CreateDriver` mutation → `DriverService.create()` creates a `Driver` with `status=PENDING` and **no login** (`Driver.user` is null). No code exists today.
- `Driver.user` is a nullable `OneToOneField` to `accounts.AgencyUser`. `AgencyUser` is the login entity (email + password); `authenticate_user()` rejects users where `is_active` is False.
- Roles are agency-scoped `accounts.Role` rows joined via `UserRole`. A `Driver` role already exists per agency (empty permission set), created by `seed_minimal`.
- Email is greenfield: dev uses `django.core.mail.backends.console.EmailBackend`; there is **no** `notifications` app and **no** `send_mail` usage anywhere. `DEFAULT_FROM_EMAIL` is **unset**.
- Celery tasks follow a consistent pattern (`apps/onboarding/tasks.py`): `@shared_task`, take an id, fetch via `Model.all_objects.get(...)`, then `with agency_context(obj.agency):`. Celery runs eager in dev (`CELERY_TASK_ALWAYS_EAGER=True`), so tasks execute inline.
- Console driver detail (`app/(console)/drivers/[id]/page.tsx`) renders profile/compliance/shifts/invoices/notes from `DriverType`; fields come through the `DriverFields` fragment (`lib/graphql/fragments.ts`) + `DRIVER_DETAIL` query (`app/(console)/drivers/mutations.ts`).

## Backend changes (`OnvyaBackend/`)

### 1. Model — `apps/drivers/models.py`
Add to `Driver`:
```python
registration_code = models.CharField(max_length=6, blank=True, default="")
```
- 6-digit numeric string (zero-padded; stored as text to preserve leading zeros).
- Reusable, no expiry — never cleared by this task. The future activation task decides what to do with it once the login is active (e.g. leave it; it's inert because the login is already active).
- Generate one Django migration.

### 2. Service — `apps/drivers/services.py` (`DriverService.create`)
After the `Driver` is saved, within the same logical operation:

1. **Generate code:** random 6-digit string. Re-roll if another **unregistered** driver in the same agency already holds the same code (unregistered = no active linked login). Bounded retry (e.g. up to 10 attempts); collisions are astronomically unlikely at demo scale.
2. **Pre-create disabled login:**
   - If an `AgencyUser` with this email already exists in the agency → link it (`Driver.user`) rather than creating a duplicate (the `(agency, email)` unique constraint forbids duplicates).
   - Otherwise create `AgencyUser(agency=..., email=..., first_name=..., last_name=..., is_active=False)`, call `set_unusable_password()`, save.
   - Ensure the `Driver` role is assigned via `UserRole.get_or_create`.
   - Set `Driver.user` and persist `registration_code`.
3. **Send email:** enqueue the Celery task (below) with the driver id.

Keep this logic in the service (business logic out of resolvers, per repo convention). Wrap user/code creation in a transaction so a half-built driver is never left behind.

### 3. Email task — `apps/drivers/tasks.py` (new file)
```python
@shared_task
def send_driver_registration_email(driver_id):
    driver = Driver.all_objects.get(id=driver_id)
    with agency_context(driver.agency):
        # plain-text send_mail with subject + body containing driver.registration_code
        # best-effort: swallow/log send failures so creation is never blocked
```
- Plain-text body: greeting, the 6-digit code, and a one-line instruction to download the app and register with their email + this code.
- Called from the mutation/service after the driver is created. Eager in dev → printed by the console `EmailBackend`; async in prod.
- A send failure must not raise out of the task in a way that breaks creation (note: `CELERY_TASK_EAGER_PROPAGATES=True` in dev, so wrap the send in try/except and log).

### 4. Settings — `config/settings/base.py`
Add:
```python
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "no-reply@onvya.local")
```

### 5. GraphQL — `apps/drivers/schema.py` (`DriverType`)
- Add `registration_code` to `DriverType.Meta.fields`.
- Add a resolved field `registered = graphene.Boolean(required=True)` →
  `True` when `self.user_id is not None and self.user.is_active`, else `False`.
- Both are returned through the existing `drivers.read`-gated `driver`/`drivers` resolvers; no new permission. (The code is also emailed in plaintext, so exposing it to users who can already read the driver record is consistent.)

## Console changes (`omnio_management_console/`)

### 6. GraphQL fields
- Add `registrationCode` and `registered` to the `DriverFields` fragment (`lib/graphql/fragments.ts`) — or, to keep the code off list views, add them only to the `DRIVER_DETAIL` query in `app/(console)/drivers/mutations.ts`. **Chosen:** add to `DRIVER_DETAIL` only (detail page is the sole consumer).

### 7. Driver detail page — `app/(console)/drivers/[id]/page.tsx`
- In the left profile column, add a **"Registration code"** row:
  - When `registered === false` and a code exists: show the 6-digit code in a monospace style with a **copy-to-clipboard** button (`navigator.clipboard.writeText`), with a brief "Copied" affirmation.
  - When `registered === true`: show a "Registered" badge instead of the code.
- No change to the create-driver success screen (`drivers/new/`).

## Testing

### Backend (`apps/drivers/tests/`)
- `CreateDriver` (or `DriverService.create`) sets a 6-digit numeric `registration_code`.
- It creates an `AgencyUser` that is **inactive**, has an **unusable password**, is linked via `Driver.user`, and has the **Driver** role.
- When an `AgencyUser` with the same email already exists in the agency, it is **linked, not duplicated** (no constraint violation).
- `send_driver_registration_email` is invoked (assert via task spy / `mail.outbox` under eager + `locmem` email backend in tests) and the message contains the code.
- `DriverType` returns `registrationCode` and `registered=False` for a freshly created driver; `registered` flips `True` once the linked user is activated.

### Console
- Light render test: detail page shows the code + copy button when `registered` is false, and a "Registered" badge (no code) when true.

## Out of scope (deferred to a follow-up task)
- `registerWithCode` / activation mutation that sets the password and flips the login `is_active=True`.
- Mobile app **Register** screen wired to that mutation.
- Backfilling codes/logins for pre-existing drivers seeded before this change.
- Code regeneration / resend-email action and expiry (intentionally omitted — code is reusable, no expiry).

## Risks / notes
- The repo implements multi-tenancy as **agency-scoped rows** (`AgencyScopedModel` + `agency_context`), not django-tenants schema-per-tenant as the older `Plan.md` describes. All new queries/tasks must run inside `agency_context`. (Do not reconcile the naming/architecture difference here — out of scope.)
- 6-digit numeric is low entropy. Acceptable because the code is used **together with the driver's email**, is reusable only until first registration, and this task does not build the consumption endpoint. The future activation task should add rate limiting / lockout on code submission.
