"""Code-declared email templates with editable database overrides.

A project declares each email it sends once, usually from ``AppConfig.ready()``::

    from baseapp_message_templates.registry import Placeholder, register_email_template

    register_email_template(
        "orders/shipped",
        label=_("Order shipped"),
        group="orders",
        placeholders=[
            Placeholder("order.number", help=_("Order number"), sample="A-1001"),
            Placeholder("user.first_name", sample="Ada"),
        ],
        editable=("subject",),
    )

The default copy lives in template files (``emails/orders/shipped.subject.txt.j2``,
``.body.txt.j2`` and an optional ``.body.html.j2``). Staff may override the ``editable`` parts
by filling the matching fields of the ``EmailTemplate`` row with that name; a blank field falls
back to the file. Overrides are rendered with the Django template engine against a context
limited to the declared placeholders, so an override cannot reach objects the code did not
offer to it.

Names that are not registered keep rendering their files by pattern, so
:func:`render_email_template` can replace a project's own ``render_to_string`` calls one template
at a time.
"""

import copy
import logging
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.template import (
    Context,
    Engine,
    Template,
    TemplateDoesNotExist,
    TemplateSyntaxError,
    engines,
)
from django.template.base import Lexer, TokenType
from django.template.loader import render_to_string
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _
from jinja2 import ChainableUndefined

if TYPE_CHECKING:
    from .models import EmailTemplate

logger = logging.getLogger(__name__)

EditablePart = Literal["subject", "plain_text_content", "html_content"]

# Model fields that may be overridden, in rendering order (html last: it receives body_text).
EDITABLE_PARTS: tuple[str, ...] = ("subject", "plain_text_content", "html_content")

# Model field -> key of BASEAPP_MESSAGE_TEMPLATES_FILE_PATTERNS.
_FILE_KEYS = {"subject": "subject", "plain_text_content": "text", "html_content": "html"}

DEFAULT_FILE_PATTERNS = {
    "subject": "emails/{name}.subject.txt.j2",
    "text": "emails/{name}.body.txt.j2",
    "html": "emails/{name}.body.html.j2",
}

# Names every Django template can use without them being declared.
_BUILTIN_NAMES = frozenset({"True", "False", "None", "forloop", "block"})

# Tags an override may use. Anything else (include, extends, load, debug, url, ...) could read
# other templates, files or the whole context, so validate_override() rejects it.
ALLOWED_OVERRIDE_TAGS = frozenset(
    {
        "autoescape",
        "endautoescape",
        "comment",
        "endcomment",
        "cycle",
        "filter",
        "endfilter",
        "firstof",
        "for",
        "empty",
        "endfor",
        "if",
        "elif",
        "else",
        "endif",
        "ifchanged",
        "endifchanged",
        "lorem",
        "now",
        "regroup",
        "resetcycle",
        "spaceless",
        "endspaceless",
        "templatetag",
        "verbatim",
        "endverbatim",
        "widthratio",
        "with",
        "endwith",
    }
)

# Tags whose arguments are not variables.
_TAGS_WITHOUT_VARIABLES = frozenset(
    {"autoescape", "comment", "filter", "lorem", "now", "resetcycle", "templatetag", "verbatim"}
)
_TAG_KEYWORDS = frozenset({"and", "or", "not", "in", "is", "as", "by", "reversed", "silent"})
_STRING_RE = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'")
_NAME_RE = re.compile(r"(?<![\w.])([A-Za-z_]\w*)((?:\.\w+)*)")
_FILTER_NAME_RE = re.compile(r"\|\s*\w+")


@dataclass(frozen=True)
class Placeholder:
    """A value an email template receives, as offered to staff editing an override.

    ``name`` is a dotted path (``"order.number"``); its first segment is the context key the
    sending code passes. ``sample`` is used by previews and test sends.
    """

    name: str
    help: Any = ""
    sample: Any = ""

    @property
    def root(self) -> str:
        return self.name.split(".", 1)[0]


@dataclass(frozen=True)
class RenderedEmail:
    """The three parts of a rendered email.

    ``customized`` holds the parts (``"subject"``, ``"plain_text_content"``,
    ``"html_content"``) that came from an override instead of the template files.
    """

    subject: str
    body_text: str
    body_html: str
    customized: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class EmailPreview(RenderedEmail):
    """A :class:`RenderedEmail` rendered with sample values (see :func:`preview_email_template`)."""

    @property
    def preview_subject(self) -> str:
        return self.subject


@dataclass(frozen=True)
class RegisteredTemplate:
    """A registered email template. Build it with :func:`register_email_template`."""

    name: str
    label: Any
    group: str = ""
    description: Any = ""
    subject_template: str | None = None
    text_template: str | None = None
    html_template: str | None = None
    placeholders: tuple[Placeholder, ...] = ()
    editable: tuple[str, ...] = ("subject",)
    sample_context: Callable[[], dict] | None = None

    @property
    def placeholder_roots(self) -> frozenset[str]:
        return frozenset(placeholder.root for placeholder in self.placeholders)

    def template_path(self, part: str) -> str:
        """The file holding the default copy of ``part`` (a model field name)."""
        explicit = {
            "subject": self.subject_template,
            "plain_text_content": self.text_template,
            "html_content": self.html_template,
        }[part]
        return explicit or file_path_for(self.name, part)

    def is_editable(self, part: str) -> bool:
        return part in self.editable


class EmailTemplateRegistry:
    """Ordered, in-memory registry of :class:`RegisteredTemplate` keyed by name."""

    def __init__(self) -> None:
        self._templates: dict[str, RegisteredTemplate] = {}

    def register(self, template: RegisteredTemplate) -> RegisteredTemplate:
        """Add ``template``; registering the same name again replaces it in place."""
        self._templates[template.name] = template
        return template

    def unregister(self, name: str) -> None:
        self._templates.pop(name, None)

    def clear(self) -> None:
        self._templates.clear()

    def get(self, name: str) -> RegisteredTemplate | None:
        return self._templates.get(name)

    def is_registered(self, name: str) -> bool:
        return name in self._templates

    def list(self, group: str | None = None) -> list[RegisteredTemplate]:
        """All templates in registration order, limited to ``group`` when given."""
        templates = list(self._templates.values())
        if group is None:
            return templates
        return [template for template in templates if template.group == group]


email_templates = EmailTemplateRegistry()


def register_email_template(
    name: str,
    *,
    label: Any,
    group: str = "",
    description: Any = "",
    subject_template: str | None = None,
    text_template: str | None = None,
    html_template: str | None = None,
    placeholders: Sequence[Placeholder | str] = (),
    editable: Iterable[EditablePart] = ("subject",),
    sample_context: Callable[[], dict] | None = None,
) -> RegisteredTemplate:
    """Register (or replace) an email template.

    Args:
        name: Stable identifier; also the ``EmailTemplate.name`` holding its overrides.
        label: User-facing name (a lazy translation is fine).
        group: Free-form key used to list related templates together.
        description: Optional user-facing help text.
        subject_template, text_template, html_template: Template files with the default copy.
            Each defaults to ``BASEAPP_MESSAGE_TEMPLATES_FILE_PATTERNS`` formatted with ``name``.
            The html file is optional.
        placeholders: Values the template receives, as :class:`Placeholder` or dotted names.
            Overrides may only use these (plus ``BASEAPP_MESSAGE_TEMPLATES_BASE_CONTEXT``).
        editable: Parts staff may override: ``"subject"``, ``"plain_text_content"`` and/or
            ``"html_content"``. Pass ``()`` for a template that is listed but not editable.
        sample_context: ``callable() -> dict`` with sample values for previews, merged over the
            placeholder samples. Use it for values a flat sample cannot express (lists, dates).
    """
    editable_parts = tuple(editable)
    unknown = [part for part in editable_parts if part not in EDITABLE_PARTS]
    if unknown:
        raise ImproperlyConfigured(
            f"Unknown editable part(s) {unknown!r} for email template {name!r}; "
            f"use {EDITABLE_PARTS!r}."
        )
    return email_templates.register(
        RegisteredTemplate(
            name=name,
            label=label,
            group=group,
            description=description,
            subject_template=subject_template,
            text_template=text_template,
            html_template=html_template,
            placeholders=tuple(
                p if isinstance(p, Placeholder) else Placeholder(name=p) for p in placeholders
            ),
            editable=editable_parts,
            sample_context=sample_context,
        )
    )


def get_registered_template(name: str) -> RegisteredTemplate | None:
    return email_templates.get(name)


def file_path_for(name: str, part: str) -> str:
    """The template file for ``part`` (a model field name) of ``name``, from the file patterns."""
    patterns = {
        **DEFAULT_FILE_PATTERNS,
        **(getattr(settings, "BASEAPP_MESSAGE_TEMPLATES_FILE_PATTERNS", None) or {}),
    }
    return patterns[_FILE_KEYS[part]].format(name=name)


def get_base_context(recipient: str | None = None) -> dict[str, Any]:
    """Values every email receives, from ``BASEAPP_MESSAGE_TEMPLATES_BASE_CONTEXT``.

    The setting is a dotted path to ``callable(recipient) -> dict``; unset means ``{}``.
    """
    path = getattr(settings, "BASEAPP_MESSAGE_TEMPLATES_BASE_CONTEXT", None)
    if not path:
        return {}
    func = import_string(path) if isinstance(path, str) else path
    return dict(func(recipient) or {})


# Rendering ------------------------------------------------------------------------------------


class PreviewUndefined(ChainableUndefined):
    """A Jinja undefined that prints itself as ``{{ dotted.name }}`` in previews."""

    __slots__ = ()

    def __str__(self) -> str:
        return "{{ %s }}" % (self._undefined_name or "")

    def __getattr__(self, name: str) -> Any:
        if name[:2] == "__":
            raise AttributeError(name)
        dotted = f"{self._undefined_name}.{name}" if self._undefined_name else name
        return type(self)(name=dotted)

    __getitem__ = __getattr__


def _django_engine() -> Engine:
    try:
        return Engine.get_default()
    except ImproperlyConfigured:
        return Engine()


def _preview_engine() -> Engine:
    """A copy of the Django engine that prints unknown variables as ``{{ name }}``."""
    engine = copy.copy(_django_engine())
    engine.string_if_invalid = "{{ %s }}"
    return engine


def _render_override(
    source: str, context: Mapping[str, Any], *, autoescape: bool, engine: Engine | None = None
) -> str:
    template = Template(source, engine=engine or _django_engine())
    return _plain(template.render(Context(dict(context), autoescape=autoescape)))


def _render_file(path: str, context: Mapping[str, Any], *, preview: bool = False) -> str:
    if not preview:
        return render_to_string(path, dict(context))
    return _render_file_for_preview(path, context)


def _render_file_for_preview(path: str, context: Mapping[str, Any]) -> str:
    """Render ``path`` like ``render_to_string``, printing unknown names as ``{{ name }}``."""
    last_exc: TemplateDoesNotExist | None = None
    for engine in engines.all():
        try:
            backend_template = engine.get_template(path)
        except TemplateDoesNotExist as exc:
            last_exc = exc
            continue
        env = getattr(engine, "env", None)
        if env is not None:  # Jinja2 (django_jinja or Django's own backend)
            overlay = env.overlay(undefined=PreviewUndefined)
            return overlay.get_template(path).render(dict(context))
        inner = getattr(backend_template, "template", None)
        if isinstance(inner, Template):  # DjangoTemplates
            preview_template = Template(inner.source, engine=_preview_engine())
            return preview_template.render(Context(dict(context)))
        return backend_template.render(dict(context))  # pragma: no cover - other backends
    raise last_exc or TemplateDoesNotExist(path)


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _plain(text: str) -> str:
    """``text`` as a plain ``str``.

    Template engines return safe strings; left that way, the rendered plain text would skip
    escaping when the html part prints ``body_text``.
    """
    return str.__str__(text)


def _load_row(name: str) -> "EmailTemplate | None":
    from .models import EmailTemplate

    return EmailTemplate.objects.filter(name=name).first()


def _render(
    name: str,
    context: Mapping[str, Any],
    *,
    overrides: Mapping[str, str | None] | None,
    recipient: str | None,
    preview: bool,
    row: "EmailTemplate | None" = None,
    row_loaded: bool = False,
) -> RenderedEmail:
    registered = email_templates.get(name)
    base_context = get_base_context(recipient)
    full_context = {**base_context, **context}
    overrides = overrides or {}

    if registered is not None and registered.editable and not row_loaded:
        row = _load_row(name)

    def override_for(part: str) -> str | None:
        if registered is None or not registered.is_editable(part):
            return None
        for candidate in (overrides.get(part), getattr(row, part, None) if row else None):
            if candidate is not None and str(candidate).strip():
                return str(candidate)
        return None

    restricted: dict[str, Any] = {}
    if registered is not None:
        roots = registered.placeholder_roots
        restricted = {
            **base_context,
            **{key: value for key, value in context.items() if key in roots},
        }
    engine = _preview_engine() if preview else None

    customized: set[str] = set()
    parts: dict[str, str] = {}
    for part in EDITABLE_PARTS:
        extra = {"body_text": parts["plain_text_content"]} if part == "html_content" else {}
        override = override_for(part)
        if override is not None:
            parts[part] = _render_override(
                override,
                {**restricted, **extra},
                autoescape=part == "html_content",
                engine=engine,
            )
            customized.add(part)
            continue

        path = registered.template_path(part) if registered else file_path_for(name, part)
        try:
            parts[part] = _plain(_render_file(path, {**full_context, **extra}, preview=preview))
        except TemplateDoesNotExist:
            if part != "html_content":
                raise
            parts[part] = ""

    return RenderedEmail(
        subject=_collapse(parts["subject"]),
        body_text=parts["plain_text_content"],
        body_html=parts["html_content"],
        customized=frozenset(customized),
    )


def render_email_template(
    name: str,
    context: Mapping[str, Any] | None = None,
    *,
    overrides: Mapping[str, str | None] | None = None,
    fallback: str | None = None,
    recipient: str | None = None,
    row: "EmailTemplate | None" = None,
) -> RenderedEmail:
    """Render the subject, plain text and html of the email ``name``.

    For each part, the first non-blank of ``overrides[part]`` and the ``EmailTemplate`` row's
    field is used, but only for parts the registration marks ``editable``. An override is
    rendered with the Django template engine against the declared placeholder roots plus
    ``BASEAPP_MESSAGE_TEMPLATES_BASE_CONTEXT``; autoescaping is off for the subject and the plain
    text. Every other part renders its template file with the full context through
    ``render_to_string`` (any engine). The html part also receives ``body_text``, the rendered
    plain text, so a text override flows into a branded html layout. A missing html file
    renders as ``""``. The subject's whitespace is collapsed to single spaces.

    Names that are not registered render their files by pattern and ignore overrides.

    Args:
        name: Registered name, or any name whose files follow the file patterns.
        context: Template context.
        overrides: Per-send text keyed by part, e.g. ``{"subject": "..."}``.
        fallback: Another name rendered when the subject or text file of ``name`` is missing.
        recipient: Passed to ``BASEAPP_MESSAGE_TEMPLATES_BASE_CONTEXT``.
        row: The ``EmailTemplate`` row of ``name`` when the caller already holds it.

    Raises:
        TemplateDoesNotExist: When neither ``name`` nor ``fallback`` has a subject and a text.
    """
    context = dict(context or {})
    candidates = [name] + ([fallback] if fallback and fallback != name else [])
    last_exc: TemplateDoesNotExist | None = None
    for candidate in candidates:
        try:
            return _render(
                candidate,
                context,
                overrides=overrides,
                recipient=recipient,
                preview=False,
                row=row if candidate == name else None,
                row_loaded=row is not None and candidate == name,
            )
        except TemplateDoesNotExist as exc:
            last_exc = exc
    raise last_exc or TemplateDoesNotExist(name)


def _expand(dotted: str, value: Any) -> dict[str, Any]:
    head, _sep, rest = dotted.partition(".")
    return {head: _expand(rest, value) if rest else value}


def _deep_merge(base: dict[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in extra.items():
        if isinstance(merged.get(key), dict) and isinstance(value, Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_sample_context(name: str) -> dict[str, Any]:
    """Sample values for ``name``: placeholder samples as nested dicts, then ``sample_context()``."""
    registered = email_templates.get(name)
    if registered is None:
        return {}
    sample: dict[str, Any] = {}
    for placeholder in registered.placeholders:
        if placeholder.sample is None or placeholder.sample == "":
            continue
        sample = _deep_merge(sample, _expand(placeholder.name, placeholder.sample))
    if registered.sample_context is not None:
        sample = _deep_merge(sample, registered.sample_context() or {})
    return sample


def preview_email_template(
    name: str,
    overrides: Mapping[str, str | None] | None = None,
    *,
    recipient: str | None = None,
    row: "EmailTemplate | None" = None,
) -> EmailPreview:
    """Render ``name`` with its sample values (see :func:`get_sample_context`).

    Values without a sample print as ``{{ name }}`` instead of disappearing, in overrides and in
    template files alike. ``overrides`` work as in :func:`render_email_template`, so an editor
    can preview text before saving it. Rendering errors (a filter given a placeholder string
    instead of a date, say) propagate to the caller.
    """
    rendered = _render(
        name,
        get_sample_context(name),
        overrides=overrides,
        recipient=recipient,
        preview=True,
        row=row,
        row_loaded=row is not None,
    )
    return EmailPreview(
        subject=rendered.subject,
        body_text=rendered.body_text,
        body_html=rendered.body_html,
        customized=rendered.customized,
    )


# Validation -----------------------------------------------------------------------------------


def _bound_names(tag: str, args: str) -> set[str]:
    """Names a tag defines for its body: ``for x, y in``, ``with a=b``, ``... as name``."""
    bound: set[str] = set()
    if tag == "for" and " in " in f" {args} ":
        loop_vars = f" {args} ".split(" in ", 1)[0]
        bound.update(part.strip() for part in loop_vars.split(",") if part.strip())
    if tag == "with":
        bound.update(re.findall(r"(\w+)=", args))
    bound.update(re.findall(r"\bas\s+(\w+)", args))
    return bound


def _scan(source: str) -> tuple[set[str], set[str], set[str]]:
    """Return (roots of the variables used, names bound by tags, tag names) of ``source``."""
    roots: set[str] = set()
    bound: set[str] = set()
    tags: set[str] = set()
    skip_until: str | None = None
    for token in Lexer(source).tokenize():
        if token.token_type == TokenType.BLOCK:
            tag, _sep, args = token.contents.strip().partition(" ")
            if skip_until is not None:
                if tag == skip_until:
                    skip_until = None
                    tags.add(tag)
                continue
            tags.add(tag)
            if tag in {"comment", "verbatim"}:
                skip_until = f"end{tag}"
            if tag in _TAGS_WITHOUT_VARIABLES:
                continue
            args = _STRING_RE.sub('""', args)
            bound.update(_bound_names(tag, args))
            args = re.sub(r"\bby\s+[\w.]+", "", args)
            args = re.sub(r"\b\w+=", "", args)
        elif token.token_type == TokenType.VAR and skip_until is None:
            args = _STRING_RE.sub('""', token.contents)
        else:
            continue
        args = _FILTER_NAME_RE.sub("", args)
        for match in _NAME_RE.finditer(args):
            if match.group(1) not in _TAG_KEYWORDS:
                roots.add(match.group(1))
    return roots, bound, tags


def validate_override(name: str, field: str, text: str | None) -> list[str]:
    """Check override ``text`` for ``field`` of the email ``name``; return error messages.

    The text must compile with the Django template engine, use only the tags in
    ``ALLOWED_OVERRIDE_TAGS`` and, for registered names, only the declared placeholder roots
    (plus the base context keys and, in ``html_content``, ``body_text``). Blank text is valid:
    it resets the part to its default.
    """
    if field not in EDITABLE_PARTS:
        raise ValueError(f"{field!r} is not an editable part; use one of {EDITABLE_PARTS!r}.")
    if not text or not text.strip():
        return []

    try:
        Template(text, engine=_django_engine())
    except TemplateSyntaxError as exc:
        return [_("Template syntax error: %(error)s") % {"error": exc}]

    errors: list[str] = []
    roots, bound, tags = _scan(text)
    for tag in sorted(tags - ALLOWED_OVERRIDE_TAGS):
        errors.append(_("The “%(tag)s” tag is not allowed here.") % {"tag": tag})

    registered = email_templates.get(name)
    if registered is None:
        return errors

    allowed = set(registered.placeholder_roots) | bound | _BUILTIN_NAMES
    try:
        allowed |= set(get_base_context(None))
    except Exception:  # a base context that cannot be built without a recipient
        logger.exception("BASEAPP_MESSAGE_TEMPLATES_BASE_CONTEXT failed without a recipient")
    if field == "html_content":
        allowed.add("body_text")
    for root in sorted(roots - allowed):
        errors.append(_("Unknown placeholder “%(name)s”.") % {"name": root})
    return errors


# Template sources -----------------------------------------------------------------------------


def get_template_source(path: str) -> str | None:
    """The raw source of the template file ``path``, from the first engine that has it."""
    for engine in engines.all():
        try:
            backend_template = engine.get_template(path)
        except TemplateDoesNotExist:
            continue
        env = getattr(engine, "env", None)
        if env is not None and env.loader is not None:
            return env.loader.get_source(env, path)[0]
        return getattr(getattr(backend_template, "template", None), "source", None)
    return None


def get_default_source(name: str, part: str) -> str | None:
    """The raw default copy of ``part`` (a model field name) of the email ``name``."""
    registered = email_templates.get(name)
    path = registered.template_path(part) if registered else file_path_for(name, part)
    source = get_template_source(path)
    return source.strip() if source is not None else None


# Database rows --------------------------------------------------------------------------------


def is_customized(row: "EmailTemplate") -> bool:
    """Whether ``row`` overrides an editable part of its registered template."""
    registered = email_templates.get(row.name)
    if registered is None:
        return False
    return any((getattr(row, part, None) or "").strip() for part in registered.editable)


def sync_email_templates(using: str = "default", model: Any = None) -> int:
    """Create a blank ``EmailTemplate`` row for every registered name that has none.

    Runs after every ``migrate`` and as ``manage.py sync_email_templates``. Existing rows are
    never changed. Returns the number of rows created.
    """
    if model is None:
        from .models import EmailTemplate as model

    names = [template.name for template in email_templates.list()]
    if not names:
        return 0
    existing = {
        value.lower()
        for value in model.objects.using(using)
        .filter(name__in=names)
        .values_list("name", flat=True)
    }
    missing = [name for name in names if name.lower() not in existing]
    model.objects.using(using).bulk_create(
        [model(name=name, plain_text_content="") for name in missing], ignore_conflicts=True
    )
    return len(missing)
