import factory
import swapper
from django.contrib.contenttypes.models import ContentType

from baseapp_core.models import DocumentId


class FollowFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = swapper.load_model("baseapp_follows", "Follow")

    target_is_following_back = False

    class Params:
        actor_object = None
        target_object = None

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        actor_object = kwargs.pop("actor_object", None)
        target_object = kwargs.pop("target_object", None)

        if actor_object:
            ct = ContentType.objects.get_for_model(actor_object)
            kwargs["actor"] = DocumentId.objects.get(content_type=ct, object_id=actor_object.pk)

        if target_object:
            ct = ContentType.objects.get_for_model(target_object)
            kwargs["target"] = DocumentId.objects.get(content_type=ct, object_id=target_object.pk)

        return super()._create(model_class, *args, **kwargs)
