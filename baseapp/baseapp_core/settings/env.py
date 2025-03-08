import ast
import os
import sys

from django.core.exceptions import ImproperlyConfigured


def env(key, *args, **kwargs):
    """
    Retrieves environment variables and returns Python natives. The (optional)
    default will be returned if the environment variable does not exist.
    """
    try:
        value = os.environ[key]
        return ast.literal_eval(value)
    except (SyntaxError, ValueError):
        value = value.replace("**newline**", "\n")
        return value
    except KeyError:
        if "default" in kwargs:
            return kwargs["default"]
        if len(args) > 0:
            return args[0]
        if "required" in kwargs and not kwargs["required"]:
            return None
        raise ImproperlyConfigured("Missing required environment variable '%s'" % key)


def is_uvicorn():
    return any("uvicorn" in arg for arg in sys.argv)
