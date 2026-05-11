from django.contrib import admin

from .models import Application, Step, ApplicationDocument


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("driver", "state", "submitted_at", "decided_at", "agency")
    list_filter = ("state", "agency")


@admin.register(Step)
class StepAdmin(admin.ModelAdmin):
    list_display = ("application", "kind", "status", "completed_at")
    list_filter = ("kind", "status")


admin.site.register(ApplicationDocument)
