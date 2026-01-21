from collections import defaultdict

from django.conf import settings
from django.contrib.auth.models import Permission
from django.forms.models import ModelChoiceIteratorValue
from django.forms.widgets import CheckboxSelectMultiple

from .utils.app_and_model_verbose_names import get_app_and_model_verbose_names


class GroupedPermissionWidget(CheckboxSelectMultiple):
    """
    A widget that displays permissions grouped by app and model.
    Permissions can be hidden based on settings.
    Settings:
        PERMISSIONS_HIDE_APPS: List of app labels to hide all permissions from.
        PERMISSIONS_HIDE_MODELS: List of "app_label.model" strings to hide specific model permissions.
    """

    template_name = "admin/widgets/grouped_permission_widget.html"

    class Media:
        js = ("baseapp_auth/js/grouped_permission_widget.js",)
        css = {"all": ("baseapp_auth/css/grouped_permission_widget.css",)}

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)

        value = set(str(v) for v in value or [])
        grouped = defaultdict(lambda: defaultdict(list))

        hide_apps = set(getattr(settings, "PERMISSIONS_HIDE_APPS", []))
        hide_models = set(getattr(settings, "PERMISSIONS_HIDE_MODELS", []))

        for option_value, option_label in self.choices:
            instance = self._resolve_permission_instance(option_value)
            if not instance:
                continue

            pk = instance.pk

            app_label = instance.content_type.app_label
            model = instance.content_type.model
            full_model = f"{app_label}.{model}"

            app_verbose, model_verbose = get_app_and_model_verbose_names(instance.content_type)

            if self._is_hidden(app_label, full_model, hide_apps, hide_models):
                continue

            # Use the permission's human-readable name as the label
            short_label = instance.name

            grouped[app_verbose][model_verbose].append(
                {
                    "value": pk,
                    "label": short_label,
                    "checked": str(pk) in value,
                }
            )

        context["grouped_permissions"] = {app: dict(models) for app, models in grouped.items()}

        return context

    def _resolve_permission_instance(self, option_value):
        """Resolve the Permission instance from the option value."""
        if option_value is None:
            return None

        if isinstance(option_value, ModelChoiceIteratorValue):
            return option_value.instance

        try:
            return Permission.objects.select_related("content_type").get(pk=option_value)
        except Permission.DoesNotExist:
            return None

    def _is_hidden(self, app_label, full_model, hide_apps, hide_models):
        """Determine if a permission should be hidden based on app and model."""
        return app_label in hide_apps or full_model in hide_models
