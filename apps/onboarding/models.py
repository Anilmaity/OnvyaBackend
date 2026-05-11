from django.db import models
from auditlog.registry import auditlog

from apps.common.models import AgencyScopedModel


class Application(AgencyScopedModel):
    class State(models.TextChoices):
        NOT_STARTED = "NOT_STARTED"
        IN_PROGRESS = "IN_PROGRESS"
        PENDING_REVIEW = "PENDING_REVIEW"
        APPROVED = "APPROVED"
        REJECTED = "REJECTED"

    driver = models.OneToOneField("drivers.Driver", on_delete=models.CASCADE, related_name="application")
    state = models.CharField(max_length=20, choices=State.choices, default=State.NOT_STARTED)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        "accounts.AgencyUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="decided_applications"
    )
    rejection_reason = models.TextField(blank=True, default="")

    class Meta(AgencyScopedModel.Meta):
        indexes = AgencyScopedModel.Meta.indexes + [models.Index(fields=["agency", "state"])]


class Step(AgencyScopedModel):
    class Kind(models.TextChoices):
        PERSONAL_DETAILS = "PERSONAL_DETAILS"
        DOCUMENT_UPLOAD = "DOCUMENT_UPLOAD"
        OCR = "OCR"
        DVLA_CHECK = "DVLA_CHECK"
        RTW_CHECK = "RTW_CHECK"
        CONTRACT_SIGNATURE = "CONTRACT_SIGNATURE"

    class Status(models.TextChoices):
        PENDING = "PENDING"
        IN_PROGRESS = "IN_PROGRESS"
        PASSED = "PASSED"
        FAILED = "FAILED"

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="steps")
    kind = models.CharField(max_length=32, choices=Kind.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    outcome = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta(AgencyScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["application", "kind"], name="step_unique_kind_per_application"),
        ]


class ApplicationDocument(AgencyScopedModel):
    class Kind(models.TextChoices):
        LICENCE = "LICENCE"
        PASSPORT = "PASSPORT"
        RTW_EVIDENCE = "RTW_EVIDENCE"

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=32, choices=Kind.choices)
    file = models.FileField(upload_to="applications/%Y/%m/")
    ocr_payload = models.JSONField(default=dict, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)


auditlog.register(Application)
auditlog.register(Step)
