import factory
import swapper
from django.contrib.contenttypes.models import ContentType

from baseapp_core.tests.factories import UserFactory

RateModel = swapper.load_model("baseapp_ratings", "Rate")


def get_content_type(field_name):
    def _obj_content_type(obj):
        if not hasattr(obj, field_name):
            return None
        fk_obj = getattr(obj, "target", None)
        if fk_obj:
            return ContentType.objects.get_for_model(obj.target)

    return _obj_content_type


def get_obj_pk(field_name):
    def _obj_id(obj):
        if not hasattr(obj, field_name):
            return None
        return getattr(obj, field_name).pk

    return _obj_id


class AbstractRateFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory(UserFactory)
    target_object_id = factory.LazyAttribute(get_obj_pk("target"))
    target_content_type = factory.LazyAttribute(get_content_type("target"))
    value = factory.Faker("random_int", min=1, max=5)

    class Meta:
        exclude = ["target"]
        abstract = True

    def __setattr__(self, name, value):
        super().__setattr__(name, value)

        if name in ["target"]:
            setattr(self, f"{name}_content_type", ContentType.objects.get_for_model(value))
            setattr(self, f"{name}_object_id", value.id)


class RateFactory(AbstractRateFactory):
    class Meta:
        model = RateModel
