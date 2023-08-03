from django.db import models
from model_utils.models import TimeStampedModel


class SocialAuthAccessTokenCache(TimeStampedModel):
    """
    An access token can only be retrieved from the social
    provider one time for each set of credentials.  Sometimes
    social auth requires more than 1 step (e.g. if an email
    is not retrieved).  In this case more than 1 request will
    be required.  Requests after the first will fail because
    the access token cannot be retrieved again.  This class
    caches the access token so we don't have to exchange
    credentials for an access token more than once.
    """

    access_token = models.TextField()

    # OAuth1
    oauth_token = models.TextField(blank=True)
    oauth_verifier = models.TextField(blank=True)

    # OAuth2
    code = models.TextField(blank=True)
