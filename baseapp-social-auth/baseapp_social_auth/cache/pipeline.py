import json

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
