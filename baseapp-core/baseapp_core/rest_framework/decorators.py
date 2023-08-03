from django.forms.utils import pretty_name
from rest_framework.decorators import MethodMapper


def action(methods=None, detail=None, url_path=None, url_name=None, **kwargs):
    """
    using this decorator instead of @action from rest_framework.decorators to replace _ with - for the url_path
    """
    methods = ["get"] if (methods is None) else methods
    methods = [method.lower() for method in methods]

    assert detail is not None, "@action() missing required argument: 'detail'"

    # name and suffix are mutually exclusive
    if "name" in kwargs and "suffix" in kwargs:
        raise TypeError("`name` and `suffix` are mutually exclusive arguments.")

    def decorator(func):
        func.mapping = MethodMapper(func, methods)

        func.detail = detail
        func.url_path = url_path if url_path else func.__name__.replace("_", "-")
        func.url_name = url_name if url_name else func.__name__.replace("_", "-")

        func.kwargs = kwargs

        if "name" not in kwargs and "suffix" not in kwargs:
            func.kwargs["name"] = pretty_name(func.__name__)
        func.kwargs["description"] = func.__doc__ or None

        return func

    return decorator
