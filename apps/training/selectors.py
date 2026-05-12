from apps.training.models import Course, Completion


def list_courses():
    return Course.objects.all().order_by("name")


def list_completions(*, driver_id=None, course_id=None, status=None):
    qs = Completion.objects.all().select_related("driver", "course").order_by("-completed_on")
    if driver_id:
        qs = qs.filter(driver_id=driver_id)
    if course_id:
        qs = qs.filter(course_id=course_id)
    if status:
        qs = qs.filter(status=status)
    return qs
