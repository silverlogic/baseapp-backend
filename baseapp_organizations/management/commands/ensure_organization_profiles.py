from django.core.management.base import BaseCommand

from baseapp_organizations.services import ensure_profiles_for_organizations


class Command(BaseCommand):
    help = "Give every organization without a profile an ownerless one."

    def handle(self, *args, **options) -> None:
        created = ensure_profiles_for_organizations()
        self.stdout.write(f"Created {created} organization profile(s).")
