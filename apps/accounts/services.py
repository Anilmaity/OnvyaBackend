from apps.accounts.models import AgencyUser
from apps.audit.models import LoginEvent


def find_user_by_email(email):
    email = email.lower().strip()
    return AgencyUser.all_objects.filter(email=email, is_active=True).first()


def write_login_event(*, email_attempted, success, user=None, agency=None, request=None):
    ip = None
    user_agent = ""
    if request is not None:
        ip = request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:512]
    return LoginEvent.objects.create(
        email_attempted=email_attempted,
        success=success,
        user=user,
        agency=agency,
        ip=ip,
        user_agent=user_agent,
    )


def authenticate_user(email, password):
    """Returns AgencyUser or None. Bypasses agency scoping (login has no context yet)."""
    user = find_user_by_email(email)
    if user is None:
        return None
    if not user.check_password(password):
        return None
    if not user.is_active:
        return None
    return user
