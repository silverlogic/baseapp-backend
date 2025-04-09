from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

User = get_user_model()


class CustomClaimRefreshToken(RefreshToken):
    """
    Refresh token that always uses the most up-to-date claim data
    """

    def __init__(self, *args, ClaimSerializerClass=None, **kwargs) -> None:
        self.claim_serializer_class = ClaimSerializerClass
        super().__init__(*args, **kwargs)

    @property
    def access_token(self) -> AccessToken:
        access = super().access_token

        user = User.objects.get(id=access["user_id"])
        user_data = self.claim_serializer_class(user).data

        for key, value in user_data.items():
            access[key] = value

        return access
