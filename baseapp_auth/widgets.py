from collections import defaultdict

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import Permission
from django.forms.models import ModelChoiceIteratorValue
from django.forms.widgets import CheckboxSelectMultiple


def get_app_and_model_verbose_names(content_type):
    """
    Returns a tuple: (app_verbose_name, model_verbose_name)

    Always safe:
    - Falls back to app_label / model name if resolution fails
    """
    try:
        app_config = apps.get_app_config(content_type.app_label)
        app_verbose = app_config.verbose_name
    except LookupError:
        app_config = None
        app_verbose = content_type.app_label
    try:
        model_class = apps.get_model(content_type.model)
        model_verbose = model_class._meta.verbose_name
    except LookupError:
        model_verbose = content_type.model

    return app_verbose, model_verbose


class GroupedPermissionWidget(CheckboxSelectMultiple):
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

            # CLEAN LABEL
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
        if option_value is None:
            return None

        if isinstance(option_value, ModelChoiceIteratorValue):
            return option_value.instance

        try:
            return Permission.objects.select_related("content_type").get(pk=option_value)
        except Permission.DoesNotExist:
            return None

    def _is_hidden(self, app_label, full_model, hide_apps, hide_models):
        return app_label in hide_apps or full_model in hide_models
