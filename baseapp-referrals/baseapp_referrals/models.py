from django.conf import settings
from django.db import models


class UserReferral(models.Model):
    referrer = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='referrals', on_delete=models.CASCADE)
    referee = models.OneToOneField(settings.AUTH_USER_MODEL, related_name='referred_by', on_delete=models.CASCADE)
