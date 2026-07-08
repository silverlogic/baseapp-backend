"""
Test GraphQL queries for plugin testing.
"""

import graphene


class TestQueries:
    """Test GraphQL queries mixin."""

    test_query = graphene.String()

    def resolve_test_query(self, info):
        """Resolve test query."""
        return "test_value"
