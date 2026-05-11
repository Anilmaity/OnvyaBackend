from django.contrib import admin

from .models import AgencyUser, Role, Permission, RolePermission, UserRole


@admin.register(AgencyUser)
class AgencyUserAdmin(admin.ModelAdmin):
    list_display = ("email", "agency", "is_active", "is_staff")
    search_fields = ("email",)
    list_filter = ("agency", "is_active")


admin.site.register(Role)
admin.site.register(Permission)
admin.site.register(RolePermission)
admin.site.register(UserRole)
