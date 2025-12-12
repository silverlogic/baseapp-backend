from django.conf import settings
from django.core.management.commands import shell


class Command(shell.Command):
    def get_auto_imports(self):
        print("its getting called")
        imports = super().get_auto_imports()
        schema_path = settings.GRAPHENE.get("SCHEMA")
        if schema_path:
            imports.append(schema_path)
        return imports
