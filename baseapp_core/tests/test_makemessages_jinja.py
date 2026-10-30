from baseapp_core.management.commands.makemessages import jinja_templatize


def test_extracts_string_arguments_keeping_line_numbers() -> None:
    # Only the literal arguments matter to xgettext; keyword arguments are dropped.
    src = (
        "{% extends 'emails/base.html.j2' %}\n"
        "\n"
        '<p>{{ _("Hello,") }}</p>\n'
        '<p>{{ _("Changed to %(new_email)s.", new_email=new_email) }} {{ gettext("Bye") }}</p>\n'
        "{{ url }}\n"
        "{{ ngettext('%(n)d item', '%(n)d items', n) }}\n"
    )
    assert jinja_templatize(src).splitlines() == [
        "",
        "",
        '_("Hello,")',
        '_("Changed to %(new_email)s."); gettext("Bye")',
        "",
        "ngettext('%(n)d item', '%(n)d items')",
    ]


def test_ignores_identifiers_that_merely_end_in_underscore() -> None:
    src = '{{ some_("not gettext") }} {{ obj._("not gettext") }}'
    assert jinja_templatize(src) == "\n"


def test_keeps_escaped_quotes_inside_the_literal() -> None:
    src = '{{ _("Didn\'t sign up? Say \\"no\\".") }}'
    assert jinja_templatize(src) == '_("Didn\'t sign up? Say \\"no\\".")\n'


def test_extracts_calls_spanning_several_lines() -> None:
    src = (
        "<p>{{ _(\n"
        '    "Hello %(name)s,",\n'
        "    name=name,\n"
        ") }}</p>\n"
        "{{ ngettext('%(n)d item',\n"
        "            '%(n)d items', n) }}\n"
    )
    assert jinja_templatize(src).splitlines() == [
        '_("Hello %(name)s,")',
        "",
        "",
        "",
        "ngettext('%(n)d item', '%(n)d items')",
        "",
    ]


def test_escapes_newlines_inside_a_literal() -> None:
    src = '{{ _("First line\nsecond line") }}\n'
    assert jinja_templatize(src).splitlines()[0] == '_("First line\\nsecond line")'
