import json

from social_core.exceptions import AuthException

from .models import SocialAuthAccessTokenCache


def cache_access_token(strategy, response, user=None, *args, **kwargs):
    if not user:
        data = strategy.request_data()

        access_token = response["access_token"]
        try:
            access_token = json.dumps(access_token)
        except:  # noqa
            pass

        oauth_token = data.get("oauth_token", "")
        oauth_verifier = data.get("oauth_verifier", "")
        code = data.get("code", "")
        if oauth_token and oauth_verifier:
            SocialAuthAccessTokenCache.objects.get_or_create(
                oauth_token=oauth_token,
                oauth_verifier=oauth_verifier,
                defaults={"access_token": access_token},
            )
        elif code:
            SocialAuthAccessTokenCache.objects.get_or_create(
                code=code, defaults={"access_token": access_token}
            )


def associate_by_email(strategy, response, user=None, *args, **kwargs):
    # Associate current auth with a user with the same email address in the DB.
    # This pipeline entry is not 100% secure unless you know that the providers
    # enabled enforce email verification on their side, otherwise a user can
    # attempt to take over another user account by using the same (not validated)
    # email address on some provider.  This pipeline entry is disabled by
    # default.
    provider = strategy.request.data["provider"]
    providers_to_trust = ["facebook", "apple-id", "google-oauth2"]
    if provider in providers_to_trust:
        email = response["email"]
        if email:
            backend = strategy.get_backend(provider)
            users = list(backend.strategy.storage.user.get_users_by_email(email))
            if len(users) == 0:
                return None
            elif len(users) > 1:
                raise AuthException(
                    backend, "The given email address is associated with another account"
                )
            else:
                return {"user": users[0], "is_new": False}
