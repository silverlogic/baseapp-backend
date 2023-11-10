import urllib.parse

from django.urls import reverse


class ApiMixin:
    view_name = ""
    url_kwargs = None
    api_version = "v1"

    def reverse(self, view_name=None, query_params=None, **kwargs):
        if self.url_kwargs is not None:
            kwargs.setdefault("kwargs", self.url_kwargs)

        if not view_name:
            view_name = self.view_name

        url = reverse("{}:{}".format(self.api_version, view_name), **kwargs)

        if query_params:
            url += "?" + urllib.parse.urlencode(query_params, doseq=True)

        return url
