import factory
import swapper

from ..models import get_document_id_for_object


class FollowFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = swapper.load_model("baseapp_follows", "Follow")

    target_is_following_back = False

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        actor_object = kwargs.pop("actor_object", None)
        target_object = kwargs.pop("target_object", None)

        if actor_object:
            kwargs["actor"] = get_document_id_for_object(actor_object)

        if target_object:
            kwargs["target"] = get_document_id_for_object(target_object)

        return super()._create(model_class, *args, **kwargs)
