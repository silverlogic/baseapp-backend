from django.apps import apps
from django.core.management.base import BaseCommand

from apps.reactions.models import ReportableModel, update_reports_count


class Command(BaseCommand):
    def handle(self, *args, **options):
        for models in apps.all_models.values():
            for Model in models.values():
                if issubclass(Model, ReportableModel):
                    for obj in Model.objects.all():
                        update_reports_count(obj)
