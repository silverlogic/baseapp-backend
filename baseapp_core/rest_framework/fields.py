import uuid
from typing import Any

from django.conf import settings
from django.core.cache import InvalidCacheBackendError, caches
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from drf_extra_fields.fields import Base64ImageField
from easy_thumbnails.files import get_thumbnailer
from rest_framework import serializers
from rest_framework.relations import PKOnlyObject

from baseapp_core.hashids.strategies import (
    drf_get_pk_from_public_id_or_pk,
    get_hashids_strategy_from_instance_or_cls,
    should_use_public_id,
)
from baseapp_core.plugins import shared_serializer_registry

try:
    cache = caches[settings.THUMBNAIL_CACHE]
except InvalidCacheBackendError:
    cache = None


class ThumbnailImageField(Base64ImageField):
    def __init__(self, *args, **kwargs) -> None:
        self.sizes = kwargs.pop("sizes", {})
        super(ThumbnailImageField, self).__init__(*args, **kwargs)

    def _get_cache_key(self, value) -> str:
        sizes = []
        for name, size in self.sizes.items():
            size_string = "-".join(map(str, size))
            sizes.append(f"{name}-{size_string}")
        sizes_string = "_".join(sizes)
        return f"et:thumbnail:{value.url}:{sizes_string}"

    def to_representation(self, value) -> dict[str, str] | None:
        if not value:
            return None

        if not getattr(value, "url", None):
            # If the file has not been saved it may not have a URL.
            return None

        has_sizes = len(self.sizes.keys()) > 0

        if has_sizes and cache:
            cache_key = self._get_cache_key(value)
            value_from_cache = cache.get(cache_key)
            if value_from_cache:
                return value_from_cache

        url = value.url
        request = self.context.get("request", None)
        if request is not None:
            url = request.build_absolute_uri(url)

        sizes = {"full_size": url}

        if has_sizes:
            thumbnailer = get_thumbnailer(value)
            for name, size in self.sizes.items():
                url = thumbnailer.get_thumbnail({"size": size}).url
                if request is not None:
                    url = request.build_absolute_uri(url)
                sizes[name] = url

            if cache:
                cache.set(cache_key, sizes, timeout=None)

        return sizes


class SharedSerializerField(serializers.Field):
    def __init__(
        self,
        serializer_name: str,
        *,
        default_representation: object = None,
        many: bool = False,
        **kwargs,
    ) -> None:
        self.serializer_name = serializer_name
        self.default_representation = default_representation
        self.many = many
        super().__init__(**kwargs)

    def get_attribute(self, instance: object) -> object:
        try:
            return super().get_attribute(instance)
        except (AttributeError, KeyError):
            return None

    def to_representation(self, value: object) -> object:
        return shared_serializer_registry.serialize(
            self.serializer_name,
            value,
            context=getattr(self.parent, "context", None),
            many=self.many,
            default=self.default_representation,
        )


def get_public_id_representation(instance: models.Model | None) -> str | int | None:
    """The id a client sees for `instance`: its public id as a string, or its pk for a model that
    does not use the public id strategy."""
    if instance is None:
        return None
    strategy = get_hashids_strategy_from_instance_or_cls(instance)
    value = strategy.id_resolver.get_id_from_instance(instance)
    return str(value) if isinstance(value, uuid.UUID) else value


class PublicIdField(serializers.Field):
    """Read-only field that renders the object's public id.

    By default it renders the serialized object itself (`source="*"`), so `id = PublicIdField()`
    replaces an integer `id`. With `source="<relation>"` it renders that related object's id. A
    model without public ids (or with `ENABLE_PUBLIC_ID_LOGIC = False`) renders its pk.

    Annotate list querysets with `annotate_public_ids()` to avoid one query per row.
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs["read_only"] = True
        kwargs.setdefault("source", "*")
        super().__init__(**kwargs)

    def to_representation(self, value: models.Model) -> str | int | None:
        return get_public_id_representation(value)


class _PublicIdOnlyObject:
    """Stands in for a related object whose public id was annotated on the parent row."""

    def __init__(self, public_id: Any) -> None:
        self.public_id = public_id


class PublicIdRelatedField(serializers.RelatedField):
    """A `PrimaryKeyRelatedField` that speaks public ids.

    - Output: the related object's public id. It reads the `<source>_public_id` annotation that
      `annotate_public_ids(queryset, "<source>")` adds, then a prefetched `<source>__document`,
      and only then queries.
    - Input: the related object's public id. A public id of another model is rejected. The
      integer pk is accepted while `allow_pk_lookup` is true (default:
      `BASEAPP_PUBLIC_ID_ALLOW_PK_LOOKUP`).
    - Supports `many=True`.

    For a related model without public ids (or with `ENABLE_PUBLIC_ID_LOGIC = False`) it behaves
    like `PrimaryKeyRelatedField`.
    """

    default_error_messages = {
        "required": _("This field is required."),
        "does_not_exist": _('Invalid id "{pk_value}" - object does not exist.'),
        "incorrect_type": _("Incorrect type. Expected an id, received {data_type}."),
    }

    def __init__(self, allow_pk_lookup: bool | None = None, **kwargs: Any) -> None:
        self.allow_pk_lookup = allow_pk_lookup
        super().__init__(**kwargs)

    def _get_related_model(self) -> type[models.Model] | None:
        queryset = self.get_queryset() if self.queryset is not None else None
        return getattr(queryset, "model", None)

    def use_pk_only_optimization(self) -> bool:
        # Without public ids the pk is all that is rendered, so skip loading the related row,
        # as PrimaryKeyRelatedField does.
        model_cls = self._get_related_model()
        return model_cls is not None and not should_use_public_id(model_cls)

    def get_attribute(self, instance: Any) -> Any:
        annotation = "__".join(self.source_attrs) + "_public_id"
        if self.source_attrs and isinstance(instance, models.Model):
            public_id = instance.__dict__.get(annotation)
            if public_id is not None:
                return _PublicIdOnlyObject(public_id)
        return super().get_attribute(instance)

    def to_representation(self, value: Any) -> str | int | None:
        if isinstance(value, _PublicIdOnlyObject):
            return str(value.public_id)
        if isinstance(value, PKOnlyObject):
            return value.pk
        return get_public_id_representation(value)

    def to_internal_value(self, data: Any) -> models.Model:
        if isinstance(data, bool) or not isinstance(data, (str, int, uuid.UUID)):
            self.fail("incorrect_type", data_type=type(data).__name__)

        queryset = self.get_queryset()
        pk = drf_get_pk_from_public_id_or_pk(
            data, queryset.model, allow_pk_lookup=self.allow_pk_lookup
        )
        if pk is None:
            self.fail("does_not_exist", pk_value=data)
        try:
            return queryset.get(pk=pk)
        except ObjectDoesNotExist:
            self.fail("does_not_exist", pk_value=data)
        except (TypeError, ValueError, DjangoValidationError):
            self.fail("incorrect_type", data_type=type(data).__name__)
