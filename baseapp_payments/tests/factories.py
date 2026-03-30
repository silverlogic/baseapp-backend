import factory
import swapper
from django.contrib.contenttypes.models import ContentType

from baseapp_core.tests.factories import UserFactory  # noqa


class _FakeTracker:
    """Minimal tracker shim to work around FieldTracker not propagating
    from abstract BaseCustomer to concrete Customer in model_utils 5.0."""

    def has_changed(self, field):
        return False


class CustomerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = swapper.load_model("baseapp_payments", "Customer")
        exclude = ["entity"]

    entity = factory.SubFactory(UserFactory)
    entity_type = factory.LazyAttribute(lambda o: ContentType.objects.get_for_model(o.entity))
    entity_id = factory.LazyAttribute(lambda o: o.entity.id)
    remote_customer_id = factory.Faker("uuid4")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        instance = model_class(**kwargs)
        instance.tracker = _FakeTracker()
        instance.save()
        return instance


class SubscriptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = swapper.load_model("baseapp_payments", "Subscription")

    remote_customer_id = factory.Faker("uuid4")
    remote_subscription_id = factory.Faker("uuid4")
