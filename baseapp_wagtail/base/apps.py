from django.apps import AppConfig


class WagtailConfig(AppConfig):
    name = "baseapp_wagtail.base"
    verbose_name = "BaseApp Wagtail - Base"
    label = "baseapp_wagtail_base"

    def ready(self):
        from grapple.registry import registry

        from baseapp_pages.urlpath_registry import urlpath_registry
        from baseapp_wagtail.base.graphql.object_types import WagtailPageObjectType

        for model_type in registry.pages.keys():
            urlpath_registry.register_type(model_type, WagtailPageObjectType)
