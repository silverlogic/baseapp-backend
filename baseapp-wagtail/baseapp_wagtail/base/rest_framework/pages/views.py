from django.http import Http404
from django.urls import path
from rest_framework.response import Response
from wagtail.api.v2.views import PagesAPIViewSet
from wagtail.models import Locale

from .serializers import CustomPageSerializer


class CustomPagesAPIEndpoint(PagesAPIViewSet):
    base_serializer_class = CustomPageSerializer
    path_view_queryset = None

    meta_fields = PagesAPIViewSet.meta_fields + [
        "url_path",
        "ancestors",
    ]

    def path_view(self, request):
        queryset = self.get_queryset()
        try:
            obj = self.find_object(queryset, request)
            if obj is None:
                raise self.model.DoesNotExist
        except self.model.DoesNotExist:
            raise Http404("not found")

        self.path_view_queryset = self._maybe_get_translated_page(request, obj)

        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def _maybe_get_translated_page(self, request, page):
        lang_code = request.GET.get("locale")
        if not lang_code:
            return page

        try:
            locale = Locale.objects.get(language_code=lang_code)
        except Locale.DoesNotExist:
            return page

        translation = page.get_translation_or_none(locale=locale)
        if not translation or not translation.live:
            return page

        return translation

    def get_object(self):
        if self.path_view_queryset:
            return self.path_view_queryset.specific
        return super().get_object()

    @classmethod
    def get_urlpatterns(cls):
        return [
            path("", cls.as_view({"get": "listing_view"}), name="listing"),
            path("<int:pk>/", cls.as_view({"get": "detail_view"}), name="detail"),
            path("find/", cls.as_view({"get": "find_view"}), name="find"),
            path("path/", cls.as_view({"get": "path_view"}), name="path"),
        ]
