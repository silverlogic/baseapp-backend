from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser
from django.utils import translation
from graphql.error import GraphQLError

from baseapp_core.graphql.decorators import login_required


@login_required
def resolve_secret(cls, root, info, **data) -> str:
    return "secret"


@pytest.mark.parametrize("language", ["en", "es", "pt-br"])
def test_login_required_error_is_a_plain_translated_string(language) -> None:
    info = SimpleNamespace(context=SimpleNamespace(user=AnonymousUser()))
    with translation.override(language):
        expected = translation.gettext("authentication required")
        with pytest.raises(GraphQLError) as exc:
            resolve_secret(None, None, info)
    assert type(exc.value.message) is str
    assert exc.value.message == expected
    assert str(exc.value) == expected
    assert exc.value.extensions == {"code": "authentication_required"}
