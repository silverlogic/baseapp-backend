from rest_framework_simplejwt.tokens import AccessToken, RefreshToken


class ImpersonationRefreshToken(RefreshToken):
    """
    A refresh token whose access tokens never outlive it.

    `start_impersonation` caps the refresh token's `exp` at the session's expiry, so capping
    the access token at the same value keeps every token of a session inside it.
    """

    @property
    def access_token(self) -> AccessToken:
        access = super().access_token
        cap = self.payload.get("exp")
        if cap is not None and access["exp"] > cap:
            access["exp"] = cap
        return access
