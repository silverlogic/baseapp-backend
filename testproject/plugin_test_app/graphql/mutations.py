"""
Test GraphQL mutations for plugin testing.
"""

import graphene


class TestMutations:
    """Test GraphQL mutations mixin."""

    test_mutation = graphene.String()

    def resolve_test_mutation(self, info):
        """Resolve test mutation."""
        return "test_result"
