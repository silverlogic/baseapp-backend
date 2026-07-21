from django.contrib.gis.geos import GEOSGeometry, Point
from graphql import parse
from graphql.language import ast

from baseapp_geo.graphql.scalars import Geometry


def _argument_value_node(document: str) -> ast.ValueNode:
    operation = parse(document).definitions[0]
    field = operation.selection_set.selections[0]
    return field.arguments[0].value


class TestParseValue:
    def test_geojson_dict(self):
        geom = Geometry.parse_value({"type": "Point", "coordinates": [1.0, 2.0]})

        assert isinstance(geom, GEOSGeometry)
        assert geom.geom_type == "Point"
        assert geom.coords == (1.0, 2.0)

    def test_wkt(self):
        geom = Geometry.parse_value("POINT (1 2)")

        assert isinstance(geom, GEOSGeometry)
        assert geom.geom_type == "Point"
        assert geom.coords == (1.0, 2.0)

    def test_hex(self):
        hex_value = Point(1, 2, srid=4326).hexewkb.decode()

        geom = Geometry.parse_value(hex_value)

        assert isinstance(geom, GEOSGeometry)
        assert geom.geom_type == "Point"
        assert geom.coords == (1.0, 2.0)
        assert geom.srid == 4326


class TestParseLiteral:
    def test_string_value_node(self):
        node = _argument_value_node('{ features(geometry: "POINT (1 2)") { id } }')
        assert isinstance(node, ast.StringValueNode)

        geom = Geometry.parse_literal(node)

        assert isinstance(geom, GEOSGeometry)
        assert geom.geom_type == "Point"
        assert geom.coords == (1.0, 2.0)

    def test_object_value_node(self):
        node = _argument_value_node(
            '{ features(geometry: {type: "Point", coordinates: [1, 2]}) { id } }'
        )
        assert isinstance(node, ast.ObjectValueNode)

        geom = Geometry.parse_literal(node)

        assert isinstance(geom, GEOSGeometry)
        assert geom.geom_type == "Point"
        assert geom.coords == (1.0, 2.0)

    def test_object_value_node_resolves_variables(self):
        node = _argument_value_node(
            "query($coords: [Float]!) "
            '{ features(geometry: {type: "Point", coordinates: $coords}) { id } }'
        )
        assert isinstance(node, ast.ObjectValueNode)

        geom = Geometry.parse_literal(node, {"coords": [3.0, 4.0]})

        assert isinstance(geom, GEOSGeometry)
        assert geom.geom_type == "Point"
        assert geom.coords == (3.0, 4.0)

    def test_non_handled_node_returns_none(self):
        node = _argument_value_node("{ features(geometry: 42) { id } }")
        assert isinstance(node, ast.IntValueNode)

        assert Geometry.parse_literal(node) is None


class TestSerialize:
    def test_returns_geojson_dict(self):
        result = Geometry.serialize(Point(1, 2, srid=4326))

        assert result == {"type": "Point", "coordinates": [1.0, 2.0]}
