from django.conf import settings
from django.core.checks import Error, register


@register()
def check_test_send_limit(app_configs, **kwargs) -> list[Error]:
    """Reject a ``BASEAPP_MESSAGE_TEMPLATES_TEST_SEND_LIMIT`` that cannot be parsed at startup,
    instead of inside the first ``emailTemplateSendTest``."""
    from .services import DEFAULT_TEST_SEND_LIMIT, parse_rate

    rate = getattr(settings, "BASEAPP_MESSAGE_TEMPLATES_TEST_SEND_LIMIT", DEFAULT_TEST_SEND_LIMIT)
    try:
        parse_rate(rate)
    except ValueError as exc:
        return [
            Error(
                str(exc),
                hint="Use '<count>/<period>' with a period of second, minute, hour or day "
                "(or s, m, h, d), e.g. '10/h', or None for no limit.",
                id="baseapp_message_templates.E001",
            )
        ]
    return []
