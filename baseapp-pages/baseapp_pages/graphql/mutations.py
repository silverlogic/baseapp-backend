import graphene
import swapper
from baseapp_core.graphql import (
    SerializerMutation,
    get_pk_from_relay_id,
    login_required,
)
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from ..models import URLPath
from .object_types import PageObjectType

Page = swapper.load_model("baseapp_pages", "Page")


class PageSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    url_path = serializers.CharField(required=False, allow_blank=True)
    title = serializers.CharField(required=False, allow_blank=True)
    body = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Page
        fields = ("user", "title", "body", "url_path")

    def validate_url_path(self, value):
        language = get_language()
        queryset = URLPath.objects.filter(
            Q(language=language) | Q(language__isnull=True), path=value
        )
        if self.instance:
            queryset = queryset.exclude(
                target_content_type=ContentType.objects.get_for_model(self.instance),
                target_object_id=self.instance.pk,
            )

        if queryset.exists():
            raise serializers.ValidationError(_("URL Path already being used"))

        return value

    def save(self, **kwargs):
        url_path = self.validated_data.pop("url_path", None)
        instance = super().save(**kwargs)
        language = get_language()
        if url_path:
            URLPath.objects.create(
                target=instance, path=url_path, language=language, is_active=True
            )
        return instance


class PageCreate(SerializerMutation):
    page = graphene.Field(PageObjectType._meta.connection.Edge)

    class Meta:
        serializer_class = PageSerializer

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        if not info.context.user.has_perm("baseapp_pages.add_page"):
            raise PermissionError(_("You don't have permission to create a page"))

        return super().mutate_and_get_payload(root, info, **input)

    @classmethod
    def perform_mutate(cls, serializer, info):
        obj = serializer.save()
        return cls(
            errors=None,
            page=PageObjectType._meta.connection.Edge(node=obj),
        )


class PageEdit(SerializerMutation):
    page = graphene.Field(PageObjectType)

    class Meta:
        serializer_class = PageSerializer

    class Input:
        id = graphene.ID(required=True)

    @classmethod
    def get_serializer_kwargs(cls, root, info, **input):
        pk = get_pk_from_relay_id(input.get("id"))
        instance = Page.objects.get(pk=pk)
        if not info.context.user.has_perm("baseapp_pages.change_page", instance):
            raise PermissionError(_("You don't have permission to edit this page"))
        return {
            "instance": instance,
            "data": input,
            "partial": True,
            "context": {"request": info.context},
        }

    @classmethod
    def perform_mutate(cls, serializer, info):
        obj = serializer.save()
        return cls(
            errors=None,
            page=obj,
        )

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        return super().mutate_and_get_payload(root, info, **input)


class PagesMutations(object):
    page_create = PageCreate.Field()
    page_edit = PageEdit.Field()
