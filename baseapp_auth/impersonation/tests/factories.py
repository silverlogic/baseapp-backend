import factory
from django.utils import timezone

from baseapp_auth.tests.factories import UserFactory


class ImpersonationSessionFactory(factory.django.DjangoModelFactory):
    impersonator = factory.SubFactory(UserFactory, is_superuser=True)
    target = factory.SubFactory(UserFactory)
    reason = "Support ticket 42"
    expires_at = factory.LazyFunction(lambda: timezone.now() + timezone.timedelta(hours=1))

    class Meta:
        model = "baseapp_impersonation.ImpersonationSession"
