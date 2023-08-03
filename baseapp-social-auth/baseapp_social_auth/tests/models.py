from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
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

    def create_user_without_password(self, email, **extra_fields):
        user = self.model(email=email, **extra_fields)
        user.set_unusable_password()
        user.save()
        return user


class User(AbstractBaseUser):
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)

    USERNAME_FIELD = "email"

    objects = UserManager()
