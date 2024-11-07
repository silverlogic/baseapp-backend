from functools import wraps
from urllib.parse import urlparse, urlunparse

from allauth.account.utils import get_next_redirect_url
from allauth.mfa.utils import is_mfa_enabled
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.http import HttpResponseRedirect, QueryDict
from django.urls import reverse


def mfa_required(function=None):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapper_view(request, *args, **kwargs):
            if (
                all([request.user.is_authenticated, request.user.is_staff, request.user.is_active])
                is False
            ):
                return view_func(request, *args, **kwargs)

            if is_mfa_enabled(request.user):
                return view_func(request, *args, **kwargs)
            else:
                next_url = get_next_redirect_url(request) or request.get_full_path()
                target_url = reverse("mfa_required")
                url_parts = list(urlparse(target_url))
                query_string = QueryDict(url_parts[4], mutable=True)
                query_string[REDIRECT_FIELD_NAME] = next_url
                url_parts[4] = query_string.urlencode(safe="/")
                target_url = urlunparse(url_parts)
                return HttpResponseRedirect(target_url)

        return _wrapper_view

    if function:
        return decorator(function)
    return decorator
