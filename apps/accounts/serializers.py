from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class AgencyTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Adds agency_id and role codes to the JWT."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["agency_id"] = str(user.agency_id)
        token["roles"] = list(
            user.user_roles.values_list("role__name", flat=True)
        )
        return token
