from unittest.mock import Mock


def stripe_list(items) -> Mock:
    """Stand in for a Stripe ``ListObject``.

    The viewsets page through results with ``auto_paging_iter()`` while the
    serializers read ``.data``, so the stand-in has to answer both. A bare Mock
    auto-creates ``.data`` as another Mock, which fails only later, where the
    serializer tries to iterate it.
    """
    items = list(items)
    return Mock(data=items, auto_paging_iter=Mock(return_value=items))
