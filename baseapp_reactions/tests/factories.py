import factory
import swapper

from baseapp_core.models import DocumentId
from baseapp_core.tests.factories import UserFactory

Reaction = swapper.load_model("baseapp_reactions", "Reaction")


class AbstractReactionFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory(UserFactory)
    reaction_type = factory.Faker("random_element", elements=Reaction.ReactionTypes)
    target_document = factory.LazyAttribute(lambda o: DocumentId.get_or_create_for_object(o.target))

    class Meta:
        exclude = ["target"]
        abstract = True


class ReactionFactory(AbstractReactionFactory):
    class Meta:
        model = Reaction
