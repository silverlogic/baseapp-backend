import enum
import re
from functools import lru_cache
from typing import Any

import strawberry
from django.db.models import Model
from django.utils.encoding import force_str
from graphql import assert_name


def _to_camel_case(snake: str) -> str:
    head, *tail = snake.split("_")
    return head + "".join(part.capitalize() if part else "_" for part in tail)


def _to_const(value: str) -> str:
    return re.sub(r"[\W|^]+", "_", value).upper()


def choice_member_name(value: Any) -> str:
    """graphene_django.converter.convert_choice_name: `1` -> `A_1`, `pending` -> `PENDING`."""
    name = _to_const(force_str(value))
    try:
        assert_name(name)
    except Exception:
        name = f"A_{name}"
    return name


@lru_cache(maxsize=None)
def choices_enum(model: type[Model], field_name: str) -> type[enum.Enum]:
    """The enum graphene-django generates for a model field with `choices`.

    Named `<AppLabel><ModelName><FieldName>Choices`; members keep the stored values, so resolvers
    can return the raw column value.
    """
    field = model._meta.get_field(field_name)
    name = "{app}{model}{field}Choices".format(
        app=_to_camel_case(model._meta.app_label.title()),
        model=model._meta.object_name,
        field=_to_camel_case(field.name.title()),
    )
    members = {choice_member_name(value): value for value, _label in field.flatchoices}
    return strawberry.enum(enum.Enum(name, members), name=name)


@lru_cache(maxsize=None)
def enum_from_choices(choices: type[enum.Enum], name: str | None = None) -> type[enum.Enum]:
    """Expose a Django `TextChoices`/`IntegerChoices` class as an enum (graphene `Enum.from_enum`).

    The class itself is wrapped, so inputs arrive as real choices members, as with Graphene.
    """
    return strawberry.enum(choices, name=name or choices.__name__)
