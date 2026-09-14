from django.urls import path
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from wagtail.api.v2.views import PagesAPIViewSet

from .serializers import SitemapPageSerializer


class SitemapAPIViewSet(PagesAPIViewSet):
    base_serializer_class = SitemapPageSerializer
    body_fields = [
        "id",
        "type",
        "title",
        "url_path",
        "locale",
        "last_published_at",
    ]
    meta_fields = []

    # Wagtail's BaseAPIViewSet sets no permission_classes, so it inherits
    # REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]. These endpoints serve public pages;
    # pin them so a future tightening of that default cannot 401 the public site.
    permission_classes = (AllowAny,)

    @method_decorator(cache_page(60 * 60 * 1))  # 1 hour
    def listing_view(self, request):
        queryset = self.get_queryset()
        self.check_query_parameters(queryset)
        queryset = self.filter_queryset(queryset)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @classmethod
    def get_urlpatterns(cls):
        return [
            path("", cls.as_view({"get": "listing_view"}), name="listing"),
        ]
