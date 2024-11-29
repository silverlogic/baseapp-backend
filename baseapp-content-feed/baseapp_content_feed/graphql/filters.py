import django_filters
import swapper
from django.db.models import Q

ContentPost = swapper.load_model("baseapp_content_feed", "ContentPost")
ContentPostImage = swapper.load_model("baseapp_content_feed", "ContentPostImage")


class ContentPostFilter(django_filters.FilterSet):
    class Meta:
        model = ContentPost
        fields = []

class ContentPostImageFilter(django_filters.FilterSet):
    class Meta:
        model = ContentPostImage
        fields = []
