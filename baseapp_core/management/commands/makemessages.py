"""``makemessages`` that extracts from Jinja (``.j2``) templates and applies project defaults.

Django's ``templatize`` only understands Django template syntax, so the ``_("...")``
calls in Jinja email templates never reached the catalogs unless ``-e j2`` was passed
and django_jinja's regex patches were active. This command turns a ``.j2`` file into a
Python stub (one ``gettext`` call per source line, so ``#:`` locations stay correct)
before handing it to ``xgettext``, and defaults the extension list to include ``j2``.

When django_jinja is installed its own ``makemessages`` is used as the base class so
Jinja ``{% trans %}`` blocks in ``.html`` / ``.txt`` templates keep working too.

Project-wide defaults come from ``settings.BA_MAKEMESSAGES_DEFAULTS``::

    BA_MAKEMESSAGES_DEFAULTS = {
        "extensions": ["html", "txt", "py", "j2"],
        "ignore_patterns": ["baseapp-backend", "static"],
        "add_location": "file",
        "no_obsolete": True,
    }

Explicit command-line flags always win over these defaults.

Django resolves a management command to the *first* app in ``INSTALLED_APPS`` that
defines it, so a project that lists ``django_jinja`` before ``baseapp_core`` must
re-export this command from an app listed earlier (the template does so in ``apps.i18n``).
"""

import re
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.commands import makemessages as django_makemessages

try:
    from django_jinja.management.commands.makemessages import (
        Command as BaseMakeMessages,
    )
except ImportError:  # pragma: no cover - django_jinja is optional
    BaseMakeMessages = django_makemessages.Command

DEFAULT_EXTENSIONS = ["html", "txt", "py", "j2"]

_STRING = r"""(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')"""
# `_("msg")`, `gettext("msg", name=value)`, `ngettext("one", "many", n)`, `pgettext("ctx", "msg")`
JINJA_GETTEXT_RE = re.compile(
    r"(?<![\w.])(?P<func>_|gettext|ngettext|pgettext|npgettext)\(\s*"
    r"(?P<args>" + _STRING + r"(?:\s*,\s*" + _STRING + r")*)"
)


STRING_RE = re.compile(_STRING)


def jinja_templatize(src: str) -> str:
    """Return a Python stub with the gettext calls of a Jinja template, line numbers preserved.

    A call spanning several lines is emitted on the line it starts on.
    """
    lines: list[list[str]] = [[] for _line in src.removesuffix("\n").split("\n")]
    for match in JINJA_GETTEXT_RE.finditer(src):
        lineno = src.count("\n", 0, match.start())
        args = ", ".join(
            literal.replace("\n", "\\n") for literal in STRING_RE.findall(match.group("args"))
        )
        lines[lineno].append(f"{match.group('func')}({args})")
    return "\n".join("; ".join(calls) for calls in lines) + "\n"


class JinjaAwareBuildFile(django_makemessages.BuildFile):
    def preprocess(self) -> None:
        if not self.is_templatized or not self.path.endswith(".j2"):
            super().preprocess()
            return
        with open(self.path, encoding="utf-8") as fp:
            src_data = fp.read()
        with open(self.work_path, "w", encoding="utf-8") as fp:
            fp.write(jinja_templatize(src_data))


# BaseCommand is already an ancestor; naming it keeps static analysis able to see it.
class Command(BaseMakeMessages, BaseCommand):
    build_file_class = JinjaAwareBuildFile

    def _get_default_jinja_template_engine(self) -> dict[str, Any]:
        try:
            return super()._get_default_jinja_template_engine()
        except (AttributeError, IndexError):
            # No Jinja2 engine configured (or plain Django base): nothing to apply.
            return {}

    def handle(self, *args: Any, **options: Any) -> None:
        defaults = getattr(settings, "BA_MAKEMESSAGES_DEFAULTS", {})
        if not options.get("extensions"):
            options["extensions"] = list(defaults.get("extensions", DEFAULT_EXTENSIONS))
        if not options.get("ignore_patterns"):
            options["ignore_patterns"] = list(defaults.get("ignore_patterns", []))
        if not options.get("add_location") and not options.get("no_location"):
            options["add_location"] = defaults.get("add_location")
        if not options.get("no_obsolete"):
            options["no_obsolete"] = bool(defaults.get("no_obsolete", False))
        if not options.get("no_wrap"):
            options["no_wrap"] = bool(defaults.get("no_wrap", False))
        options.setdefault("jinja_engine", None)
        super().handle(*args, **options)
