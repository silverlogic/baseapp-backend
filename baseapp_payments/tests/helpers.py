from collections.abc import Iterable
from functools import cache
from typing import Any
from unittest.mock import Mock

import stripe


def stripe_object(data: dict[str, Any]) -> stripe.StripeObject:
    """A real Stripe object built from ``data``, nested dicts included.

    Fakes should be the shape the pinned stripe library returns. Since stripe-python 15 a
    StripeObject is no longer a dict, so a plain-dict fake hides the code paths that would
    break on a real response (``.get()``, ``isinstance(x, dict)``, JSON rendering).
    """
    return stripe.StripeObject.construct_from(data, "sk_test_fake")


def stripe_list(items: Iterable[Any]) -> Mock:
    """Stand in for a Stripe ``ListObject``.

    The viewsets page through results with ``auto_paging_iter()`` while the
    serializers read ``.data``, so the stand-in has to answer both. A bare Mock
    auto-creates ``.data`` as another Mock, which fails only later, where the
    serializer tries to iterate it.
    """
    items = list(items)
    return Mock(data=items, auto_paging_iter=Mock(return_value=items))


@cache
def holdable_order_proxy() -> type:
    """A proxy of the test project's card hold target, defined once per test session: the
    test project ships none, and a proxy needs no table (nor a migration to test with)."""
    from testproject.testapp.models import HoldableOrder

    class HoldableOrderProxy(HoldableOrder):
        class Meta:
            proxy = True
            app_label = "testapp"

    return HoldableOrderProxy


def grant_card_hold_perm(user: Any, codename: str = "change_cardhold") -> Any:
    """Grant ``user`` a card hold model permission; returns the user reloaded (Django
    caches permissions on the user object)."""
    import swapper
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    CardHold = swapper.load_model("baseapp_payments", "CardHold")
    user.user_permissions.add(
        Permission.objects.get(
            codename=codename, content_type=ContentType.objects.get_for_model(CardHold)
        )
    )
    return type(user).objects.get(pk=user.pk)
