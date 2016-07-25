from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import ugettext_lazy as _

from .forms import UserChangeForm, UserCreationForm
from .models import User


@admin.register(User)
class UserAdmin(UserAdmin):
    fieldsets = (
        (None, {
            'fields': ('email', 'password', 'date_joined', 'last_login')
        }),
        (_('Permissions'), {
            'fields': ('is_active', 'is_superuser')
        }),
        (_('Profile'), {
            'fields': (('first_name', 'last_name'),)
        }),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
    )
    form = UserChangeForm
    add_form = UserCreationForm
    list_display = ('id', 'email', 'is_active', 'is_superuser',)
    list_filter = ('is_superuser', 'is_active',)
    search_fields = ('=email',)
    ordering = ('id',)
    filter_horizontal = ()
