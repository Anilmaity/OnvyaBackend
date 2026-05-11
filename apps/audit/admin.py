from django.contrib import admin

from .models import LoginEvent


@admin.register(LoginEvent)
class LoginEventAdmin(admin.ModelAdmin):
    list_display = ("email_attempted", "success", "ip", "created_at")
    list_filter = ("success",)
    readonly_fields = tuple(f.name for f in LoginEvent._meta.fields)
