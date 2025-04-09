import factory
import swapper
from django.contrib.contenttypes.models import ContentType

from baseapp_core.tests.factories import UserFactory

Report = swapper.load_model("baseapp_reports", "Report")
ReportType = swapper.load_model("baseapp_reports", "ReportType")


class ReportTypeFactory(factory.django.DjangoModelFactory):
    key = factory.Faker("word")
    label = factory.Faker("word")

    class Meta:
        model = ReportType

    @factory.post_generation
    def set_content_types(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            self.content_types = [ContentType.objects.get_for_model(extracted)]


class AbstractReportFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory(UserFactory)
    report_type = factory.SubFactory(ReportTypeFactory)
    target_object_id = factory.SelfAttribute("target.id")
    target_content_type = factory.LazyAttribute(
        lambda o: ContentType.objects.get_for_model(o.target)
    )

    class Meta:
        exclude = ["target"]
        abstract = True
