import re
from copy import deepcopy

import nh3
from bs4 import BeautifulSoup
from django.db.models import Case, Q, When
from django.template import Context, Template
from django.template.loader import render_to_string


def _get_text_from_html(html):
    soup = BeautifulSoup(html.replace("<br/>", "\n"), features="lxml")
    return soup.get_text().strip()


def _clean_extra_white_space(copy):
    return str(re.sub(" +", " ", copy)).strip()


def _produce(content, context):
    render_template = Template(content)
    return _clean_extra_white_space(render_template.render(context))


def _wrap_in_base_template(
    html,
    plain_text,
    extended_with,
):
    attributes = deepcopy(nh3.ALLOWED_ATTRIBUTES)
    tags = deepcopy(nh3.ALLOWED_TAGS)
    # add "class" attribute to all allowed tags
    for tag in tags:
        if tag in attributes:
            attributes[tag].add("class")
        else:
            attributes[tag] = {"class"}

    # add specific attributes
    attributes["a"].add("target")

    sanitized_html = nh3.clean(html, attributes=attributes)
    full_copy_html = render_to_string(
        f"{extended_with}.html.j2",
        {
            "template_content": sanitized_html,
        },
        using="jinja2",
    )

    full_copy_txt = render_to_string(
        f"{extended_with}.txt.j2",
        {
            "template_content": plain_text,
        },
        using="jinja2",
    )

    return full_copy_html, full_copy_txt


# returns tuple of copy template (html message with context, message with context, subject with context)
def get_full_copy_template(
    copy_template,
    context=None,
    use_base_template=False,
    extended_with="",
    language=None,
):
    if context is None:
        context = {}
    # TODO: Do we want to default to English if the language is not provided? Or should we raise an exception?
    content_translation = (
        copy_template.translations.filter(Q(language=language) | Q(language="en"))
        .order_by(
            Case(
                When(language=language, then=0),
                When(language="en", then=1),
                default=2,
            )
        )
        .first()
    )

    base_html = content_translation.html_content

    # if custom plain text hasn't been provided, we create it automatically from the HTML
    base_plain_text = content_translation.plain_text_content or _get_text_from_html(base_html)

    if use_base_template:
        copy_message_html, copy_message_txt = _wrap_in_base_template(
            base_html,
            base_plain_text,
            extended_with,
        )

    else:
        copy_message_html = base_html
        copy_message_txt = base_plain_text

    render_template_context = Context(context)

    html_message = _produce(copy_message_html, render_template_context)
    message = _produce(copy_message_txt, render_template_context)
    subject = _produce(content_translation.subject, render_template_context)

    return html_message, message, subject


def get_sms_template_message(
    copy_template,
    context={},
):
    message = _produce(copy_template.message, Context(context))
    return message
