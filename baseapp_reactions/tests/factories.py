import factory
import swapper
from django.contrib.contenttypes.models import ContentType

from baseapp_comments.tests.factories import get_content_type, get_obj_pk
from baseapp_core.tests.factories import UserFactory

Reaction = swapper.load_model("baseapp_reactions", "Reaction")


class AbstractReactionFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory(UserFactory)
    reaction_type = factory.Faker("random_element", elements=Reaction.ReactionTypes)

    target_object_id = factory.LazyAttribute(get_obj_pk("target"))
    target_content_type = factory.LazyAttribute(get_content_type("target"))

    class Meta:
        exclude = ["target"]
        abstract = True

    def __setattr__(self, name, value):
        super().__setattr__(name, value)

        if name in ["target"]:
            setattr(self, f"{name}_content_type", ContentType.objects.get_for_model(value))
            setattr(self, f"{name}_object_id", value.id)


class ReactionFactory(AbstractReactionFactory):
    class Meta:
        model = Reaction
