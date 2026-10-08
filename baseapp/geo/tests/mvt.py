"""Minimal Mapbox Vector Tile decoder for tests.

Reads the protobuf wire format of the MVT 2.1 spec directly, so tests need no protobuf-based
dependency (mapbox-vector-tile caps protobuf below the version baseapp locks). Decodes layers,
their extent, and each feature's type, properties and geometry in tile coordinates.
https://github.com/mapbox/vector-tile-spec/tree/master/2.1
"""

import struct
from collections.abc import Iterator

GEOMETRY_TYPES = {1: "Point", 2: "LineString", 3: "Polygon"}
MOVE_TO, LINE_TO, CLOSE_PATH = 1, 2, 7


def _varint(data: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def _fields(data: bytes) -> Iterator[tuple[int, int, int | bytes]]:
    """Yield `(field_number, wire_type, value)`; length-delimited values are bytes."""
    pos = 0
    while pos < len(data):
        key, pos = _varint(data, pos)
        field, wire_type = key >> 3, key & 7
        if wire_type == 0:
            value, pos = _varint(data, pos)
        elif wire_type == 1:
            value, pos = data[pos : pos + 8], pos + 8
        elif wire_type == 2:
            length, pos = _varint(data, pos)
            value, pos = data[pos : pos + length], pos + length
        elif wire_type == 5:
            value, pos = data[pos : pos + 4], pos + 4
        else:
            raise ValueError(f"Unsupported wire type {wire_type}")
        yield field, wire_type, value


def _packed(data: bytes) -> list[int]:
    values, pos = [], 0
    while pos < len(data):
        value, pos = _varint(data, pos)
        values.append(value)
    return values


def _zigzag(value: int) -> int:
    return (value >> 1) ^ -(value & 1)


def _value(data: bytes) -> str | float | int | bool | None:
    for field, _wire_type, raw in _fields(data):
        if field == 1:
            return raw.decode()
        if field == 2:
            return struct.unpack("<f", raw)[0]
        if field == 3:
            return struct.unpack("<d", raw)[0]
        if field in (4, 5):
            return raw if raw < 2**63 else raw - 2**64
        if field == 6:
            return _zigzag(raw)
        if field == 7:
            return bool(raw)
    return None


def _geometry(commands: list[int]) -> list[list[tuple[int, int]]]:
    """Decode drawing commands into parts (points, or rings), in tile coordinates."""
    parts, current, x, y, pos = [], [], 0, 0, 0
    while pos < len(commands):
        command, count = commands[pos] & 7, commands[pos] >> 3
        pos += 1
        if command == CLOSE_PATH:
            continue
        for _ in range(count):
            x += _zigzag(commands[pos])
            y += _zigzag(commands[pos + 1])
            pos += 2
            if command == MOVE_TO and current:
                parts.append(current)
                current = []
            current.append((x, y))
    if current:
        parts.append(current)
    return parts


def _feature(data: bytes, keys: list[str], values: list) -> dict:
    feature = {"type": None, "properties": {}, "geometry": []}
    for field, _wire_type, raw in _fields(data):
        if field == 2:
            tags = _packed(raw)
            for key_index, value_index in zip(tags[::2], tags[1::2]):
                feature["properties"][keys[key_index]] = values[value_index]
        elif field == 3:
            feature["type"] = GEOMETRY_TYPES.get(raw)
        elif field == 4:
            feature["geometry"] = _geometry(_packed(raw))
    return feature


def decode(tile: bytes) -> dict[str, dict]:
    """`{layer name: {"extent": int, "features": [feature, ...]}}`."""
    layers = {}
    for field, _wire_type, layer_data in _fields(tile):
        if field != 3:
            continue
        name, extent, keys, values, raw_features = None, 4096, [], [], []
        for layer_field, _layer_wire_type, raw in _fields(layer_data):
            if layer_field == 1:
                name = raw.decode()
            elif layer_field == 2:
                raw_features.append(raw)
            elif layer_field == 3:
                keys.append(raw.decode())
            elif layer_field == 4:
                values.append(_value(raw))
            elif layer_field == 5:
                extent = raw
        layers[name] = {
            "extent": extent,
            "features": [_feature(raw, keys, values) for raw in raw_features],
        }
    return layers
