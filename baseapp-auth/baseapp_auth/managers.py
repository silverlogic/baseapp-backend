from django.contrib.auth.models import BaseUserManager

from baseapp_auth.querysets import UserQuerySet


class UserManager(BaseUserManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._queryset_class = UserQuerySet

    def _create_user(self, email, password, **extra_fields):
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_user(self, email, password=None, **extra_fields):
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields["is_superuser"] = True
        return self._create_user(email, password, **extra_fields)

    def get_queryset(self, *args, **kwargs) -> UserQuerySet:
        return super().get_queryset(*args, **kwargs).add_is_password_expired()
