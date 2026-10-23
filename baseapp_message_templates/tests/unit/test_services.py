import pytest

import baseapp_core.tests.factories as core_factories
import baseapp_message_templates.tests.factories as f
from baseapp_message_templates.permissions import MessageTemplatesPermissionsBackend
from baseapp_message_templates.services import (
    consume_test_send_quota,
    parse_rate,
    with_unsaved_text,
)
from baseapp_message_templates.tests.fixtures import grant

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "rate, expected",
    [("10/h", (10, 3600)), ("3/minute", (3, 60)), ("1/d", (1, 86400)), ("", None), (None, None)],
)
def test_parse_rate(rate, expected) -> None:
    assert parse_rate(rate) == expected


@pytest.mark.parametrize("rate", ["ten/h", "10", "10/w"])
def test_parse_rate_rejects_invalid(rate) -> None:
    with pytest.raises(ValueError):
        parse_rate(rate)


def test_no_limit(settings) -> None:
    settings.BASEAPP_MESSAGE_TEMPLATES_TEST_SEND_LIMIT = None
    user = core_factories.UserFactory()
    assert all(consume_test_send_quota(user) for _ in range(20))


def test_quota_is_per_user(settings) -> None:
    settings.BASEAPP_MESSAGE_TEMPLATES_TEST_SEND_LIMIT = "1/h"
    first, second = core_factories.UserFactory(), core_factories.UserFactory()
    assert consume_test_send_quota(first)
    assert not consume_test_send_quota(first)
    assert consume_test_send_quota(second)


def test_with_unsaved_text_leaves_the_row_untouched() -> None:
    row = f.EmailTemplateFactory.build(name="x", subject="Saved", plain_text_content="Body")
    copy, overrides = with_unsaved_text(
        row, {"subject": "", "plain_text_content": "New", "html_content": None}
    )
    assert (copy.subject, copy.plain_text_content) == ("", "Body")
    assert overrides == {"plain_text_content": "New"}
    assert row.subject == "Saved"


def test_permissions_backend() -> None:
    backend = MessageTemplatesPermissionsBackend()
    user = core_factories.UserFactory()
    template = f.EmailTemplateFactory(name="x")
    perm = "baseapp_message_templates.send_test_emailtemplate"

    assert not backend.has_perm(user, perm, template)
    grant(user, "send_test_emailtemplate")
    user = type(user).objects.get(pk=user.pk)
    assert backend.has_perm(user, perm, template)
    assert user.has_perm(perm, template)
    assert not backend.has_perm(user, perm, None)
    assert not backend.has_perm(user, "baseapp_message_templates.delete_emailtemplate", template)
    user.is_active = False
    assert not backend.has_perm(user, perm, template)
