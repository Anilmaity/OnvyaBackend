"""Canonical permission catalogue for the foundation slice.
Add to this list as new apps come online; never rename existing codes."""

PERMISSIONS = [
    # agencies
    ("agencies.read", "Read agency + depots"),
    ("agencies.manage", "Update agency settings"),
    # drivers
    ("drivers.read", "Read driver records"),
    ("drivers.create", "Create driver records"),
    ("drivers.update", "Update driver records"),
    ("drivers.suspend", "Suspend / reactivate drivers"),
    ("drivers.offboard", "Offboard drivers"),
    ("drivers.note", "Add internal driver notes"),
    # applications / onboarding
    ("applications.read", "Read applications"),
    ("applications.create", "Start applications"),
    ("applications.update", "Update / upload to applications"),
    ("applications.approve", "Approve / reject / request more info"),
    # accounts
    ("accounts.read", "Read other console users"),
    ("accounts.manage", "Create / disable console users; assign roles"),
    # audit
    ("audit.read", "Read login events and audit log"),
    # scheduling
    ("scheduling.read", "Read shifts and adjustments"),
    ("scheduling.create", "Create shifts"),
    ("scheduling.update", "Update / cancel / complete shifts, request adjustments"),
    ("scheduling.approve_adjustment", "Approve / reject time adjustments"),
    # documents
    ("documents.read", "Read driver compliance documents"),
    ("documents.write", "Upsert / delete driver documents"),
    # invoicing
    ("invoicing.read", "Read invoices"),
    ("invoicing.create", "Generate draft invoices"),
    ("invoicing.update", "Edit / issue / mark paid / void invoices"),
    # training
    ("training.read", "Read training courses and completions"),
    ("training.write", "Upsert courses / record completions"),
]

# role_name -> set of permission codes
ROLE_MATRIX = {
    "Super Admin": {p[0] for p in PERMISSIONS},
    "Fleet Manager": {
        "agencies.read",
        "drivers.read", "drivers.create", "drivers.update", "drivers.suspend", "drivers.note",
        "applications.read",
        "scheduling.read", "scheduling.create", "scheduling.update", "scheduling.approve_adjustment",
        "documents.read",
        "invoicing.read", "invoicing.create", "invoicing.update",
        "training.read",
    },
    "Compliance Officer": {
        "agencies.read",
        "drivers.read", "drivers.suspend", "drivers.note",
        "applications.read",
        "audit.read",
        "scheduling.read",
        "documents.read", "documents.write",
        "training.read", "training.write",
    },
    "Finance Admin": {
        "agencies.read",
        "drivers.read",
        "audit.read",
        "scheduling.read",
        "invoicing.read", "invoicing.create", "invoicing.update",
    },
    "Recruiter": {
        "agencies.read",
        "drivers.read", "drivers.create",
        "applications.read", "applications.create", "applications.update", "applications.approve",
    },
    "OSM": {
        "agencies.read",
        "drivers.read", "drivers.note",
        "scheduling.read",
    },
    "Driver": set(),  # self-service only via myApplication etc.
}
