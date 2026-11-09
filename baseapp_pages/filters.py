import django_filters
import swapper

Page = swapper.load_model("baseapp_pages", "Page")


class PageFilter(django_filters.FilterSet):
    class Meta:
        model = Page
        fields = ["status"]
