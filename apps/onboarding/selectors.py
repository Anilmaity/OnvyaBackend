from apps.onboarding.models import Application


def list_applications(*, state=None, search=None):
    qs = Application.objects.all()
    if state:
        qs = qs.filter(state=state)
    if search:
        qs = qs.filter(driver__last_name__icontains=search) | qs.filter(driver__first_name__icontains=search)
    return qs.order_by("-created_at")
