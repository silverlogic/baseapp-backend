"""The served schema is the frontend's contract: it must equal the committed SDL.

After an intentional schema change, refresh the snapshot:
`manage.py graphql_schema --out testproject/schema.graphql`.
"""

from pathlib import Path

from graphql import build_schema

from baseapp_core.strawberry.parity import compare_schemas
from baseapp_core.strawberry.schema import get_schema

SNAPSHOT = Path(__file__).resolve().parents[2] / "testproject" / "schema.graphql"


def test_schema_matches_committed_sdl() -> None:
    diffs = compare_schemas(build_schema(SNAPSHOT.read_text()), get_schema()._schema)
    assert not diffs, "\n".join(str(d) for d in diffs)
