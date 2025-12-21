from django.contrib import admin
from django.contrib.auth import get_user_model

from baseapp_auth.admin import AbstractUserAdmin, CustomGroupAdmin
from django.contrib.auth.models import Group
User = get_user_model()


@admin.register(User)
class UserAdmin(AbstractUserAdmin):
    pass


@admin.register(Group)
class GroupAdmin(CustomGroupAdmin):
    pass
