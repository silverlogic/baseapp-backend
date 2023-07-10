from django.contrib import admin
from django.contrib.auth import get_user_model

from baseapp_auth.admin import AbstractUserAdmin

User = get_user_model()


@admin.register(User)
class UserAdmin(AbstractUserAdmin):
    pass
