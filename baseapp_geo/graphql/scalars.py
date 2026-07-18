from typing import Any, Dict, Optional

from django.contrib.gis.geos import GEOSGeometry
from graphql.language import ast
from graphql.utilities import value_from_ast_untyped
from graphql_geojson.types.geometry import Geometry as BaseGeometry


class Geometry(BaseGeometry):
    """GeoJSON geometry scalar with a graphene-3 compatible ``parse_literal``.

    Upstream django-graphql-geojson 0.1.4 targets graphql-core 2 AST names,
    so inline literals break on graphene 3. ``serialize``/``parse_value``
    (GEOSGeometry <-> GeoJSON dict | WKT | HEX) are inherited unchanged.
    """

    @classmethod
    def parse_literal(
        cls, node: ast.ValueNode, _variables: Optional[Dict[str, Any]] = None
    ) -> Optional[GEOSGeometry]:
        if isinstance(node, ast.StringValueNode):
            return cls.parse_value(node.value)
        if isinstance(node, ast.ObjectValueNode):
            return cls.parse_value(value_from_ast_untyped(node))
        return None
