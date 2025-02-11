from baseapp_auth.admin import AbstractUserAdmin
from django.contrib import admin
from django.contrib.auth import get_user_model

User = get_user_model()


@admin.register(User)
class UserAdmin(AbstractUserAdmin):
    pass
