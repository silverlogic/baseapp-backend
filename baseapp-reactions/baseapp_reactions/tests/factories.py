import factory
import swapper
from django.contrib.contenttypes.models import ContentType

Reaction = swapper.load_model("baseapp_reactions", "Reaction")

# from baseapp_auth.tests.factories import UserFactory


class AbstractReactionFactory(factory.django.DjangoModelFactory):
    # TO DO: user = factory.SubFactory(UserFactory)
    reaction_type = factory.Faker("random_element", elements=Reaction.ReactionTypes)
    target_object_id = factory.SelfAttribute("target.id")
    target_content_type = factory.LazyAttribute(
        lambda o: ContentType.objects.get_for_model(o.target)
    )

    class Meta:
        exclude = ["target"]
        abstract = True
