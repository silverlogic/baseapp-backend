# pragma: no cover

import typing

from django.apps import apps
from django.core.management.base import BaseCommand

from baseapp_api_key.models import BaseAPIKey


class Command(BaseCommand):
    help = f"{BaseAPIKey._meta.verbose_name.title()} Management"

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            type=str,
            required=True,
            help=f"The concrete {BaseAPIKey._meta.verbose_name.title()} to use",
            choices=[
                m._meta.label
                for m in apps.get_models()
                if isinstance(m, type) and issubclass(m, BaseAPIKey) and not m._meta.abstract
            ],
        )
        parser.add_argument("--generate_encryption_key", action="store_true", default=False)
        parser.add_argument(
            "--rotate_encryption_key",
            action="append",
            nargs=2,
            metavar=("BA_API_KEY_ENCRYPTION_KEY_OLD", "BA_API_KEY_ENCRYPTION_KEY_NEW"),
            help="Rotate BA_API_KEY_ENCRYPTION_KEY",
        )

    def handle(self, *args, **options):
        try:
            model: str = options.pop("model")
            APIKeyModel = apps.get_model(model)

            self._handle(*args, APIKeyModel=APIKeyModel, **options)
        except BaseException as e:
            self.stdout.write("\r\n")
            if isinstance(e, KeyboardInterrupt):
                return
            raise e

    def _handle(self, *args, APIKeyModel: typing.Type[BaseAPIKey], **options):
        if options.get("generate_encryption_key"):
            encryption_key = APIKeyModel.objects.generate_encryption_key()
            self.stdout.write(self.style.SUCCESS(f"\n{encryption_key}\n"))
        if _args := options.get("rotate_encryption_key"):

            def _mask(k: str) -> str:
                return f"{k[:6]}…{k[-4:]}" if len(k) > 10 else "********"

            encryption_key_old, encryption_key_new = _args[0]
            self.stdout.write(self.style.NOTICE("\nRotating BA_API_KEY_ENCRYPTION_KEY"))
            self.stdout.write(self.style.SUCCESS(f"OLD: {_mask(encryption_key_old)}"))
            self.stdout.write(self.style.SUCCESS(f"NEW: {_mask(encryption_key_new)}"))

            APIKeyModel.objects.rotate_encryption_key(
                encryption_key_old=encryption_key_old,
                encryption_key_new=encryption_key_new,
            )

            self.stdout.write(self.style.SUCCESS("\nRotated BA_API_KEY_ENCRYPTION_KEY\n"))
