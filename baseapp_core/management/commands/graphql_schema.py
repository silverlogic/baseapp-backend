from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from graphql import build_schema


class Command(BaseCommand):
    help = "Write the GraphQL schema as SDL, or check it against a committed SDL file."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--schema", help="Dotted path; defaults to settings.STRAWBERRY_SCHEMA.")
        parser.add_argument("--out", default="schema.graphql")
        parser.add_argument(
            "--check", action="store_true", help="Exit 1 when the schema differs from --out."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        from baseapp_core.strawberry.parity import compare_schemas
        from baseapp_core.strawberry.schema import get_schema

        schema = get_schema(options["schema"])
        out = Path(options["out"])
        if not options["check"]:
            out.write_text(schema.as_str() + "\n")
            self.stdout.write(f"Schema written to {out}")
            return
        diffs = compare_schemas(build_schema(out.read_text()), schema._schema)
        for diff in diffs:
            self.stdout.write(str(diff))
        if diffs:
            raise CommandError(f"{len(diffs)} differences from {out}")
        self.stdout.write(f"Schema matches {out}")
