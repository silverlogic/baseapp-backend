from django.apps import apps
from django.contrib import admin


def get_model_admin_classes():
    """
    Returns appropriate admin classes based on whether 'unfold' is installed.
    If unfold is available, use its enhanced admin classes, otherwise fallback to Django's default admin classes.
    """
    try:
        if apps.is_installed("unfold"):
            from unfold.admin import ModelAdmin, StackedInline, TabularInline
        else:
            raise ImportError("unfold not in INSTALLED_APPS")
    except ImportError:
        ModelAdmin = admin.ModelAdmin
        StackedInline = admin.StackedInline
        TabularInline = admin.TabularInline

    return {
        "ModelAdmin": ModelAdmin,
        "StackedInline": StackedInline,
        "TabularInline": TabularInline,
    }


admin_classes = get_model_admin_classes()

ModelAdmin = admin_classes["ModelAdmin"]
StackedInline = admin_classes["StackedInline"]
TabularInline = admin_classes["TabularInline"]
