from django.conf import settings

INVITATION_EXPIRATION_DAYS = getattr(settings, "INVITATION_EXPIRATION_DAYS", 7)
