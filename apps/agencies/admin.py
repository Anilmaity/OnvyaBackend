from django.contrib import admin

from .models import Agency, Depot


@admin.register(Agency)
class AgencyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "created_at")
    search_fields = ("name", "slug")


@admin.register(Depot)
class DepotAdmin(admin.ModelAdmin):
    list_display = ("name", "agency", "is_active")
    list_filter = ("agency", "is_active")
