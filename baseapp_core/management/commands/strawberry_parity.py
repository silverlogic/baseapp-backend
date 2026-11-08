from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils.module_loading import import_string


class Command(BaseCommand):
    help = "Diff the Strawberry schema against the Graphene schema (migration progress)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--graphene", default="testproject.graphql.schema")
        parser.add_argument("--strawberry", default="testproject.strawberry_schema.schema")
        parser.add_argument("--type", action="append", dest="types", default=[])
        parser.add_argument("--missing", action="store_true", help="List unported types too.")
        parser.add_argument("--strict", action="store_true", help="Exit 1 on any difference.")

    def handle(self, *args: Any, **options: Any) -> None:
        from baseapp_core.strawberry.parity import compare_schemas, missing_types

        graphene = import_string(options["graphene"]).graphql_schema
        strawberry = import_string(options["strawberry"])._schema
        diffs = compare_schemas(graphene, strawberry)
        if options["types"]:
            diffs = [d for d in diffs if d.path.split(".")[0].split("(")[0] in options["types"]]
        for diff in diffs:
            self.stdout.write(str(diff))
        missing = missing_types(graphene, strawberry)
        if options["missing"]:
            for name in missing:
                self.stdout.write(f"{name}: not ported")
        self.stdout.write(
            f"{len(diffs)} differences, {len(missing)} of {len(graphene.type_map)} types not ported"
        )
        if options["strict"] and (diffs or missing):
            raise CommandError("Schemas differ")
