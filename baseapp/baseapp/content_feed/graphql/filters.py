import django_filters
import swapper

ContentPost = swapper.load_model("baseapp_content_feed", "ContentPost")


class ContentPostFilter(django_filters.FilterSet):
    class Meta:
        model = ContentPost
        fields = []
