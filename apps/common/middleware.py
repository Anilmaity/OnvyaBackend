from django.http import JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from apps.agencies.models import Agency
from apps.common.context import set_current_agency, clear_current_agency


class AgencyContextMiddleware:
    """Sets the current agency on the request from the JWT's agency_id claim."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._auth = JWTAuthentication()

    def __call__(self, request):
        try:
            auth_header = request.META.get("HTTP_AUTHORIZATION", "")
            if not auth_header.startswith("Bearer "):
                return self.get_response(request)

            try:
                validated = self._auth.get_validated_token(auth_header.split(" ", 1)[1])
            except (InvalidToken, TokenError):
                return JsonResponse({"detail": "Invalid or expired token"}, status=401)

            agency_id = validated.get("agency_id")
            try:
                agency = Agency.objects.get(id=agency_id, is_active=True)
            except (Agency.DoesNotExist, ValueError, TypeError):
                return JsonResponse({"detail": "Agency not found"}, status=401)

            set_current_agency(agency)

            try:
                user = self._auth.get_user(validated)
            except Exception:
                return JsonResponse({"detail": "User not found"}, status=401)

            if str(user.agency_id) != str(agency.id):
                return JsonResponse({"detail": "Token agency mismatch"}, status=401)

            request.user = user
            return self.get_response(request)
        finally:
            clear_current_agency()
