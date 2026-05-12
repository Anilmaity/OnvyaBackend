from django.contrib import admin
from apps.scheduling.models import Shift, TimeAdjustment

admin.site.register(Shift)
admin.site.register(TimeAdjustment)
