from apps.reactions.models import ReactableModel, update_reactions_count
from django.apps import apps
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *args, **options):
        for models in apps.all_models.values():
            for Model in models.values():
                if issubclass(Model, ReactableModel):
                    for obj in Model.objects.all():
                        update_reactions_count(obj)
