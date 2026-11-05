from typing import Any

from django.conf import settings
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField as PhoneNumberModelField
from phonenumber_field.serializerfields import PhoneNumberField
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer as OrigModelSerializer

from baseapp_core.hashids.strategies import should_use_public_id

from .fields import PublicIdRelatedField, ThumbnailImageField


def _use_public_id_related_fields() -> bool:
    """`settings.BASEAPP_REST_PUBLIC_ID_RELATED_FIELDS` (default False)."""
    return bool(getattr(settings, "BASEAPP_REST_PUBLIC_ID_RELATED_FIELDS", False))


class ModelSerializer(OrigModelSerializer):
    def build_url_field(
        self, field_name, model_class
    ) -> tuple[type[serializers.Field], dict[str, Any]]:
        """
        Create a field representing the object's own URL.
        """
        field_class = self.serializer_url_field
        field_kwargs = {
            "view_name": "{model_name}s-detail".format(
                model_name=model_class._meta.object_name.lower()
            )
        }
        return field_class, field_kwargs

    def build_standard_field(
        self, field_name, model_field
    ) -> tuple[type[serializers.Field], dict[str, Any]]:
        field_class, field_kwargs = super().build_standard_field(field_name, model_field)
        is_primary = bool(getattr(model_field, "primary_key", False))

        # Use public_id for primary key fields if model is compatible and feature is enabled
        if model_field.name in ("id", "pk") or is_primary:
            if should_use_public_id(self.Meta.model):
                field_class = serializers.CharField
                field_kwargs["source"] = "public_id"
                field_kwargs["read_only"] = True

        if issubclass(field_class, PhoneNumberField) and model_field.blank:
            field_kwargs["allow_blank"] = True
        return field_class, field_kwargs

    def build_relational_field(
        self, field_name, relation_info
    ) -> tuple[type[serializers.Field], dict[str, Any]]:
        """
        With `BASEAPP_REST_PUBLIC_ID_RELATED_FIELDS = True`, foreign keys and many-to-many
        fields to a model that uses public ids are rendered and accepted as public ids
        (`PublicIdRelatedField`) instead of integer pks.
        """
        field_class, field_kwargs = super().build_relational_field(field_name, relation_info)
        if (
            field_class is self.serializer_related_field
            and issubclass(field_class, serializers.PrimaryKeyRelatedField)
            and _use_public_id_related_fields()
            and should_use_public_id(relation_info.related_model)
        ):
            field_class = PublicIdRelatedField
        return field_class, field_kwargs


ModelSerializer.serializer_field_mapping[models.ImageField] = ThumbnailImageField
ModelSerializer.serializer_field_mapping[PhoneNumberModelField] = PhoneNumberField
