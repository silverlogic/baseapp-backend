from functools import wraps
from importlib import import_module

from django.conf import settings
from graphql.error import GraphQLError


def user_passes_test(test_func):
    """
    Decorator for views that checks that the user passes the given test,
    redirecting to the log-in page if necessary. The test should be a callable
    that takes the user object and returns True if the user passes.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(cls, root, info, **data):
            if test_func(info.context.user):
                return view_func(cls, root, info, **data)
            raise GraphQLError(
                "authentication required",
                extensions={"code": "authentication_required"},
            )

        return _wrapped_view

    return decorator


def login_required(function):
    actual_decorator = user_passes_test(
        lambda u: u.is_authenticated,
    )
    if function:
        return actual_decorator(function)
    return actual_decorator


_graphql_loaded = False


def _ensure_graphql_loaded():
    """
    Ensure the GraphQL schema module is imported so that the
    Graphene global registry is populated.

    Raises:
        ModuleNotFoundError: if the schema module cannot be imported.
        ImportError: for other import-related errors.
    """
    global _graphql_loaded

    if _graphql_loaded:
        return

    schema_path = getattr(settings, "GRAPHENE", {}).get("SCHEMA")
    if not schema_path:
        # Nothing configured – don't keep trying on every call
        _graphql_loaded = True
        return

    module_path, _, _ = schema_path.rpartition(".")
    module_path = module_path or schema_path  # supports module or module.attr style

    try:
        import_module(module_path)
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(
            f"Could not import GraphQL schema module '{module_path}'. "
            "Check GRAPHENE['SCHEMA'] / GRAPHQL_SCHEMA_PATH."
        ) from e
    except ImportError as e:
        raise ImportError(f"Error importing GraphQL schema module '{module_path}': {e}") from e

    _graphql_loaded = True


def graphql_schema_required(func):
    """
    Decorator that ensures the GraphQL schema is imported (and thus
    the Graphene registry is populated) before calling `func`.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        _ensure_graphql_loaded()
        return func(*args, **kwargs)

    return wrapper
