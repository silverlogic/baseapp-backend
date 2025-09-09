import uuid


def is_uuid4(s: str) -> bool:
    try:
        val = uuid.UUID(s, version=4)
    except ValueError:
        return False
    return str(val) == s.lower()
