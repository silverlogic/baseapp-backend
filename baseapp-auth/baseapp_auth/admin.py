from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .emails import new_superuser_notification_email, remove_superuser_notification_email
from .forms import UserChangeForm, UserCreationForm
from .models import PasswordValidation, SuperuserUpdateLog, User


@admin.register(User)
class UserAdmin(UserAdmin):
    fieldsets = (
        (None, {"fields": ("email", "password", "date_joined", "last_login")}),
        (
            _("Permissions"),
            {"fields": ("is_active", "is_superuser", "role", "permission_groups")},
        ),
        (_("Profile"), {"fields": (("first_name", "last_name"),)}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)
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
    )
    list_filter = ("date_joined", "is_superuser", "is_active")
    search_fields = ("first_name", "last_name", "email")
    ordering = ("id",)
    filter_horizontal = ()

    def save_model(self, request, obj, form, change):
        if change and obj.superuser_tracker.has_changed("is_superuser"):
            SuperuserUpdateLog.objects.create(
                assigner=request.user, assignee=obj, made_superuser=obj.is_superuser
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
        return False


@admin.register(PasswordValidation)
class PasswordValidationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "is_active",
    )
