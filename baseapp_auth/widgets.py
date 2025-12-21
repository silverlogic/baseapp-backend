from collections import defaultdict
from django.forms.widgets import CheckboxSelectMultiple
from django.conf import settings
from django.contrib.auth.models import Permission
from django.forms.models import ModelChoiceIteratorValue
from django.apps import apps


def get_app_and_model_verbose_names(content_type):
    """
    Returns a tuple: (app_verbose_name, model_verbose_name)

    Always safe:
    - Falls back to app_label / model name if resolution fails
    """
    app_config = apps.get_app_config(content_type.app_label)
    app_verbose = getattr(app_config, "verbose_name", content_type.app_label)

    try:
        model_class = app_config.get_model(content_type.model)
        model_verbose = model_class._meta.verbose_name
    except LookupError:
        model_verbose = content_type.model

    return app_verbose, model_verbose


class GroupedPermissionWidget(CheckboxSelectMultiple):
    template_name = "admin/widgets/grouped_permission_widget.html"

    class Media:
        js = ("baseapp_auth/js/grouped_permissions.js",)
        css = {"all": ("baseapp_auth/css/grouped_permissions.css",)}

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)

        value = set(str(v) for v in value or [])
        grouped = defaultdict(lambda: defaultdict(list))

        hide_apps = set(getattr(settings, "PERMISSIONS_HIDE_APPS", []))
        hide_models = set(getattr(settings, "PERMISSIONS_HIDE_MODELS", []))

        for option_value, option_label in self.choices:
            if option_value is None:
                continue

            if isinstance(option_value, ModelChoiceIteratorValue):
                pk = option_value.value
                instance = option_value.instance
            else:
                pk = option_value
                instance = None

            if not instance:
                try:
                    instance = Permission.objects.select_related(
                        "content_type"
                    ).get(pk=pk)
                except Permission.DoesNotExist:
                    continue

            app_label = instance.content_type.app_label
            model = instance.content_type.name
            full_model = f"{app_label}.{model}"


            app_verbose, model_verbose = get_app_and_model_verbose_names(
                instance.content_type
            )

            # FILTERS
            if app_label in hide_apps:
                continue

            if full_model in hide_models:
                continue

            # CLEAN LABEL
            short_label = instance.name

            grouped[app_verbose][model_verbose].append({
                "value": pk,
                "label": short_label,
                "checked": str(pk) in value,
            })

        context["grouped_permissions"] = {
            app: dict(models)
            for app, models in grouped.items()
        }

        return context
