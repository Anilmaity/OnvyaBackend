# Onvya Backend — Architecture & Plan (v2)

**Stack:** Django 5 · Graphene-Django (GraphQL) · PostgreSQL · Redis · Celery · AWS S3
**Multi-agency model:** Shared database, agency-aware via `agency_id` foreign key
**Serves:** Driver mobile app (iOS / Android), Management Console (web admin), OSM portal

---

## 1. Architectural principles

1. **Single backend, three front-ends.** One GraphQL API serves the driver app, the management console, and the OSM portal. Field-level RBAC controls what each role sees and does.

2. **Shared DB with agency scoping.** Every per-agency table carries an `agency_id` foreign key to the `Agency` table. A base model and custom manager auto-filter every query by the current agency loaded from the JWT — developers never write `.filter(agency=...)` manually, which means they can never forget it.

3. **GraphQL as the contract.** One typed schema is the source of truth for both clients. Mobile takes only the fields it needs (cheap on bandwidth); the console pulls dense aggregates in one round trip.

4. **Background-first compliance.** DVLA, RTW, expiry alerts, Cortex pulls, and payment runs all run on Celery — never block a request.

5. **Audit by default.** Every mutation is logged with user, entity, before/after diff, IP, and timestamp. Required for UK GDPR and for regulator-ready audit packs.

6. **Real-time where it matters.** Channels (WebSocket) pushes compliance alerts and dashboard counters live to the console. Everything else stays plain GraphQL.

7. **Migrate to schema-per-tenant later if needed.** The architecture is "tenant-aware shared DB" — when you hit 50+ agencies or get enterprise compliance pressure, the path to django-tenants is a copy script, not a rewrite.

---

## 2. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Framework | Django 5.0 | Mature ORM, admin, ecosystem, GDPR-friendly |
| API | Graphene-Django 3.x | Native Django integration, DataLoader for N+1 |
| Auth | `djangorestframework-simplejwt` + Django sessions | JWT for clients; sessions for Django admin only |
| Database | PostgreSQL 15+ | JSONB, partial indexes, full-text search |
| Cache and broker | Redis 7 | Cache, Celery broker, Channels layer |
| Background jobs | Celery 5 + Celery Beat | Scheduled DVLA, expiry sweeps, payment runs |
| Real-time | Django Channels 4 | WebSocket alerts to console |
| Files | AWS S3 via `django-storages` | Signed URLs, no public buckets |
| Payments | Stripe Connect / Payouts | UK payouts; pass-through, no markup |
| Email and SMS | SendGrid + Twilio | Notifications, OTP fallback |
| OCR | AWS Textract | Licence + RTW data extraction |
| Audit | `django-auditlog` | Append-only mutation log |
| Observability | Sentry + structured JSON logs | Errors + audit forensics |
| Infra | AWS ECS Fargate · RDS Postgres · ElastiCache Redis · S3 | Standard, GDPR-safe (eu-west-2 London) |

---

## 3. How agency scoping works (the key pattern)

This replaces multi-tenancy. Every per-agency model inherits from a base class:

```python
class AgencyScopedModel(models.Model):
    agency = models.ForeignKey('agencies.Agency', on_delete=models.CASCADE)
    objects = AgencyScopedManager()      # auto-filters when current_agency is set

    class Meta:
        abstract = True
        indexes = [models.Index(fields=['agency'])]
```

A thread-local stores the current agency (loaded from JWT in middleware), and the manager wraps every query:

```python
class AgencyScopedManager(models.Manager):
    def get_queryset(self):
        qs = super().get_queryset()
        agency = get_current_agency()
        if agency is not None:
            qs = qs.filter(agency=agency)
        return qs
```

So when a resolver writes `Driver.objects.all()`, the SQL is actually `SELECT * FROM drivers WHERE agency_id = <current>`. Developers cannot forget the filter — it's structural, not a discipline rule.

Three safeguards on top:

1. **Composite database indexes.** Every per-agency table has `(agency_id, …)` as the leading index columns. Queries stay fast even with many agencies.
2. **Mutation guard.** Every save/update goes through a base service that re-checks `obj.agency_id == current_agency_id`. A malicious payload trying to update another agency's row is rejected before SQL.
3. **JWT carries agency_id.** Token forgery to switch agencies is blocked by signature verification.

---

## 4. Module breakdown

Each module is a Django app under `apps/`. All apps live in a single Django project against a single Postgres database.

### 4.1 `agencies`
The `Agency` record — name, slug, contact, timezone, branding (logo, primary colour), active flag. Plus `Depot` (regional bases the drivers work from). This is the only "system" model — every other module references it.

### 4.2 `accounts`
Console operators (`AgencyUser`), roles, permissions, login events. JWT issuance and refresh. MFA (TOTP). Password reset. SSO hook for Phase 2.

Includes the `Role` and `Permission` system — agency admins can define custom roles in addition to seeded defaults.

### 4.3 `drivers`
The driver record — personal info, contact, NI number, status (Active / Resting / Suspended / Offboarded), licence type, depot, Amazon Flex enrolment flag, joined date. Soft-delete via `status`. GDPR delete and export endpoints. Internal notes.

### 4.4 `onboarding`
Pipeline: `Application` → many `Step` rows (document upload, OCR, DVLA, RTW, e-signature, complete). Each step records outcome and timestamp. Kanban-friendly state machine. Triggers `dvla_check_driver` and `rtw_check_driver` Celery tasks.

### 4.5 `compliance`
- `DocumentType` — agency-configurable (licence, passport, RTW, insurance, etc.)
- `DriverDocument` — per-driver document with expiry, verification status, OCR JSON, S3 file URL
- `DvlaCheck`, `RtwCheck` — historical record of every check run
- Daily Celery sweep flags documents expiring in 30/14/7/1 days, dispatches notifications, optionally auto-suspends drivers per agency policy
- **Audit Pack export** — bundles all driver compliance docs into a signed PDF/CSV with a SHA-256 hash, suitable for regulator submission

### 4.6 `vehicles`
Vehicle directory (registration, make, model, VIN, mileage, MOT and tax expiry, status). Vehicle documents (insurance, V5C). Driver-to-vehicle assignment history. Daily vehicle check submissions (AI van check + manual checklist) — `DailyVehicleCheck` rows store the checklist JSON, photo URLs, and pass/fail/defect result. Maintenance log.

### 4.7 `scheduling`
`Route` and `Shift` rows (driver × time × route × vehicle). Conflict detection (overlapping shifts, expired licence at shift start, no MOT on assigned vehicle). Bulk copy-week, CSV import. WebSocket push to the console when a shift is changed.

### 4.8 `payments`
`PaymentRun` (weekly) → many `Payment` rows → each Payment has many `Deduction` rows and exactly one `DriverInvoice` (PDF, S3-hosted). Approval workflow: Draft → Approved → Sent to Stripe → Paid / Failed. NMW monitor: a Celery task checks each driver's effective hourly rate vs the HMRC NMW threshold and flags violations.

### 4.9 `cortex` (Amazon Flex)
Daily pull from Amazon Cortex API stores per-driver metrics (on-time, acceptance, completion, overall score). Score drop alerts. Tickets — raised by driver (via app) or by operator. Ticket message thread.

### 4.10 `notifications`
Outbound notification queue: email (SendGrid), push (FCM / APNs), SMS (Twilio fallback). Each `Notification` row records channel, status, retry count. Template-driven, rendered server-side.

### 4.11 `audit`
- `LoginEvent` — every console login (success / failure)
- `AuditLog` — every mutation: who, what, when, before/after diff. Powered by `django-auditlog`. Append-only, 24-month retention then archive to S3 Glacier.
- Per-driver data-access log when sensitive PII is read (UK GDPR requirement).

### 4.12 `common`
Shared base models (`UUIDBaseModel`, `TimestampedModel`, `AgencyScopedModel`), permissions decorators, GraphQL helpers, S3 signed-URL utility, custom managers, agency-context middleware.

---

## 5. Feature catalogue

This is what the platform actually does, organised by who uses it.

### 5.1 Driver mobile app features

**Onboarding (the "9-minute" flow)**
- Invite link from agency, account creation
- Personal details capture
- Document upload (licence, passport, RTW evidence) — direct to S3 via pre-signed POST
- OCR auto-fills the fields from documents
- DVLA check runs in background, result shown when ready
- Right-to-Work check
- Digital contract signature
- Status: active

**Daily operation**
- Home dashboard: today's shifts, compliance status, recent earnings
- AI van check — camera scan with damage detection
- Manual van check — checklist (brakes, tyres, lights, fluids, body, windscreen)
- Shift view — assigned shifts with route, vehicle, depot
- Clock-in / clock-out
- Incident reporting — photo + description, real-time to manager

**Money and admin**
- Weekly payslip viewer
- Deduction log (itemised, transparent)
- Invoice PDF download
- Tax info (UTR, NI)

**Compliance and personal**
- Document expiry alerts (30/14/7/1 days)
- Re-upload documents directly
- Profile / contact details edit

**Wellbeing & benefits**
- 24/7 GP service link
- Mental health support
- Retail discounts, fuel savings
- Insurance and mortgage advice access

**Communication**
- In-app chat with manager
- Push notifications for alerts, payments, shifts
- Cortex score view (if Amazon Flex enrolled)
- Raise a ticket

### 5.2 Management console features

**Dashboard (operator home)**
- Fleet health score (overall compliance %)
- Active drivers today, sparkline trend
- Pending applications count
- Expiring documents (30-day window, sorted by urgency)
- Upcoming vehicle checks
- Recent payment runs
- Average Cortex score
- Live alert feed (WebSocket)
- Quick actions: approve applications, trigger DVLA, download report, add driver

**Onboarding queue**
- Kanban: Not Started → In Progress → Pending Review → Approved → Rejected
- List view with sortable columns, filters
- Applicant slide-out with document checklist, previews, DVLA result, RTW result, internal notes
- Per-applicant actions: Approve, Request More Info, Reject
- Bulk approve / bulk request documents / CSV export

**Driver directory**
- Searchable, filterable database of all drivers
- Filters: status, compliance, vehicle type, licence, Flex enrolment, depot, join date
- Driver profile page: personal info, compliance dashboard, vehicle history, earnings, payment history, Cortex metrics, shift history, notes, activity timeline
- Actions: Suspend, Reactivate, Offboard, Message

**Compliance & documents centre**
- Fleet compliance overview with rate %
- Documents expiring in 7/14/30 days
- Non-compliant drivers list (sorted by severity)
- Document management table — all docs across all drivers, sortable, filterable
- Bulk renewal requests
- One-click document preview
- Configurable auto-suspend rules per agency
- Audit-ready export — signed PDF / CSV with timestamp

**Scheduling**
- Day / week / month calendar views
- Drag-and-drop shift assignment (real-time)
- Conflict highlighting (overlap, expired licence, no MOT)
- Click-to-edit shift details
- Bulk copy day/week
- CSV import

**Vehicle management**
- Vehicle directory with status, MOT/tax expiry
- Daily vehicle check log with photos
- Defect tracking and assignment to maintenance
- Maintenance log per vehicle

**Amazon Flex (Cortex integration)**
- Fleet score average, distribution chart
- Drivers at risk (score below threshold)
- Drivers blocked by Amazon (auto-flagged)
- Per-driver metrics view
- Ticket management — open, in-progress, resolved
- Score drop alerts (configurable thresholds)
- Weekly performance digest email

**Payments & invoicing**
- Total payroll this week / month
- Pending and failed payments
- Per-driver earnings breakdown with deductions
- Bulk approve and process
- Stripe payout integration
- Auto-generated invoice PDFs
- Agency-to-client invoicing (Phase 2)
- Financial reports

**Reporting & analytics**
- Fleet utilisation over time
- Onboarding conversion %
- Compliance health breakdown
- Earnings summary by period
- Cortex trend
- Vehicle check completion and defect frequency
- Regional performance by depot
- Export to PDF / CSV; scheduled email delivery

**Settings**
- Organisation details, branding
- Compliance rules (required docs, auto-suspend, check frequency)
- Notification config (who gets what)
- Integrations status (DVLA, Stripe, Cortex)
- User management (add operators, assign roles, login log)
- Billing (current plan, payment method, invoices)

### 5.3 OSM portal features

A simpler subset of the console for on-the-ground supervisors:
- Today's drivers and vehicle status
- Review submitted van checks
- Log incidents
- Driver status changes (mark resting / unavailable)
- Quick chat with drivers

---

## 6. GraphQL schema design

### Type structure
- **Types** mirror models — `DriverType`, `VehicleType`, `ShiftType`, etc.
- **Connections** for paginated lists — Relay-style cursors keep large fleets (10,000+ drivers) fast.
- **Filter input objects** per type — `DriverFilter { status, complianceStatus, depotId, search }`.
- **Mutations** named after the business action — `approveDriverApplication`, `suspendDriver`, `runPayment`, `raiseCortexTicket`. They return a `MutationResult` union (`Success` / `ValidationError` / `PermissionDenied`).
- **Subscriptions** (Channels-backed) — `complianceAlertAdded`, `paymentRunCompleted`, `shiftUpdated`.

### Auth on every field
Every resolver passes through a `@permission_required('module.action')` decorator that reads the user's roles from JWT context. A Finance Admin sees `Driver.earningsThisWeek`; a Recruiter doesn't.

### Performance
- **DataLoader** for every FK that crosses types — kills N+1 queries.
- **Persisted queries** for the mobile app — clients ship a query hash; backend has the document on disk. Cuts payload and locks down what mobile can ask for.
- **Query depth + complexity limit** middleware — caps malicious deep queries.

---

## 7. Authentication & authorisation

### Token model
- **Mobile (driver app):** JWT access (30 min) + refresh (14 days) in secure storage. Refresh rotates on use.
- **Console:** Same JWT, MFA (TOTP) enforced for admin roles. Sessions also created via HttpOnly cookie + CSRF for the Django admin.

### Token claims
```json
{
  "sub": "<user_uuid>",
  "agency_id": "<agency_uuid>",
  "roles": ["fleet_manager"],
  "iat": ..., "exp": ...
}
```

### Roles (seeded per agency)

| Role | Scope |
|---|---|
| Super Admin | Full agency, billing, settings |
| Fleet Manager | Drivers, scheduling, vehicles, compliance read |
| Compliance Officer | Compliance + audit exports |
| Finance Admin | Payments, invoices, reports |
| Recruiter | Onboarding queue only |
| OSM | Vehicle checks + incident reports |
| Driver | Self only (own data, submit checks, view payslips) |

Permissions stored as `module.action` strings (e.g. `payments.run`, `drivers.suspend`) joined to roles via `RolePermission`. Adding a new role is a data change, not a code change.

---

## 8. Background jobs (Celery + Beat)

| Task | Schedule | Purpose |
|---|---|---|
| `dvla_check_driver(driver_id)` | On-demand + weekly per driver | Hit DVLA API, store result, alert if changed |
| `rtw_check_driver(driver_id)` | On-demand + monthly per driver | Right-to-work re-check |
| `compliance_expiry_sweep` | Daily 04:00 UTC | Find docs expiring in 30/14/7/1 days, dispatch notifications, optionally auto-suspend |
| `cortex_pull_metrics` | Daily 02:00 UTC | Pull yesterday's Cortex metrics per agency, store, alert on score drops |
| `payment_run_process(run_id)` | Triggered by operator | Process Stripe payouts, generate invoice PDFs, mark paid/failed |
| `nmw_check(driver_id, period)` | After each payment | Verify driver pay vs HMRC NMW, flag violations |
| `vehicle_check_reminder` | Daily 06:00 per driver | Push reminder if no check submitted by configured time |
| `notification_dispatch(notification_id)` | Continuous | Send queued emails / push / SMS |
| `audit_log_archive` | Monthly | Archive logs older than 24 months to S3 Glacier |
| `incident_alert(incident_id)` | Immediate | Notify manager + OSM in real time |

Tasks accept `agency_id` as parameter where relevant. Sweep tasks iterate agencies and batch-process.

---

## 9. File handling
- All uploads go to `s3://onvya-{env}/{agency_id}/...` with server-side encryption (AES-256 / KMS).
- Public buckets forbidden. Console and app fetch via short-lived (60s) signed S3 URLs.
- Mobile document uploads use **two-step pre-signed POST** — client uploads directly to S3, then notifies backend with the key. Backend never proxies bytes.
- Generated PDFs (invoices, audit packs) follow the same pattern, written by Celery workers.

---

## 10. Security & compliance

| Concern | How it's handled |
|---|---|
| UK GDPR | Data resident in `eu-west-2` (London). Per-driver export and delete endpoints. Access log of all reads of personal data. |
| Data encryption | TLS 1.3 in transit; AES-256 at rest (RDS, S3, EBS). |
| Agency isolation | `agency_id` FK on every per-agency model + auto-filtering manager + mutation guard + JWT cross-check. |
| MFA | Mandatory for Super Admin + Finance Admin roles. |
| Password hashing | Argon2 (Django default). |
| Rate limiting | Django Ratelimit on auth endpoints; Nginx limit_req on `/graphql`. |
| GraphQL hardening | Depth limit, cost limit, persisted queries in production. |
| Audit logging | Every mutation + every personal-data read. Append-only, 24-month retention then archived. |
| Webhooks | Stripe + Cortex webhooks verify HMAC signatures. |
| Secrets | AWS Secrets Manager; never in code, never in env files in prod. |
| Pen testing | Annual, plus before each major release. |

---

## 11. Project layout

```
onvya_backend/
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── dev.py
│   │   └── prod.py
│   ├── urls.py
│   ├── schema.py            # Root GraphQL schema (stitches all apps)
│   ├── asgi.py              # ASGI app (Channels + Django)
│   └── celery.py
│
├── apps/
│   ├── agencies/            # Agency, Depot
│   ├── accounts/            # AgencyUser, Role, Permission, JWT
│   ├── drivers/             # Driver, DriverNote
│   ├── onboarding/          # Application, Step pipeline
│   ├── compliance/          # DocumentType, DriverDocument, DVLA, RTW
│   ├── vehicles/            # Vehicle, VehicleCheck, Maintenance
│   ├── scheduling/          # Shift, Route
│   ├── payments/            # PaymentRun, Payment, Deduction, Invoice
│   ├── cortex/              # Amazon Flex metrics + tickets
│   ├── notifications/       # Email, push, SMS queue
│   ├── audit/               # LoginEvent, AuditLog
│   └── common/              # Base models, utils, GraphQL helpers, middleware
│
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── scripts/
│   ├── seed_defaults.py
│   └── create_agency.py
└── manage.py
```

Each app:
```
apps/<name>/
├── models.py
├── schema.py                # Graphene types, queries, mutations
├── permissions.py
├── tasks.py                 # Celery tasks
├── services.py              # Business logic (kept out of resolvers)
├── selectors.py             # Read-side queries
├── migrations/
├── admin.py
└── tests/
```

---

## 12. Phased delivery

### Phase 1 — Foundation (weeks 1–3)
- Project scaffold, settings split, Docker compose
- `agencies` + `accounts` apps; JWT auth + roles + MFA
- `AgencyScopedModel` base + auto-filter manager + middleware
- GraphQL skeleton (schema, JWT auth context, depth/cost limits)
- Audit logging baseline
- Django admin set up for internal ops

### Phase 2 — Driver lifecycle (weeks 4–6)
- `drivers` model + CRUD
- `onboarding` pipeline (state machine + steps)
- `compliance` documents
- DVLA + RTW integration
- OCR pipeline (Textract)
- Document upload (pre-signed S3)
- Expiry sweep job

### Phase 3 — Fleet & ops (weeks 7–9)
- `vehicles` directory + daily checks (AI + manual)
- `scheduling` shifts + conflict detection
- WebSocket compliance alerts
- Incident reporting
- In-app chat (basic)

### Phase 4 — Money & performance (weeks 10–12)
- `payments` — runs, approvals, Stripe payouts, invoices
- NMW monitoring
- `cortex` — daily pulls, score alerts, tickets
- Reports & exports (PDF, CSV)
- Driver wellbeing module (links + benefits hub)

### Phase 5 — Polish & launch (weeks 13–14)
- Performance tuning (DataLoaders, indexes, query budget)
- Security review + pen test
- Observability (Sentry, dashboards, alerting)
- Load test (10,000-driver agency, 50 concurrent operators)
- Docs + onboarding guides for new agencies

---

## 13. Future migration path (if needed)

If you outgrow shared DB:

| Trigger | Action |
|---|---|
| 50+ agencies, slow queries | Add partitioning on `agency_id` for large tables (drivers, payments, audit_log) |
| Enterprise compliance ask | Move sensitive tables (drivers, documents) to per-agency schemas via django-tenants; keep shared tables alone |
| Single agency demands isolated DB | Spin a dedicated deployment for that agency from the same codebase |

Because every per-agency model already has `agency_id` and goes through `AgencyScopedManager`, none of these moves require resolver rewrites — only data migrations.

---
    
## 14. Open decisions

Before writing the first model:

1. **Hosting region:** confirm `eu-west-2` (London) for UK GDPR.
2. **OCR provider:** AWS Textract vs Google Document AI.
3. **Push notifications:** native FCM/APNs vs Expo (depends on mobile stack).
4. **GraphQL subscriptions:** Channels from day one, or polling for v1?
5. **E-signature:** DocuSign/SignNow integration, or in-house click-sign + hash for v1?
6. **Stripe model:** Stripe Connect (Express) for drivers, or pass-through payouts only?