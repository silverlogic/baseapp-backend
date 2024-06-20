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
from .object_types import ProfileObjectType

Profile = swapper.load_model("baseapp_profiles", "Profile")


class ProfileSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    url_path = serializers.CharField(required=False, allow_blank=True)
    title = serializers.CharField(required=False, allow_blank=True)
    body = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Profile
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


class ProfileCreate(SerializerMutation):
    profile = graphene.Field(ProfileObjectType._meta.connection.Edge)

    class Meta:
        serializer_class = ProfileSerializer

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        if not info.context.user.has_perm("baseapp_profiles.add_profile"):
            raise PermissionError(_("You don't have permission to create a profile"))

        return super().mutate_and_get_payload(root, info, **input)

    @classmethod
    def perform_mutate(cls, serializer, info):
        obj = serializer.save()
        return cls(
            errors=None,
            profile=ProfileObjectType._meta.connection.Edge(node=obj),
        )


class ProfileEdit(SerializerMutation):
    profile = graphene.Field(ProfileObjectType)

    class Meta:
        serializer_class = ProfileSerializer

    class Input:
        id = graphene.ID(required=True)

    @classmethod
    def get_serializer_kwargs(cls, root, info, **input):
        pk = get_pk_from_relay_id(input.get("id"))
        instance = Profile.objects.get(pk=pk)
        if not info.context.user.has_perm("baseapp_profiles.change_profile", instance):
            raise PermissionError(_("You don't have permission to edit this profile"))
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
            profile=obj,
        )

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, **input):
        return super().mutate_and_get_payload(root, info, **input)


class ProfilesMutations(object):
    profile_create = ProfileCreate.Field()
    profile_edit = ProfileEdit.Field()
