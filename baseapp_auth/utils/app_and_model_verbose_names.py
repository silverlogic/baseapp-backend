from django.apps import apps


def get_app_and_model_verbose_names(content_type):
    """Retrieve the verbose names for the app and model from a ContentType."""
    try:
        app_config = apps.get_app_config(content_type.app_label)
        app_verbose = app_config.verbose_name
    except LookupError:
        app_verbose = content_type.app_label
    try:
        model_class = apps.get_model(content_type.app_label, content_type.model)
        model_verbose = model_class._meta.verbose_name
    except LookupError:
        model_verbose = content_type.model

    return app_verbose, model_verbose
