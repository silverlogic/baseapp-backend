import urllib.parse

from django.core.urlresolvers import reverse

import pytest


class ApiMixin:
    view_name = ''
    url_kwargs = None

    def reverse(self, view_name=None, query_params=None, **kwargs):
        # Specified in integration/vX/conftest.py
        version = pytest.api_version

        if self.url_kwargs is not None:
            kwargs.setdefault('kwargs', self.url_kwargs)

        if not view_name:
            view_name = self.view_name

        url = reverse('{}:{}'.format(version, view_name), **kwargs)

        if query_params:
            for param, value in query_params.items():
                if isinstance(value, list):
                    query_params[param] = ','.join(map(str, value))
            url += '?' + urllib.parse.urlencode(query_params)

        return url
