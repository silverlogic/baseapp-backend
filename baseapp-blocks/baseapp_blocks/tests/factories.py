import factory
import swapper
from django.contrib.contenttypes.models import ContentType


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


class BlockFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = swapper.load_model("baseapp_blocks", "Block")
