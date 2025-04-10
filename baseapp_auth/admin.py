from constance import config
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .emails import (
    new_superuser_notification_email,
    remove_superuser_notification_email,
    send_password_expired_email,
)
from .forms import UserChangeForm, UserCreationForm
from .models import PasswordValidation, SuperuserUpdateLog

User = get_user_model()


class AbstractUserAdmin(UserAdmin):
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "email",
                    "password",
                    "preferred_language",
                    "date_joined",
                    "last_login",
                    "password_changed_date",
                )
            },
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Profile"), {"fields": (("first_name", "last_name", "phone_number"),)}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )
    form = UserChangeForm
    add_form = UserCreationForm
    list_display = (
        "id",
        "email",
        "first_name",
        "last_name",
        "date_joined",
        "is_active",
        "is_superuser",
        "is_password_expired",
    )
    list_filter = ("date_joined", "is_superuser", "is_active")
    search_fields = ("first_name", "last_name", "email", "phone_number")
    ordering = ("id",)
    filter_horizontal = ()
    actions = ["force_expire_password"]

    def force_expire_password(self, request, queryset):
        if not request.user.mfa_methods.filter(is_active=True).exists():
            self.message_user(
                request,
                _("You must be a superuser with MFA enabled to perform this action."),
                level=messages.ERROR,
            )
            return
        queryset.update(
            # Add extra time so the email doesn't get sent multiple times
            password_changed_date=timezone.now()
            - timezone.timedelta(days=config.USER_PASSWORD_EXPIRATION_INTERVAL + 7)
        )
        for user in queryset:
            send_password_expired_email(user)

    force_expire_password.short_description = "Expire password"

    def is_password_expired(self, obj):
        return obj.is_password_expired

    def save_model(self, request, obj, form, change):
        if change and hasattr(obj, "tracker") and obj.tracker.has_changed("is_superuser"):
            SuperuserUpdateLog.objects.create(
                assigner=request.user,
                assignee=obj,
                made_superuser=obj.is_superuser,
            )
            if obj.is_superuser:
                new_superuser_notification_email(obj, request.user)
            else:
                remove_superuser_notification_email(obj, request.user)

        super().save_model(request, obj, form, change)


@admin.register(SuperuserUpdateLog)
class SuperuserUpdateLogAdmin(admin.ModelAdmin):
    list_display = ("id", "assigner", "assignee", "made_superuser")
    list_display_links = None
    list_display = ("assigner", "assignee", "made_superuser", "created")

    def has_add_permission(self, request, obj=None):
        return False

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["show_save_and_continue"] = False
        extra_context["show_save"] = False
        return super(SuperuserUpdateLogAdmin, self).changeform_view(
            request, object_id, extra_context=extra_context
        )

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        return False


@admin.register(PasswordValidation)
class PasswordValidationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "is_active",
    )
