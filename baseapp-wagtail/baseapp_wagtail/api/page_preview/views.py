from django.contrib.contenttypes.models import ContentType
from rest_framework.response import Response
from wagtail.api.v2.views import PagesAPIViewSet
from wagtail_headless_preview.models import PagePreview

from ..pages.views import CustomPagesAPIEndpoint


class PagePreviewAPIViewSet(CustomPagesAPIEndpoint):
    known_query_parameters = PagesAPIViewSet.known_query_parameters.union(["content_type", "token"])

    def listing_view(self, request):
        # Delegate to detail_view, specifically so there's no
        # difference between serialization formats.
        self.action = "detail_view"
        return self.detail_view(request, 0)

    def detail_view(self, request, pk):
        page = self.get_object()
        serializer = self.get_serializer(page)
        return Response(serializer.data)

    def get_object(self):
        app_label, model = self.request.GET["content_type"].split(".")
        content_type = ContentType.objects.get(app_label=app_label, model=model)

        page_preview = PagePreview.objects.get(
            content_type=content_type, token=self.request.GET["token"]
        )
        page = page_preview.as_page()
        if not page.pk:
            # fake primary key to stop API URL routing from complaining
            page.pk = 0

        return page.specific
