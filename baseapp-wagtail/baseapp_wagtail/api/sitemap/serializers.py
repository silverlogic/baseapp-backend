from rest_framework.fields import Field
from wagtail.api.v2.serializers import PageSerializer as WagtailPageSerializer
from wagtail.api.v2.serializers import get_serializer_class

from baseapp_wagtail.api.pages.serializers import PageUrlPath


class PageTranslations(Field):
    def get_attribute(self, instance):
        return instance

    def to_representation(self, page):
        if not self._is_filtering_by_locale():
            return []
        translations = page.get_translations().live()
        translated_pages = []
        for translation in translations:
            serializer_class = get_serializer_class(
                translation.__class__,
                ["id", "type", "title", "url_path", "locale", "last_published_at"],
                meta_fields=["*"],
                base=SitemapPageSerializer,
            )
            serializer = serializer_class(context=self.context)
            translated_pages.append(serializer.to_representation(translation))
        return translated_pages

    def _is_filtering_by_locale(self):
        return "locale" in self.context["request"].GET


class SitemapPageSerializer(WagtailPageSerializer):
    url_path = PageUrlPath(read_only=True)
    translations = PageTranslations(source="*")
