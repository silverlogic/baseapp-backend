import factory
from django.contrib.contenttypes.models import ContentType

from baseapp_content_feed.models import SwappedContentPost as ContentPost

# def get_content_type(field_name):
#     def _obj_content_type(obj):
#         if not hasattr(obj, field_name):
#             return None
#         fk_obj = getattr(obj, "target", None)
#         if fk_obj:
#             return ContentType.objects.get_for_model(obj.target)

#     return _obj_content_type


# def get_obj_pk(field_name):
#     def _obj_id(obj):
#         if not hasattr(obj, field_name):
#             return None
#         return getattr(obj, field_name).pk

#     return _obj_id


class AbstractContentPostFactory(factory.django.DjangoModelFactory):
    author = factory.SubFactory("baseapp_core.tests.factories.UserFactory")
    content = factory.Faker("text")

    class Meta:
        abstract = True


class ContentPostFactory(AbstractContentPostFactory):
    class Meta:
        model = ContentPost
