from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS

from baseapp_message_templates.registry import sync_email_templates


class Command(BaseCommand):
    help = "Create a blank EmailTemplate row for every registered email template that has none."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--database", default=DEFAULT_DB_ALIAS)

    def handle(self, *args, **options) -> None:
        created = sync_email_templates(using=options["database"])
        self.stdout.write(f"Created {created} email template row(s).")
