import factory
import swapper

from baseapp_core.models import DocumentId
from baseapp_core.tests.factories import UserFactory

RateModel = swapper.load_model("baseapp_ratings", "Rate")


class AbstractRateFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory(UserFactory)
    target_document = factory.LazyAttribute(lambda o: DocumentId.get_or_create_for_object(o.target))
    value = factory.Faker("random_int", min=1, max=5)

    class Meta:
        exclude = ["target"]
        abstract = True


class RateFactory(AbstractRateFactory):
    class Meta:
        model = RateModel
