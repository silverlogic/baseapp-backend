import re

from bs4 import BeautifulSoup
from django.template import Context, Template


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
    block_content_begin = "{% block content %}"
    block_content_end = "{% endblock content %}"
    load_filters = "{% load my_filters %}"
    replace_content_extend = "{% block content %}"
    replace_content_extend_bracket = " %}"

    blocked_copy = (block_content_begin + html).replace("\n ", "\n")
    blocked_text_copy = (block_content_begin + plain_text).replace("\n ", "\n")

    base_template_html = open(f"{extended_with}.html.j2", "r").read()
    base_template_txt = open(f"{extended_with}.txt.j2", "r").read()

    if replace_content_extend in base_template_html:
        full_copy_html = base_template_html.replace(replace_content_extend, f"{blocked_copy}", 1)
    else:
        full_copy_html = base_template_html.replace(
            replace_content_extend_bracket,
            f"{replace_content_extend_bracket}{blocked_copy}{block_content_end}",
            1,
        )

    if replace_content_extend in base_template_txt:
        full_copy_txt = base_template_txt.replace(
            replace_content_extend, f"{load_filters}{blocked_text_copy}", 1
        )
    else:
        full_copy_txt = base_template_txt.replace(
            replace_content_extend_bracket,
            f"{replace_content_extend_bracket}{load_filters}{blocked_text_copy}{block_content_end}",
            1,
        )

    return full_copy_html, full_copy_txt


# returns tuple of copy template (html message with context, message with context, subject with context)
def get_full_copy_template(
    copy_template,
    context={},
    use_base_template=False,
    extended_with="",
):
    # if custom plain text hasn't been provided, we create it automatically from the HTML
    plain_text = (
        copy_template.plain_text_content
        if copy_template.plain_text_content
        else _get_text_from_html(copy_template.html_content)
    )

    if use_base_template:
        copy_message_html, copy_message_txt = _wrap_in_base_template(
            copy_template.html_content,
            plain_text,
            extended_with,
        )

    else:
        copy_message_html = copy_template.html_content
        copy_message_txt = plain_text

    render_template_context = Context(context)

    html_message = _produce(copy_message_html, render_template_context)
    message = _produce(copy_message_txt, render_template_context)
    subject = _produce(copy_template.subject, render_template_context)

    return html_message, message, subject


def get_sms_template_message(
    copy_template,
    context={},
):
    message = _produce(copy_template.message, Context(context))
    return message
