from unittest.mock import Mock


def stripe_list(items) -> Mock:
    """Stand in for a Stripe ``ListObject``.

    The viewsets page through results with ``auto_paging_iter()`` rather than
    reading ``.data``, so that is what these mocks need to answer.
    """
    return Mock(auto_paging_iter=Mock(return_value=list(items)))
