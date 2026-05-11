from django.contrib import admin

from .models import Driver, DriverNote


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "email", "status", "agency")
    list_filter = ("status", "agency")
    search_fields = ("first_name", "last_name", "email")


admin.site.register(DriverNote)
