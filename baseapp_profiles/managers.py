from django.db import models


class ProfileManager(models.Manager):
    def filter_user_profiles(self, user) -> models.QuerySet:
        return self.filter(models.Q(members__user=user) | models.Q(owner=user)).distinct()

    def get_if_member(self, user, **kwargs) -> models.Model | None:
        if user.is_superuser:
            return self.get(**kwargs)
        return self.filter(models.Q(members__user=user) | models.Q(owner=user), **kwargs).first()
