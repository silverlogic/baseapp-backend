from urllib.parse import urlparse, urlunparse

from django.contrib.auth import REDIRECT_FIELD_NAME
from django.http import HttpResponseRedirect, QueryDict
from django.urls import resolve, reverse
from django.utils.deprecation import MiddlewareMixin as BaseMiddleware


class CheckIsPasswordExpiredMiddleware(BaseMiddleware):
    def process_request(self, request):
        if request.user.is_authenticated is False or request.user.is_password_expired is False:
            return
        target_url = resolve(request.path).url_name
        if target_url is None:
            return
        if target_url not in ["change-expired-password"]:
            change_expired_password_url = reverse("change-expired-password")
            url_parts = list(urlparse(change_expired_password_url))
            query_string = QueryDict(url_parts[4], mutable=True)
            query_string[REDIRECT_FIELD_NAME] = target_url
            url_parts[4] = query_string.urlencode(safe="/")
            return HttpResponseRedirect(urlunparse(url_parts))
