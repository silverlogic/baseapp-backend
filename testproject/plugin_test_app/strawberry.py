"""Strawberry roots for plugin testing (mirror of the Graphene TestQueries/TestMutations)."""

import strawberry


@strawberry.type
class TestQueries:
    @strawberry.field
    def test_query(self) -> str | None:
        return "test_value"


@strawberry.type
class TestMutations:
    @strawberry.field
    def test_mutation(self) -> str | None:
        return "test_result"
