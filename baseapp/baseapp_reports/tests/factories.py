import factory
import swapper
from django.contrib.contenttypes.models import ContentType

from baseapp_core.tests.factories import UserFactory

Report = swapper.load_model("baseapp_reports", "Report")


class AbstractReportFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory(UserFactory)
    report_type = factory.Faker("random_element", elements=Report.ReportTypes)
    target_object_id = factory.SelfAttribute("target.id")
    target_content_type = factory.LazyAttribute(
        lambda o: ContentType.objects.get_for_model(o.target)
    )

    class Meta:
        exclude = ["target"]
        abstract = True
