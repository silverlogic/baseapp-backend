from django.http import Http404
from django.utils.encoding import uri_to_iri
from rest_framework.response import Response
from wagtail.contrib.redirects import models
from wagtail.contrib.redirects.api import RedirectsAPIViewSet
from wagtail.contrib.redirects.middleware import get_redirect
from wagtail.models import Site

from baseapp_wagtail.locale.utils import clear_pathname


class CustomRedirectsAPIViewSet(RedirectsAPIViewSet):
    body_fields = RedirectsAPIViewSet.body_fields + ["is_permanent"]
    html_path_queryset = None

    listing_default_fields = RedirectsAPIViewSet.listing_default_fields + [
        "is_permanent",
    ]

    def find_view(self, request):
        queryset = self.get_queryset()
        try:
            obj = self.find_object(queryset, request)
            if obj is None:
                raise self.model.DoesNotExist
        except (self.model.DoesNotExist, Http404):
            # Avoiding retrieving an error response so NextJs can cache the result
            return Response("not found")

        self.html_path_queryset = obj
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def find_object(self, queryset, request):
        if "html_path" in request.GET and (html_path := request.GET["html_path"]):
            redirect = self.get_redirect(
                request,
                html_path,
            )

            if not redirect:
                cleaned_html_path = clear_pathname(html_path)
                if cleaned_html_path != html_path:
                    redirect = self.get_redirect(
                        request,
                        cleaned_html_path,
                    )

            if redirect is None:
                raise Http404
            else:
                return redirect

        return super().find_object(queryset, request)

    def get_redirect(self, request, path):
        redirect = get_redirect(request, path)
        if redirect is None:
            redirect = self._get_redirect(request, path)
            if redirect is None:
                redirect = self._get_redirect(request, uri_to_iri(path))
        return redirect

    def _get_redirect(self, request, path):
        """
        If the default get_redirect fails, try to find it with a case insensitive query.
        """
        if "\0" in path:  # reject URLs with null characters, which crash on Postgres (#4496)
            return None

        site = Site.find_for_request(request)
        return models.Redirect.get_for_site(site).filter(old_path__iexact=path).first()

    def get_object(self):
        if self.html_path_queryset:
            return self.html_path_queryset
        return super().get_object()
