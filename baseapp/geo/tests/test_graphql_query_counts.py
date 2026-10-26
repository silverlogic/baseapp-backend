"""Query-count regression tests for the geoFeatures connection.

An N+1 here is silent: the data stays correct and only the query count moves. These tests are
the specification for GeoJSONFeatureObjectType.pre_optimization_hook and resolve_target.
"""

import pytest
import swapper
from django.contrib.contenttypes.models import ContentType

from baseapp_core.tests.factories import UserFactory

from .factories import GeoJSONFeatureFactory

pytestmark = pytest.mark.django_db

GeoJSONFeature = swapper.load_model("baseapp_geo", "GeoJSONFeature")

# Every properties field is backed by a model column, and `target` walks the DocumentId FK.
FULL_LIST_QUERY = """
    query {
        geoFeatures {
            totalCount
            edges {
                node {
                    id
                    bbox
                    geometry { type coordinates }
                    properties {
                        name
                        description
                        featureType
                        created
                        modified
                        target { id }
                    }
                }
            }
        }
    }
"""


def _count_for(graphql_client_with_queries, features: int) -> int:
    GeoJSONFeature.objects.all().delete()
    GeoJSONFeatureFactory.create_batch(features)
    ContentType.objects.clear_cache()
    response, queries = graphql_client_with_queries(FULL_LIST_QUERY)
    content = response.json()
    assert "errors" not in content, content
    assert len(content["data"]["geoFeatures"]["edges"]) == features
    return queries.count


class TestGeoFeaturesQueryCounts:
    def test_full_feature_list_is_five_queries(self, graphql_client_with_queries) -> None:
        GeoJSONFeatureFactory.create_batch(10)
        ContentType.objects.clear_cache()

        response, queries = graphql_client_with_queries(FULL_LIST_QUERY)
        content = response.json()

        assert "errors" not in content, content
        assert len(content["data"]["geoFeatures"]["edges"]) == 10
        # 5 queries, none of them per-row:
        # 1. ContentType lookup for geo.geojsonfeature (cold cache; cached in production)
        # 2. ContentType lookup for the target's model (same)
        # 3. SELECT COUNT(*) for totalCount / pagination
        # 4. SELECT geo_geojsonfeature for the page, with mapped_public_id inlined by the base
        #    pre_optimization_hook, target_document + its content type joined, and every
        #    `properties` column in only_fields so none is deferred
        # 5. SELECT users_user — the single GenericForeignKey prefetch of all 10 targets
        assert queries.count == 5, queries.log

    def test_count_does_not_grow_with_rows(self, graphql_client_with_queries) -> None:
        """The anti-N+1 property: 30 features cost the same as 10."""
        assert _count_for(graphql_client_with_queries, 10) == _count_for(
            graphql_client_with_queries, 30
        )

    def test_shared_target_is_fetched_once(self, graphql_client_with_queries) -> None:
        """Features pointing at the same object resolve it once, not once per feature."""
        user = UserFactory()
        GeoJSONFeature.objects.all().delete()
        GeoJSONFeatureFactory.create_batch(10, target=user)
        ContentType.objects.clear_cache()

        response, queries = graphql_client_with_queries(FULL_LIST_QUERY)

        assert "errors" not in response.json(), response.json()
        assert queries.count == 5, queries.log
