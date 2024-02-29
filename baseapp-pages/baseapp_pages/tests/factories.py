import factory
import swapper

from baseapp_pages.models import URLPath

Page = swapper.load_model("baseapp_pages", "Page")


class PageFactory(factory.django.DjangoModelFactory):
    status = Page.PageStatus.PUBLISHED

    class Meta:
        model = Page


class URLPathFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = URLPath
