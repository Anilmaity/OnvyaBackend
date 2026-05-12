from django.contrib import admin
from apps.training.models import Course, Completion

admin.site.register(Course)
admin.site.register(Completion)
