from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser

User = get_user_model()


class UserPasswordExpiredException(Exception):
    user: AbstractUser

    def __init__(self, *args, user: AbstractUser, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
